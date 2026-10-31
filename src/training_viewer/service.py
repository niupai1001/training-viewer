"""应用服务层：协调目录扫描、增量索引、状态刷新与实时通知。

FastAPI 路由只调用这里，不直接操作文件或 SQL；后台轮询线程也调用同一个
synchronize()，因此手动刷新和自动刷新不会互相覆盖。
"""
from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from .application_paths import ApplicationPaths
from .discovery.run_directory_scanner import RunDirectoryScanner
from .indexing.database import IndexDatabase
from .indexing.index_queries import IndexQueries
from .indexing.training_metric_indexer import TrainingMetricIndexer
from .log_readers.base import ParseIssue
from .source_adapters.base import SourceAdapterRegistry
from .source_adapters.builtin_adapters import build_builtin_source_adapter_registry

LOGGER = logging.getLogger("training_viewer.service")


class TrainingViewerService:
    """Training Viewer 的本机服务核心。"""

    def __init__(
        self,
        paths: ApplicationPaths,
        now=None,
        scan_interval_seconds: float = 2.0,
        source_adapter_registry: SourceAdapterRegistry | None = None,
    ):
        self.paths = paths
        self.database = IndexDatabase(paths.database_file)
        self.database.initialize()
        self.registry = source_adapter_registry or build_builtin_source_adapter_registry()
        self.scanner = RunDirectoryScanner(self.registry)
        self.indexer = TrainingMetricIndexer(self.database, now=now)
        self.queries = IndexQueries(self.database)
        self.scan_interval_seconds = scan_interval_seconds
        self.version = 0
        self.last_sync_at: str | None = None
        self.last_sync_error: str | None = None
        self._sync_lock = threading.Lock()
        self._watch_lock = threading.RLock()
        self._subscribers: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []
        self._watcher = None
        self._last_scan_issue_signature: tuple | None = None
        self._last_conflict_signature: tuple | None = None

    # ------------------------------------------------------------------ 根目录
    def list_roots(self) -> list[dict]:
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT id, path, added_at FROM watched_roots ORDER BY id ASC"
            ).fetchall()
        return [dict(row) for row in rows]

    def add_root(self, path: str) -> dict:
        raw_path = Path(path).expanduser()
        if not raw_path.exists():
            raise ValueError(f"目录不存在：{raw_path}")
        if not raw_path.is_dir():
            raise ValueError(f"路径不是目录：{raw_path}")
        resolved = raw_path.resolve()
        with self.database.connection() as connection:
            existing = connection.execute(
                "SELECT id, path, added_at FROM watched_roots WHERE path = ?",
                (str(resolved),),
            ).fetchone()
            if existing is not None:
                return dict(existing)
        with self.database.transaction() as connection:
            cursor = connection.execute(
                "INSERT INTO watched_roots (path, added_at) VALUES (?, ?)",
                (str(resolved), datetime.now(timezone.utc).isoformat()),
            )
            root_id = cursor.lastrowid
        LOGGER.info("已添加扫描根目录 %s", resolved)
        self.synchronize()
        self._refresh_watch_roots()
        return {"id": root_id, "path": str(resolved), "added_at": datetime.now(timezone.utc).isoformat()}

    def remove_root(self, root_id: int) -> bool:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT path FROM watched_roots WHERE id = ?", (root_id,)
            ).fetchone()
        if row is None:
            return False
        with self.database.transaction() as connection:
            connection.execute("DELETE FROM watched_roots WHERE id = ?", (root_id,))
            connection.execute("DELETE FROM runs WHERE root_path = ?", (row["path"],))
            connection.execute("DELETE FROM run_conflicts")
        LOGGER.info("已移除扫描根目录 %s（原始文件未删除）", row["path"])
        self._publish({"version": self.version, "removed_root": root_id, "changed_runs": []})
        self.synchronize()
        self._refresh_watch_roots()
        return True

    # ------------------------------------------------------------------ 同步
    def synchronize(self) -> dict:
        with self._sync_lock:
            roots = self.list_roots()
            changed_runs: set[str] = set()
            scan_issues: list[ParseIssue] = []
            discovered_runs = []
            discovered_directories: set[str] = set()
            seen_run_ids: dict[str, str] = {}
            conflicts: list[dict] = []
            try:
                for root in roots:
                    root_path = Path(root["path"])
                    root_result = self.scanner.scan(root_path)
                    for issue in root_result.issues:
                        scan_issues.append(
                            ParseIssue(issue.path, 0, issue.message, _severity(issue.severity))
                        )
                    for discovered in root_result.runs:
                        run_directory = str(discovered.run_directory)
                        if run_directory in discovered_directories:
                            continue
                        discovered_directories.add(run_directory)
                        if discovered.run_id in seen_run_ids:
                            conflicts.append(
                                {
                                    "run_id": discovered.run_id,
                                    "kept_run_dir": seen_run_ids[discovered.run_id],
                                    "conflicting_run_dir": run_directory,
                                }
                            )
                            continue
                        seen_run_ids[discovered.run_id] = run_directory
                        discovered_runs.append((discovered, root_path))

                for discovered, root_path in discovered_runs:
                    try:
                        report = self.indexer.ingest(discovered, root_path)
                    except Exception as error:  # noqa: BLE001 - 单个 Run 失败不影响其它 Run
                        LOGGER.exception("索引运行失败：%s", discovered.run_directory)
                        scan_issues.append(
                            ParseIssue(
                                str(discovered.run_directory),
                                0,
                                f"索引运行失败，已跳过本次导入：{error}",
                            )
                        )
                        continue
                    for issue in report.issues:
                        scan_issues.append(issue)
                    if report.changed:
                        changed_runs.add(report.run_id)

                self._mark_missing_directories(discovered_directories, changed_runs)
                changed_runs.update(self.indexer.refresh_statuses())
                self._replace_conflicts(conflicts)
                self.indexer.replace_scan_issues(scan_issues)
                issue_signature = tuple(
                    sorted(
                        (issue.file_path, issue.line_number, issue.message)
                        for issue in scan_issues
                    )
                )
                conflict_signature = tuple(
                    sorted(
                        (
                            conflict["run_id"],
                            conflict["kept_run_dir"],
                            conflict["conflicting_run_dir"],
                        )
                        for conflict in conflicts
                    )
                )
                diagnostics_changed = (
                    issue_signature != self._last_scan_issue_signature
                    or conflict_signature != self._last_conflict_signature
                )
                self._last_scan_issue_signature = issue_signature
                self._last_conflict_signature = conflict_signature
                self.version += 1
                self.last_sync_at = datetime.now(timezone.utc).isoformat()
                self.last_sync_error = None
                if changed_runs or diagnostics_changed or self.version == 1:
                    self._publish(
                        {
                            "version": self.version,
                            "changed_runs": sorted(changed_runs),
                            "run_count": len(discovered_runs),
                            "diagnostics_changed": diagnostics_changed,
                        }
                    )
                return {
                    "version": self.version,
                    "changed_runs": sorted(changed_runs),
                    "run_count": len(discovered_runs),
                    "issue_count": len(scan_issues),
                }
            except Exception as error:  # noqa: BLE001 - 后台线程必须保持存活
                self.last_sync_error = str(error)
                LOGGER.exception("同步失败")
                raise

    def _mark_missing_directories(
        self, discovered_directories: set[str], changed_runs: set[str]
    ) -> None:
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT run_id, run_dir, directory_available FROM runs"
            ).fetchall()
        for row in rows:
            if row["run_dir"] in discovered_directories:
                continue
            if not row["directory_available"]:
                continue
            if self.indexer.mark_directory_unavailable(row["run_id"]):
                changed_runs.add(row["run_id"])

    def _replace_conflicts(self, conflicts: list[dict]) -> None:
        with self.database.transaction() as connection:
            connection.execute("DELETE FROM run_conflicts")
            for conflict in conflicts:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO run_conflicts
                        (run_id, kept_run_dir, conflicting_run_dir, detected_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        conflict["run_id"],
                        conflict["kept_run_dir"],
                        conflict["conflicting_run_dir"],
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )

    # ------------------------------------------------------------------ 实时通知
    def subscribe(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue) -> None:
        with self._watch_lock:
            self._subscribers.append((loop, queue))

    def unsubscribe(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue) -> None:
        with self._watch_lock:
            try:
                self._subscribers.remove((loop, queue))
            except ValueError:
                pass

    def _publish(self, payload: dict) -> None:
        with self._watch_lock:
            subscribers = list(self._subscribers)
        for loop, queue in subscribers:
            try:
                loop.call_soon_threadsafe(self._enqueue, queue, payload)
            except RuntimeError:
                self.unsubscribe(loop, queue)

    @staticmethod
    def _enqueue(queue: asyncio.Queue, payload: dict) -> None:
        if queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            pass

    def health(self) -> dict:
        return {
            "status": "ok",
            "application": "training-viewer",
            "version": self.version,
            "last_sync_at": self.last_sync_at,
            "last_sync_error": self.last_sync_error,
            "data_dir": str(self.paths.data_dir),
        }

    # ------------------------------------------------------------------ 后台监听
    def start_background_sync(self) -> None:
        from .watch.log_update_watcher import LogUpdateWatcher

        if self._watcher is None:
            self._watcher = LogUpdateWatcher(self, interval_seconds=self.scan_interval_seconds)
        self._watcher.start()

    def stop_background_sync(self) -> None:
        if self._watcher is not None:
            self._watcher.stop()
            self._watcher = None

    def _refresh_watch_roots(self) -> None:
        if self._watcher is not None:
            self._watcher.refresh_watches()

    def request_sync(self) -> None:
        if self._watcher is not None:
            self._watcher.wake_up()


def _severity(value: str):
    return "warning" if value == "warning" else "error"
