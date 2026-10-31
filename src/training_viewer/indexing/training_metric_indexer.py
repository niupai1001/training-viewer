"""训练指标索引器。

把读取器产出的标准化记录写入 SQLite：维护每个文件的字节/行/事件游标，检测
截断与替换，去重重复导入，记录解析问题，并根据心跳和生命周期事件推导运行状态。
索引可以随时从原始日志完整重建。
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ..indexing.database import IndexDatabase
from ..log_readers.base import (
    ArtifactRecord,
    FileCursor,
    HeartbeatRecord,
    LifecycleRecord,
    MetricPoint,
    ParseIssue,
    file_identity,
    format_timestamp,
    relative_source_path,
    utc_now_iso,
)
from ..security.path_guard import UnsafeArtifactPathError, resolve_artifact_path
from ..source_adapters.base import DiscoveredRun

STALE_AFTER_SECONDS = 120
MAX_STORED_ISSUES = 2000
MAX_ARTIFACT_REFRESH = 2000

_STATUS_LABELS = {
    "started": "已启动",
    "resumed": "恢复训练",
    "completed": "已完成",
    "failed": "失败",
    "cancelled": "已取消",
}

_FILE_LEVEL_SOURCE_KINDS = {
    "generic-csv",
    "generic-tsv",
    "generic-jsonl",
    "plain-text",
}


@dataclass
class IngestReport:
    run_id: str
    changed: bool = False
    new_run: bool = False
    issues: list[ParseIssue] = field(default_factory=list)


def _issue_key(run_id: str | None, file_path: str, line_number: int, message: str) -> str:
    digest = hashlib.sha1(
        f"{run_id or 'scan'}|{file_path}|{line_number}|{message}".encode("utf-8")
    ).hexdigest()
    return f"issue:{digest}"


class TrainingMetricIndexer:
    """指标索引器：规范化记录 → 可查询的 SQLite 索引。"""

    def __init__(
        self,
        database: IndexDatabase,
        now: Callable[[], datetime] | None = None,
    ):
        self.database = database
        self._now = now or (lambda: datetime.now(timezone.utc))

    # ------------------------------------------------------------------ 公共入口
    def ingest(
        self,
        discovered: DiscoveredRun,
        root_path: Path,
    ) -> IngestReport:
        run_id = discovered.run_id
        report = IngestReport(run_id=run_id)
        run_directory = discovered.run_directory
        run_directory_text = str(run_directory)
        metadata_json = json.dumps(
            discovered.metadata, ensure_ascii=False, sort_keys=True, default=str
        )
        model = discovered.metadata.get("model") or {}
        dataset = discovered.metadata.get("dataset") or {}
        tags = discovered.metadata.get("tags") or []
        source = discovered.metadata.get("source") or {}
        seed = source.get("seed") if isinstance(source.get("seed"), int) else None
        tags_json = json.dumps(tags, ensure_ascii=False)
        now_iso = utc_now_iso()

        with self.database.transaction() as connection:
            existing = connection.execute(
                "SELECT * FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            other_at_directory = connection.execute(
                "SELECT run_id, source_kind FROM runs WHERE run_dir = ? AND run_id <> ?",
                (run_directory_text, run_id),
            ).fetchone()
            if other_at_directory is not None:
                shares_directory = (
                    other_at_directory["source_kind"] in _FILE_LEVEL_SOURCE_KINDS
                    or discovered.source_kind in _FILE_LEVEL_SOURCE_KINDS
                )
                if not shares_directory:
                    self._delete_run(connection, other_at_directory["run_id"])
                    self._record_issue(
                        connection,
                        run_id=None,
                        file_path=run_directory_text,
                        line_number=0,
                        message="同一目录的 run_id 发生变化，已删除旧运行的索引并按新元数据重建。",
                        severity="warning",
                    )
                    report.changed = True

            metadata_changed = existing is not None and existing["metadata_json"] != metadata_json
            moved = existing is not None and existing["run_dir"] != run_directory_text
            source_changed = existing is not None and existing["source_kind"] != discovered.source_kind

            if existing is None:
                connection.execute(
                    """
                    INSERT INTO runs (
                        run_id, source_kind, adapter_id, run_dir, root_path, project,
                        experiment, name, task, created_at, metadata_json, model_name,
                        model_architecture, dataset_name, tags_json, seed, status,
                        status_reason, last_updated_at, discovered_at, directory_available,
                        metadata_synthetic
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        discovered.source_kind,
                        discovered.adapter_id,
                        run_directory_text,
                        str(root_path),
                        str(discovered.metadata.get("project") or ""),
                        discovered.metadata.get("experiment"),
                        str(discovered.metadata.get("name") or run_id),
                        discovered.metadata.get("task"),
                        discovered.metadata.get("created_at"),
                        metadata_json,
                        model.get("name"),
                        model.get("architecture"),
                        dataset.get("name"),
                        tags_json,
                        seed,
                        "unknown",
                        "等待首次扫描。",
                        None,
                        now_iso,
                        1,
                        1 if discovered.metadata_synthetic else 0,
                    ),
                )
                report.new_run = True
                report.changed = True
            else:
                if moved or source_changed:
                    self._delete_run_data(connection, run_id)
                    report.changed = True
                    self._record_issue(
                        connection,
                        run_id=run_id,
                        file_path=run_directory_text,
                        line_number=0,
                        message=(
                            "运行目录或日志来源发生变化，已按新位置重建索引；"
                            "原始日志未被修改，历史备注仍按 run_id 保留。"
                        ),
                        severity="warning",
                    )
                if metadata_changed and not moved:
                    self._reset_csv_cursors(connection, run_id)
                connection.execute(
                    """
                    UPDATE runs SET
                        source_kind = ?, adapter_id = ?, run_dir = ?, root_path = ?,
                        project = ?, experiment = ?, name = ?, task = ?, created_at = ?,
                        metadata_json = ?, model_name = ?, model_architecture = ?,
                        dataset_name = ?, tags_json = ?, seed = ?, metadata_synthetic = ?,
                        directory_available = 1
                    WHERE run_id = ?
                    """,
                    (
                        discovered.source_kind,
                        discovered.adapter_id,
                        run_directory_text,
                        str(root_path),
                        str(discovered.metadata.get("project") or ""),
                        discovered.metadata.get("experiment"),
                        str(discovered.metadata.get("name") or run_id),
                        discovered.metadata.get("task"),
                        discovered.metadata.get("created_at"),
                        metadata_json,
                        model.get("name"),
                        model.get("architecture"),
                        dataset.get("name"),
                        tags_json,
                        seed,
                        1 if discovered.metadata_synthetic else 0,
                        run_id,
                    ),
                )
                if metadata_changed:
                    report.changed = True

            expected_files = {str(spec.file_path): spec for spec in discovered.log_files}
            self._drop_vanished_sources(connection, run_id, run_directory, expected_files)

            newest_file_mtime: float | None = None
            for file_path, spec in expected_files.items():
                try:
                    file_stat = spec.file_path.stat()
                except OSError as error:
                    report.issues.append(
                        ParseIssue(file_path, 0, f"日志文件不可读取：{error}", "warning")
                    )
                    continue
                newest_file_mtime = max(newest_file_mtime or 0.0, file_stat.st_mtime)
                cursor_row = connection.execute(
                    "SELECT * FROM ingestion_cursors WHERE file_path = ?", (file_path,)
                ).fetchone()
                cursor = (
                    FileCursor(
                        file_path=cursor_row["file_path"],
                        file_kind=cursor_row["file_kind"],
                        file_identity=cursor_row["file_identity"],
                        offset=cursor_row["offset"],
                        line_number=cursor_row["line_number"],
                        size=cursor_row["size"],
                        mtime=cursor_row["mtime"],
                    )
                    if cursor_row is not None
                    else None
                )
                if (
                    cursor is not None
                    and cursor.file_identity == file_identity(file_stat)
                    and cursor.size == file_stat.st_size
                    and cursor.mtime == file_stat.st_mtime
                ):
                    continue
                try:
                    read_result = spec.reader.read_new_records(
                        spec.file_path, run_directory, cursor
                    )
                except Exception as error:  # noqa: BLE001 - 单个读取器故障不能中断整个扫描
                    report.issues.append(
                        ParseIssue(file_path, 0, f"读取器异常，本文件本次未导入：{error}")
                    )
                    continue
                relative_file = relative_source_path(run_directory, spec.file_path)
                if read_result.reset:
                    self._delete_source_data(
                        connection, run_id, relative_file, file_path
                    )
                    if cursor is not None:
                        self._record_issue(
                            connection,
                            run_id=run_id,
                            file_path=file_path,
                            line_number=0,
                            message="检测到日志文件被截断、替换或轮转，已重建该文件的索引。",
                            severity="warning",
                        )
                inserted = self._insert_records(connection, run_id, run_directory, read_result.records)
                if inserted:
                    report.changed = True
                if read_result.cursor is not None:
                    self._upsert_cursor(connection, run_id, read_result.cursor)
                for issue in read_result.issues:
                    self._record_issue(
                        connection,
                        run_id=run_id,
                        file_path=issue.file_path,
                        line_number=issue.line_number,
                        message=issue.message,
                        severity=issue.severity,
                    )
                    report.issues.append(issue)
                if not any("尚未写完" in issue.message for issue in read_result.issues):
                    # 半行补齐后，之前“等待补齐”的提示不再成立。
                    connection.execute(
                        "DELETE FROM ingestion_issues WHERE run_id = ? AND file_path = ? "
                        "AND message LIKE '%尚未写完%'",
                        (run_id, file_path),
                    )

            self._refresh_artifact_existence(connection, run_id, run_directory)
            status, status_reason = self._compute_status(
                connection, run_id, discovered.source_kind
            )
            last_updated_at = (
                format_timestamp(datetime.fromtimestamp(newest_file_mtime, tz=timezone.utc))
                if newest_file_mtime is not None
                else existing["last_updated_at"] if existing is not None else now_iso
            )
            previous_status = existing["status"] if existing is not None else None
            previous_reason = existing["status_reason"] if existing is not None else None
            connection.execute(
                """
                UPDATE runs SET status = ?, status_reason = ?, last_updated_at = ?,
                    directory_available = 1
                WHERE run_id = ?
                """,
                (status, status_reason, last_updated_at, run_id),
            )
            if status != previous_status or status_reason != previous_reason:
                report.changed = True
            self._prune_issues(connection)
        return report

    def refresh_statuses(self) -> list[str]:
        """心跳/时间变化会改变状态；即使日志没有新行也要重新计算。"""
        changed_runs: list[str] = []
        with self.database.transaction() as connection:
            rows = connection.execute(
                "SELECT run_id, source_kind, status, status_reason FROM runs"
            ).fetchall()
            for row in rows:
                status, reason = self._compute_status(
                    connection, row["run_id"], row["source_kind"]
                )
                if status != row["status"] or reason != row["status_reason"]:
                    connection.execute(
                        "UPDATE runs SET status = ?, status_reason = ? WHERE run_id = ?",
                        (status, reason, row["run_id"]),
                    )
                    changed_runs.append(row["run_id"])
        return changed_runs

    def mark_directory_unavailable(self, run_id: str) -> bool:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                "UPDATE runs SET directory_available = 0, status = 'unknown', "
                "status_reason = '运行目录当前不可访问（可能被移动、重命名或所在磁盘未挂载）；"
                "已保留索引，不会删除原始数据。' WHERE run_id = ? AND directory_available = 1",
                (run_id,),
            )
            return cursor.rowcount > 0

    def replace_scan_issues(self, issues: list[ParseIssue]) -> None:
        """目录级问题（坏 run.json、缺少可选依赖）每次扫描后整体替换。"""
        with self.database.transaction() as connection:
            connection.execute("DELETE FROM ingestion_issues WHERE source_key LIKE 'scan:%'")
            for issue in issues:
                source_key = f"scan:{issue.file_path}:{issue.line_number}:{issue.message}"
                connection.execute(
                    """
                    INSERT OR REPLACE INTO ingestion_issues
                        (source_key, run_id, file_path, line_number, message, severity, created_at)
                    VALUES (?, NULL, ?, ?, ?, ?, ?)
                    """,
                    (
                        source_key,
                        issue.file_path,
                        issue.line_number,
                        issue.message,
                        issue.severity,
                        utc_now_iso(),
                    ),
                )
            self._prune_issues(connection)

    # ------------------------------------------------------------------ 内部实现
    def delete_run(self, run_id: str) -> bool:
        with self.database.transaction() as connection:
            exists = connection.execute(
                "SELECT 1 FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if exists is None:
                return False
            self._delete_run(connection, run_id)
        return True

    def delete_runs_for_source_files(self, file_paths: list[str]) -> list[str]:
        """删除包含指定原始文件索引的 Run；用于逻辑归并前的旧身份清理。"""
        if not file_paths:
            return []
        placeholders = ",".join("?" for _ in file_paths)
        with self.database.transaction() as connection:
            rows = connection.execute(
                f"SELECT DISTINCT run_id FROM ingestion_cursors WHERE file_path IN ({placeholders})",
                file_paths,
            ).fetchall()
            run_ids = [row["run_id"] for row in rows]
            for run_id in run_ids:
                self._delete_run(connection, run_id)
        return run_ids

    def _delete_run(self, connection: sqlite3.Connection, run_id: str) -> None:
        self._delete_run_data(connection, run_id)
        connection.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))

    def _delete_run_data(self, connection: sqlite3.Connection, run_id: str) -> None:
        connection.execute("DELETE FROM metric_points WHERE run_id = ?", (run_id,))
        connection.execute("DELETE FROM artifacts WHERE run_id = ?", (run_id,))
        connection.execute("DELETE FROM training_events WHERE run_id = ?", (run_id,))
        connection.execute("DELETE FROM ingestion_cursors WHERE run_id = ?", (run_id,))

    def _delete_source_data(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        relative_file: str,
        absolute_file: str,
    ) -> None:
        connection.execute(
            "DELETE FROM metric_points WHERE run_id = ? AND source_file = ?",
            (run_id, relative_file),
        )
        connection.execute(
            "DELETE FROM artifacts WHERE run_id = ? AND source_file = ?",
            (run_id, relative_file),
        )
        connection.execute(
            "DELETE FROM training_events WHERE run_id = ? AND source_file = ?",
            (run_id, relative_file),
        )
        connection.execute(
            "DELETE FROM ingestion_issues WHERE run_id = ? AND file_path = ?",
            (run_id, absolute_file),
        )

    def _reset_csv_cursors(self, connection: sqlite3.Connection, run_id: str) -> None:
        rows = connection.execute(
            "SELECT file_path, file_kind FROM ingestion_cursors WHERE run_id = ?",
            (run_id,),
        ).fetchall()
        run_row = connection.execute(
            "SELECT run_dir FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if run_row is None:
            return
        for row in rows:
            if row["file_kind"] != "csv":
                continue
            relative_file = relative_source_path(
                Path(run_row["run_dir"]), Path(row["file_path"])
            )
            self._delete_source_data(
                connection, run_id, relative_file, row["file_path"]
            )
            connection.execute(
                "DELETE FROM ingestion_cursors WHERE file_path = ?", (row["file_path"],)
            )

    def _drop_vanished_sources(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        run_directory: Path,
        expected_files: dict[str, object],
    ) -> None:
        rows = connection.execute(
            "SELECT file_path FROM ingestion_cursors WHERE run_id = ?", (run_id,)
        ).fetchall()
        for row in rows:
            file_path = row["file_path"]
            if file_path in expected_files:
                continue
            relative_file = relative_source_path(run_directory, Path(file_path))
            self._delete_source_data(connection, run_id, relative_file, file_path)
            connection.execute(
                "DELETE FROM ingestion_cursors WHERE file_path = ?", (file_path,)
            )
            self._record_issue(
                connection,
                run_id=run_id,
                file_path=file_path,
                line_number=0,
                message="日志文件已不存在，已移除它的索引（原始文件未被删除）。",
                severity="warning",
            )

    def _insert_records(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        run_directory: Path,
        records: list,
    ) -> bool:
        inserted = False
        for record in records:
            if isinstance(record, MetricPoint):
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO metric_points (
                        run_id, phase, metric_name, global_step, epoch, timestamp,
                        session_id, value, event_id, source_file, source_offset, line_number
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        record.phase,
                        record.metric_name,
                        record.global_step,
                        record.epoch,
                        record.timestamp,
                        record.session_id,
                        record.value,
                        record.event_id,
                        record.source_file,
                        record.source_offset,
                        record.line_number,
                    ),
                )
                inserted = inserted or cursor.rowcount > 0
            elif isinstance(record, ArtifactRecord):
                try:
                    resolved = resolve_artifact_path(run_directory, record.path)
                except UnsafeArtifactPathError as error:
                    self._record_issue(
                        connection,
                        run_id=run_id,
                        file_path=record.source_file,
                        line_number=record.line_number,
                        message=f"产物路径被拒绝：{error}",
                        severity="error",
                    )
                    continue
                exists = resolved.is_file()
                try:
                    file_stat = resolved.stat() if exists else None
                except OSError:
                    file_stat = None
                    exists = False
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO artifacts (
                        run_id, path, artifact_type, tag, phase, global_step, epoch,
                        group_id, sample_id, role, mime_type, metadata_json, timestamp,
                        session_id, event_id, source_file, source_offset, exists_on_disk,
                        size, mtime
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        record.path,
                        record.artifact_type,
                        record.tag,
                        record.phase,
                        record.global_step,
                        record.epoch,
                        record.group_id,
                        record.sample_id,
                        record.role,
                        record.mime_type,
                        json.dumps(record.metadata, ensure_ascii=False, default=str),
                        record.timestamp,
                        record.session_id,
                        record.event_id,
                        record.source_file,
                        record.source_offset,
                        1 if exists else 0,
                        file_stat.st_size if file_stat else None,
                        file_stat.st_mtime if file_stat else None,
                    ),
                )
                inserted = inserted or cursor.rowcount > 0
            elif isinstance(record, (LifecycleRecord, HeartbeatRecord)):
                if isinstance(record, LifecycleRecord):
                    event_type, status, message, global_step = (
                        "lifecycle",
                        record.status,
                        record.message,
                        None,
                    )
                else:
                    event_type, status, message, global_step = (
                        "heartbeat",
                        None,
                        None,
                        record.global_step,
                    )
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO training_events (
                        run_id, event_type, status, timestamp, session_id, global_step,
                        message, event_id, source_file, source_offset
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        event_type,
                        status,
                        record.timestamp,
                        record.session_id,
                        global_step,
                        message,
                        record.event_id,
                        record.source_file,
                        record.source_offset,
                    ),
                )
                inserted = inserted or cursor.rowcount > 0
        return inserted

    def _upsert_cursor(
        self, connection: sqlite3.Connection, run_id: str, cursor: FileCursor
    ) -> None:
        connection.execute(
            """
            INSERT INTO ingestion_cursors (
                file_path, run_id, file_kind, file_identity, offset, line_number,
                size, mtime, updated_at, health
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ok')
            ON CONFLICT(file_path) DO UPDATE SET
                run_id = excluded.run_id,
                file_kind = excluded.file_kind,
                file_identity = excluded.file_identity,
                offset = excluded.offset,
                line_number = excluded.line_number,
                size = excluded.size,
                mtime = excluded.mtime,
                updated_at = excluded.updated_at,
                health = 'ok'
            """,
            (
                cursor.file_path,
                run_id,
                cursor.file_kind,
                cursor.file_identity,
                cursor.offset,
                cursor.line_number,
                cursor.size,
                cursor.mtime,
                utc_now_iso(),
            ),
        )

    def _record_issue(
        self,
        connection: sqlite3.Connection,
        run_id: str | None,
        file_path: str,
        line_number: int,
        message: str,
        severity: str,
    ) -> None:
        connection.execute(
            """
            INSERT OR REPLACE INTO ingestion_issues (
                source_key, run_id, file_path, line_number, message, severity, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _issue_key(run_id, file_path, line_number, message),
                run_id,
                file_path,
                line_number,
                message,
                severity,
                utc_now_iso(),
            ),
        )

    def _prune_issues(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            DELETE FROM ingestion_issues WHERE id NOT IN (
                SELECT id FROM ingestion_issues ORDER BY id DESC LIMIT ?
            )
            """,
            (MAX_STORED_ISSUES,),
        )

    def _refresh_artifact_existence(
        self, connection: sqlite3.Connection, run_id: str, run_directory: Path
    ) -> None:
        rows = connection.execute(
            """
            SELECT id, path, exists_on_disk, size, mtime FROM artifacts
            WHERE run_id = ?
            ORDER BY exists_on_disk ASC, id DESC
            LIMIT ?
            """,
            (run_id, MAX_ARTIFACT_REFRESH),
        ).fetchall()
        for row in rows:
            try:
                resolved = resolve_artifact_path(run_directory, row["path"])
                exists = resolved.is_file()
                file_stat = resolved.stat() if exists else None
            except (UnsafeArtifactPathError, OSError):
                exists = False
                file_stat = None
            new_size = file_stat.st_size if file_stat else None
            new_mtime = file_stat.st_mtime if file_stat else None
            if (
                bool(row["exists_on_disk"]) != exists
                or row["size"] != new_size
                or row["mtime"] != new_mtime
            ):
                connection.execute(
                    "UPDATE artifacts SET exists_on_disk = ?, size = ?, mtime = ? WHERE id = ?",
                    (1 if exists else 0, new_size, new_mtime, row["id"]),
                )

    def _compute_status(
        self, connection: sqlite3.Connection, run_id: str, source_kind: str
    ) -> tuple[str, str]:
        if source_kind != "tvlp":
            return (
                "imported",
                "该来源没有生命周期事件，按“已导入”显示；"
                "“最近仍在更新”只表示日志有新数据，不代表训练进程仍然存在。",
            )
        lifecycle = connection.execute(
            """
            SELECT status, timestamp FROM training_events
            WHERE run_id = ? AND event_type = 'lifecycle'
            ORDER BY timestamp DESC, id DESC LIMIT 1
            """,
            (run_id,),
        ).fetchone()
        if lifecycle is not None and lifecycle["status"] in (
            "completed",
            "failed",
            "cancelled",
        ):
            label = _STATUS_LABELS.get(lifecycle["status"], lifecycle["status"])
            return lifecycle["status"], f"最近生命周期事件：{label}（{lifecycle['timestamp']}）。"
        heartbeat_time = connection.execute(
            "SELECT MAX(timestamp) FROM training_events WHERE run_id = ? AND event_type = 'heartbeat'",
            (run_id,),
        ).fetchone()[0]
        metric_time = connection.execute(
            "SELECT MAX(timestamp) FROM metric_points WHERE run_id = ? AND timestamp IS NOT NULL",
            (run_id,),
        ).fetchone()[0]
        if heartbeat_time is not None and self._is_recent(heartbeat_time):
            return (
                "running",
                f"最近 {STALE_AFTER_SECONDS} 秒内收到心跳（{heartbeat_time}），"
                "这是训练进程仍在工作的显式证据。",
            )
        latest_activity = max(
            [value for value in (heartbeat_time, metric_time) if value] or [None]
        )
        if metric_time is not None and self._is_recent(metric_time):
            return (
                "unknown",
                f"指标仍在更新（最后指标 {metric_time}），但没有近期心跳；"
                "有新指标不等于训练进程仍然存在，因此不标记为“运行中”。",
            )
        if latest_activity is not None:
            return (
                "unknown",
                "没有收到完成事件，且超过 "
                f"{STALE_AFTER_SECONDS} 秒没有心跳或新指标（最后活动 {latest_activity}）；"
                "日志停止不能证明训练失败。",
            )
        return "unknown", "尚未收到指标、心跳或生命周期事件。"

    def _is_recent(self, timestamp: str) -> bool:
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            return False
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return (self._now() - parsed).total_seconds() <= STALE_AFTER_SECONDS
