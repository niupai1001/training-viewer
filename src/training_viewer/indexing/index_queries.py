"""索引查询：运行列表、指标曲线、多运行对比、诊断信息。

所有“最佳/最终”统计都直接使用原始采样点；降采样只影响返回给图表的点，
不会改变最佳值，也不会在不同运行之间插值。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..indexing.database import IndexDatabase
from ..log_readers.base import epoch_seconds_from_iso, format_timestamp

VALID_AXES = ("global_step", "epoch", "timestamp")
AXIS_REQUESTS = (*VALID_AXES, "auto")
STATUS_LABELS = {
    "running": "运行中",
    "completed": "已完成",
    "failed": "失败",
    "cancelled": "已取消",
    "unknown": "状态未知（可能中断）",
    "imported": "已导入（无生命周期事件）",
}
ACTIVITY_LABELS = {
    "updating": "最近仍在更新",
    "idle": "已停止更新",
    "finished": "已结束",
    "unknown": "活动未知",
}
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


def _definition_for(metadata: dict, phase: str, metric_name: str) -> tuple[str | None, dict]:
    definitions = metadata.get("metric_definitions") or {}
    for key in (f"{phase}/{metric_name}", metric_name):
        if isinstance(definitions.get(key), dict):
            return key, definitions[key]
    return None, {}


def _relative_source_path(run_directory: str, file_path: str) -> str:
    try:
        return Path(file_path).resolve().relative_to(Path(run_directory).resolve()).as_posix()
    except (ValueError, OSError):
        return file_path


class IndexQueries:
    """查询索引数据库，输出与前端/导出器约定的字典结构。"""

    def __init__(self, database: IndexDatabase, now=None):
        self.database = database
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._series_cache: dict[tuple, dict] = {}
        self._metric_keys_cache: dict[str, list[dict]] = {}

    def invalidate_series_cache(self) -> None:
        self._series_cache.clear()
        self._metric_keys_cache.clear()

    # ------------------------------------------------------------------ 运行目录树
    def projects(self) -> dict:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT project, experiment, COUNT(*) AS run_count,
                       MAX(last_updated_at) AS last_updated_at,
                       SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) AS running_count
                FROM runs GROUP BY project, experiment
                ORDER BY project ASC, experiment ASC
                """
            ).fetchall()
            roots = connection.execute(
                "SELECT id, path, added_at FROM user_state.watched_roots ORDER BY id ASC"
            ).fetchall()
        projects: dict[str, dict] = {}
        for row in rows:
            project = projects.setdefault(
                row["project"],
                {"name": row["project"], "run_count": 0, "running_count": 0, "experiments": []},
            )
            project["run_count"] += row["run_count"]
            project["running_count"] += row["running_count"] or 0
            project["experiments"].append(
                {
                    "name": row["experiment"],
                    "run_count": row["run_count"],
                    "running_count": row["running_count"] or 0,
                    "last_updated_at": row["last_updated_at"],
                }
            )
        return {
            "projects": list(projects.values()),
            "roots": [dict(root) for root in roots],
        }

    # ------------------------------------------------------------------ 运行列表
    def list_runs(
        self,
        project: str | None = None,
        experiment: str | None = None,
        status: str | None = None,
        query: str | None = None,
        tag: str | None = None,
        task: str | None = None,
        model: str | None = None,
        dataset: str | None = None,
        favorite: bool | None = None,
        sort: str = "-last_updated_at",
        limit: int = 200,
        offset: int = 0,
    ) -> dict:
        limit = max(1, min(int(limit), 5000))
        offset = max(0, int(offset))
        conditions: list[str] = []
        parameters: list[Any] = []
        if project:
            conditions.append("r.project = ?")
            parameters.append(project)
        if experiment:
            conditions.append("r.experiment = ?")
            parameters.append(experiment)
        if status:
            conditions.append("r.status = ?")
            parameters.append(status)
        if task:
            conditions.append("r.task = ?")
            parameters.append(task)
        if model:
            conditions.append("r.model_name = ?")
            parameters.append(model)
        if dataset:
            conditions.append("r.dataset_name = ?")
            parameters.append(dataset)
        if favorite is not None:
            conditions.append("COALESCE(a.favorite, 0) = ?")
            parameters.append(1 if favorite else 0)
        if query:
            like = f"%{query}%"
            conditions.append(
                "(r.name LIKE ? OR r.run_id LIKE ? OR r.project LIKE ? OR r.experiment LIKE ? "
                "OR r.model_name LIKE ? OR r.dataset_name LIKE ?)"
            )
            parameters.extend([like] * 6)
        if tag:
            conditions.append(
                "EXISTS (SELECT 1 FROM json_each(r.tags_json) WHERE json_each.value = ?)"
            )
            parameters.append(tag)
        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        order_clause = self._order_clause(sort)

        with self.database.connection() as connection:
            total = connection.execute(
                f"""
                SELECT COUNT(*) FROM runs r
                LEFT JOIN user_state.run_annotations a ON a.run_id = r.run_id
                {where_clause}
                """,
                parameters,
            ).fetchone()[0]
            rows = connection.execute(
                f"""
                SELECT r.*, COALESCE(a.note, '') AS note,
                       COALESCE(a.favorite, 0) AS favorite,
                       c.conflicting_run_dir AS conflicting_run_dir
                FROM runs r
                LEFT JOIN user_state.run_annotations a ON a.run_id = r.run_id
                LEFT JOIN run_conflicts c ON c.run_id = r.run_id
                {where_clause}
                ORDER BY {order_clause}
                LIMIT ? OFFSET ?
                """,
                [*parameters, limit, offset],
            ).fetchall()
            run_ids = [row["run_id"] for row in rows]
            time_ranges = self._time_ranges(connection, run_ids)
            artifact_counts = self._count_map(connection, "artifacts", run_ids)
            issue_counts = self._count_map(connection, "ingestion_issues", run_ids)
            runs = [
                self._run_summary(
                    connection,
                    row,
                    time_ranges.get(row["run_id"], {}),
                    artifact_counts.get(row["run_id"], 0),
                    issue_counts.get(row["run_id"], 0),
                )
                for row in rows
            ]
        return {"runs": runs, "total": total, "limit": limit, "offset": offset}

    def _order_clause(self, sort: str) -> str:
        descending = sort.startswith("-")
        field = sort[1:] if descending else sort
        columns = {
            "last_updated_at": "r.last_updated_at",
            "created_at": "r.created_at",
            "name": "r.name",
            "project": "r.project",
            "status": "r.status",
            "run_id": "r.run_id",
        }
        column = columns.get(field, "r.last_updated_at")
        direction = "DESC" if descending else "ASC"
        return f"{column} {direction} NULLS LAST"

    def _time_ranges(self, connection, run_ids: list[str]) -> dict[str, dict]:
        if not run_ids:
            return {}
        placeholders = ",".join("?" for _ in run_ids)
        rows = connection.execute(
            f"""
            SELECT run_id, MIN(timestamp) AS started_at, MAX(timestamp) AS last_metric_at
            FROM metric_points WHERE run_id IN ({placeholders}) AND timestamp IS NOT NULL
            GROUP BY run_id
            """,
            run_ids,
        ).fetchall()
        ranges = {}
        for row in rows:
            duration = None
            if row["started_at"] and row["last_metric_at"]:
                duration = max(
                    0.0,
                    epoch_seconds_from_iso(row["last_metric_at"])
                    - epoch_seconds_from_iso(row["started_at"]),
                )
            ranges[row["run_id"]] = {
                "started_at": row["started_at"],
                "last_metric_at": row["last_metric_at"],
                "duration_seconds": duration,
            }
        return ranges

    def _count_map(self, connection, table: str, run_ids: list[str]) -> dict[str, int]:
        if not run_ids:
            return {}
        placeholders = ",".join("?" for _ in run_ids)
        rows = connection.execute(
            f"SELECT run_id, COUNT(*) AS count FROM {table} "
            f"WHERE run_id IN ({placeholders}) GROUP BY run_id",
            run_ids,
        ).fetchall()
        return {row["run_id"]: row["count"] for row in rows}

    def _run_summary(
        self,
        connection,
        row,
        time_range: dict,
        artifact_count: int,
        issue_count: int,
    ) -> dict:
        metadata = json.loads(row["metadata_json"])
        primary_metric = self._primary_metric(connection, row["run_id"], metadata)
        activity = self._activity_for(row["status"], time_range.get("last_metric_at"))
        return {
            "run_id": row["run_id"],
            "name": row["name"],
            "project": row["project"],
            "experiment": row["experiment"],
            "task": row["task"],
            "status": row["status"],
            "status_label": STATUS_LABELS.get(row["status"], row["status"]),
            "status_reason": row["status_reason"],
            "activity": activity,
            "activity_label": ACTIVITY_LABELS.get(activity, activity),
            "created_at": row["created_at"],
            "last_updated_at": row["last_updated_at"],
            "started_at": time_range.get("started_at"),
            "last_metric_at": time_range.get("last_metric_at"),
            "duration_seconds": time_range.get("duration_seconds"),
            "model": metadata.get("model"),
            "dataset": metadata.get("dataset"),
            "tags": metadata.get("tags", []),
            "seed": (metadata.get("source") or {}).get("seed"),
            "source_kind": row["source_kind"],
            "adapter_id": row["adapter_id"],
            "run_directory": row["run_dir"],
            "root_path": row["root_path"],
            "metadata_synthetic": bool(row["metadata_synthetic"]),
            "directory_available": bool(row["directory_available"]),
            "note": row["note"],
            "favorite": bool(row["favorite"]),
            "artifact_count": artifact_count,
            "issue_count": issue_count,
            "conflict": (
                {"conflicting_run_dir": row["conflicting_run_dir"]}
                if row["conflicting_run_dir"]
                else None
            ),
            "primary_metric": primary_metric,
        }

    def _primary_metric(self, connection, run_id: str, metadata: dict) -> dict | None:
        groups = connection.execute(
            """
            SELECT phase, metric_name, COUNT(*) AS point_count
            FROM metric_points WHERE run_id = ?
            GROUP BY phase, metric_name
            """,
            (run_id,),
        ).fetchall()
        if not groups:
            return None
        definitions = metadata.get("metric_definitions") or {}
        definition_order = {
            key: index for index, key in enumerate(definitions.keys())
        }
        classified: list[tuple[int, int, str, str, dict]] = []
        for group in groups:
            definition_key, definition = _definition_for(
                metadata, group["phase"], group["metric_name"]
            )
            direction = definition.get("direction")
            if direction in ("min", "max"):
                preference = (
                    0
                    if group["phase"].lower() in ("val", "valid", "validation", "test", "eval")
                    else 1
                )
                classified.append(
                    (
                        preference,
                        definition_order.get(
                            definition_key or "", len(definition_order)
                        ),
                        group["phase"],
                        group["metric_name"],
                        definition,
                    )
                )
        if classified:
            classified.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
            _, _, phase, metric_name, definition = classified[0]
        else:
            latest = connection.execute(
                """
                SELECT phase, metric_name FROM metric_points
                WHERE run_id = ? ORDER BY id DESC LIMIT 1
                """,
                (run_id,),
            ).fetchone()
            phase, metric_name = latest["phase"], latest["metric_name"]
            _, definition = _definition_for(metadata, phase, metric_name)
        best = self._best_point(connection, run_id, phase, metric_name, definition)
        last = self._last_point(connection, run_id, phase, metric_name)
        return {
            "key": f"{phase}/{metric_name}",
            "phase": phase,
            "metric_name": metric_name,
            "display_name": definition.get("display_name") or metric_name,
            "unit": definition.get("unit"),
            "direction": definition.get("direction"),
            "definition": definition.get("definition"),
            "best": best,
            "last": last,
        }

    def _best_point(self, connection, run_id: str, phase: str, metric_name: str, definition: dict):
        direction = definition.get("direction")
        if direction not in ("min", "max"):
            return None
        order = "ASC" if direction == "min" else "DESC"
        row = connection.execute(
            f"""
            SELECT value, global_step, epoch, timestamp FROM metric_points
            WHERE run_id = ? AND phase = ? AND metric_name = ?
            ORDER BY value {order}, timestamp IS NULL, timestamp DESC, id DESC
            LIMIT 1
            """,
            (run_id, phase, metric_name),
        ).fetchone()
        return dict(row) if row is not None else None

    def _last_point(self, connection, run_id: str, phase: str, metric_name: str):
        row = connection.execute(
            """
            SELECT value, global_step, epoch, timestamp FROM metric_points
            WHERE run_id = ? AND phase = ? AND metric_name = ?
            ORDER BY timestamp IS NULL, timestamp DESC, id DESC LIMIT 1
            """,
            (run_id, phase, metric_name),
        ).fetchone()
        return dict(row) if row is not None else None

    # ------------------------------------------------------------------ 单运行详情
    def get_run(self, run_id: str) -> dict | None:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT r.*, COALESCE(a.note, '') AS note, COALESCE(a.favorite, 0) AS favorite,
                       c.conflicting_run_dir AS conflicting_run_dir
                FROM runs r
                LEFT JOIN user_state.run_annotations a ON a.run_id = r.run_id
                LEFT JOIN run_conflicts c ON c.run_id = r.run_id
                WHERE r.run_id = ?
                """,
                (run_id,),
            ).fetchone()
            if row is None:
                return None
            counts = connection.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM metric_points WHERE run_id = ?) AS metric_point_count,
                    (SELECT COUNT(*) FROM artifacts WHERE run_id = ?) AS artifact_count,
                    (SELECT COUNT(*) FROM artifacts WHERE run_id = ? AND exists_on_disk = 0)
                        AS missing_artifact_count,
                    (SELECT COUNT(*) FROM training_events WHERE run_id = ?) AS event_count,
                    (SELECT COUNT(*) FROM ingestion_issues WHERE run_id = ?) AS issue_count
                """,
                (run_id, run_id, run_id, run_id, run_id),
            ).fetchone()
            issues = connection.execute(
                """
                SELECT file_path, line_number, message, severity, created_at
                FROM ingestion_issues WHERE run_id = ? ORDER BY id DESC LIMIT 200
                """,
                (run_id,),
            ).fetchall()
            sessions = self._sessions(connection, run_id)
            metric_keys = self._metric_keys_cached(
                connection, run_id, json.loads(row["metadata_json"])
            )
            artifact_tags = connection.execute(
                """
                SELECT tag, artifact_type, COUNT(*) AS count
                FROM artifacts WHERE run_id = ? GROUP BY tag, artifact_type ORDER BY tag
                """,
                (run_id,),
            ).fetchall()
            cursors = connection.execute(
                "SELECT * FROM ingestion_cursors WHERE run_id = ? ORDER BY file_path",
                (run_id,),
            ).fetchall()
            step_warnings = self._step_regressions(connection, run_id)
            time_range = self._time_ranges(connection, [run_id]).get(run_id, {})
        metadata = json.loads(row["metadata_json"])
        warnings = self._run_warnings(
            row, metadata, counts, issues, metric_keys, step_warnings
        )
        activity = self._activity_for(row["status"], time_range.get("last_metric_at"))
        return {
            "run_id": row["run_id"],
            "name": row["name"],
            "project": row["project"],
            "experiment": row["experiment"],
            "task": row["task"],
            "status": row["status"],
            "status_label": STATUS_LABELS.get(row["status"], row["status"]),
            "status_reason": row["status_reason"],
            "activity": activity,
            "activity_label": ACTIVITY_LABELS.get(activity, activity),
            "created_at": row["created_at"],
            "last_updated_at": row["last_updated_at"],
            "started_at": time_range.get("started_at"),
            "last_metric_at": time_range.get("last_metric_at"),
            "duration_seconds": time_range.get("duration_seconds"),
            "source_kind": row["source_kind"],
            "adapter_id": row["adapter_id"],
            "run_directory": row["run_dir"],
            "root_path": row["root_path"],
            "metadata_synthetic": bool(row["metadata_synthetic"]),
            "directory_available": bool(row["directory_available"]),
            "metadata": metadata,
            "schema_version": metadata.get("schema_version"),
            "model": metadata.get("model"),
            "dataset": metadata.get("dataset"),
            "config": metadata.get("config") or {},
            "source": metadata.get("source") or {},
            "tags": metadata.get("tags") or [],
            "metric_definitions": metadata.get("metric_definitions") or {},
            "extensions": metadata.get("extensions") or {},
            "note": row["note"],
            "favorite": bool(row["favorite"]),
            "conflict": (
                {"conflicting_run_dir": row["conflicting_run_dir"]}
                if row["conflicting_run_dir"]
                else None
            ),
            "counts": dict(counts),
            "sessions": sessions,
            "metric_keys": metric_keys,
            "artifact_tags": [dict(tag) for tag in artifact_tags],
            "data_sources": [
                {
                    "file_path": cursor["file_path"],
                    "relative_path": _relative_source_path(row["run_dir"], cursor["file_path"]),
                    "file_kind": cursor["file_kind"],
                    "offset": cursor["offset"],
                    "size": cursor["size"],
                    "updated_at": cursor["updated_at"],
                    "health": cursor["health"],
                }
                for cursor in cursors
            ],
            "issues": [dict(issue) for issue in issues],
            "step_warnings": step_warnings,
            "warnings": warnings,
        }

    def _sessions(self, connection, run_id: str) -> list[dict]:
        rows = connection.execute(
            """
            SELECT session_id, MIN(timestamp) AS first_seen, MAX(timestamp) AS last_seen,
                   COUNT(*) AS point_count
            FROM metric_points WHERE run_id = ?
            GROUP BY session_id ORDER BY first_seen ASC
            """,
            (run_id,),
        ).fetchall()
        sessions = {row["session_id"]: dict(row) for row in rows}
        event_rows = connection.execute(
            """
            SELECT session_id, MIN(timestamp) AS first_seen, MAX(timestamp) AS last_seen,
                   COUNT(*) AS event_count
            FROM training_events WHERE run_id = ?
            GROUP BY session_id ORDER BY first_seen ASC
            """,
            (run_id,),
        ).fetchall()
        for event_row in event_rows:
            session_id = event_row["session_id"]
            if session_id in sessions:
                sessions[session_id]["event_count"] = event_row["event_count"]
            else:
                sessions[session_id] = {
                    "session_id": session_id,
                    "first_seen": event_row["first_seen"],
                    "last_seen": event_row["last_seen"],
                    "point_count": 0,
                    "event_count": event_row["event_count"],
                }
        return sorted(sessions.values(), key=lambda item: item["first_seen"] or "")

    def metric_keys(self, run_id: str) -> list[dict] | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT metadata_json FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is None:
                return None
            return self._metric_keys_cached(
                connection, run_id, json.loads(row["metadata_json"])
            )

    def _metric_keys_cached(self, connection, run_id: str, metadata: dict) -> list[dict]:
        cached = self._metric_keys_cache.get(run_id)
        if cached is not None:
            return cached
        keys = self._metric_keys(connection, run_id, metadata)
        self._metric_keys_cache[run_id] = keys
        return keys

    def _metric_keys(self, connection, run_id: str, metadata: dict) -> list[dict]:
        rows = connection.execute(
            """
            SELECT phase, metric_name, COUNT(*) AS point_count,
                   MIN(value) AS min_value, MAX(value) AS max_value,
                   MIN(timestamp) AS first_timestamp, MAX(timestamp) AS last_timestamp,
                   SUM(CASE WHEN global_step IS NOT NULL THEN 1 ELSE 0 END) AS step_point_count,
                   SUM(CASE WHEN epoch IS NOT NULL THEN 1 ELSE 0 END) AS epoch_point_count,
                   SUM(CASE WHEN timestamp IS NOT NULL THEN 1 ELSE 0 END) AS time_point_count,
                   COUNT(DISTINCT session_id) AS session_count
            FROM metric_points WHERE run_id = ?
            GROUP BY phase, metric_name ORDER BY phase ASC, metric_name ASC
            """,
            (run_id,),
        ).fetchall()
        result = []
        for row in rows:
            definition_key, definition = _definition_for(
                metadata, row["phase"], row["metric_name"]
            )
            best = self._best_point(
                connection, run_id, row["phase"], row["metric_name"], definition
            )
            last = self._last_point(connection, run_id, row["phase"], row["metric_name"])
            result.append(
                {
                    "key": f"{row['phase']}/{row['metric_name']}",
                    "phase": row["phase"],
                    "metric_name": row["metric_name"],
                    "display_name": definition.get("display_name") or row["metric_name"],
                    "definition_key": definition_key,
                    "unit": definition.get("unit"),
                    "direction": definition.get("direction"),
                    "aggregation": definition.get("aggregation"),
                    "definition": definition.get("definition"),
                    "comparison_key": definition.get("comparison_key"),
                    "point_count": row["point_count"],
                    "min_value": row["min_value"],
                    "max_value": row["max_value"],
                    "first_timestamp": row["first_timestamp"],
                    "last_timestamp": row["last_timestamp"],
                    "step_point_count": row["step_point_count"] or 0,
                    "epoch_point_count": row["epoch_point_count"] or 0,
                    "time_point_count": row["time_point_count"] or 0,
                    "session_count": row["session_count"] or 0,
                    "best": best,
                    "last": last,
                }
            )
        return result

    def _step_regressions(self, connection, run_id: str) -> list[dict]:
        rows = connection.execute(
            """
            WITH ordered AS (
                SELECT session_id, global_step, timestamp,
                       LAG(global_step) OVER (
                           PARTITION BY session_id ORDER BY timestamp, id
                       ) AS previous_step
                FROM metric_points
                WHERE run_id = ? AND global_step IS NOT NULL
            )
            SELECT session_id, previous_step, global_step, timestamp
            FROM ordered WHERE global_step < previous_step
            ORDER BY timestamp DESC LIMIT 5
            """,
            (run_id,),
        ).fetchall()
        return [
            {
                "session_id": row["session_id"],
                "previous_step": row["previous_step"],
                "global_step": row["global_step"],
                "timestamp": row["timestamp"],
                "message": (
                    f"同一执行会话内 global_step 从 {row['previous_step']} 回退到 "
                    f"{row['global_step']}；曲线按会话分段显示，不会把两段合并。"
                ),
            }
            for row in rows
        ]

    def _run_warnings(
        self, row, metadata: dict, counts, issues, metric_keys: list[dict], step_warnings: list[dict]
    ) -> list[dict]:
        warnings: list[dict] = []
        if not row["directory_available"]:
            warnings.append(
                {
                    "code": "directory_unavailable",
                    "severity": "error",
                    "message": "运行目录当前不可访问；已保留索引，不会删除原始数据。",
                }
            )
        if row["metadata_synthetic"]:
            warnings.append(
                {
                    "code": "synthetic_metadata",
                    "severity": "info",
                    "message": "该来源没有 run.json，项目与运行名称由目录推导；指标数据本身未被修改。",
                }
            )
        if row["conflicting_run_dir"]:
            warnings.append(
                {
                    "code": "run_id_conflict",
                    "severity": "warning",
                    "message": (
                        "检测到相同 run_id 的另一个运行目录："
                        f"{row['conflicting_run_dir']}。当前显示的是 {row['run_dir']}，"
                        "请检查并修正重复的 run_id。"
                    ),
                }
            )
        if counts["missing_artifact_count"]:
            warnings.append(
                {
                    "code": "missing_artifacts",
                    "severity": "warning",
                    "message": f"{counts['missing_artifact_count']} 个产物文件当前不存在。",
                }
            )
        if issues:
            warnings.append(
                {
                    "code": "log_issues",
                    "severity": "warning",
                    "message": f"日志中有 {len(issues)} 条解析或校验问题，详情见“诊断”页。",
                }
            )
        undefined = [
            item
            for item in metric_keys
            if not item.get("direction") or item.get("direction") == "none"
        ]
        if undefined:
            warnings.append(
                {
                    "code": "metric_definition_gap",
                    "severity": "info",
                    "message": (
                        f"{len(undefined)} 个指标没有 min/max 方向定义，可以绘制但不能自动评优。"
                    ),
                }
            )
        for warning in step_warnings:
            warnings.append(
                {
                    "code": "step_regression",
                    "severity": "warning",
                    "message": warning["message"],
                }
            )
        if row["status"] == "unknown":
            warnings.append(
                {
                    "code": "stale_status",
                    "severity": "info",
                    "message": row["status_reason"],
                }
            )
        return warnings

    # ------------------------------------------------------------------ 指标曲线
    def query_series(
        self,
        run_id: str,
        series_keys: list[str],
        axis: str = "auto",
        max_points: int = 2000,
        x_min: float | None = None,
        x_max: float | None = None,
    ) -> dict:
        if axis not in AXIS_REQUESTS:
            raise ValueError(f"不支持的横轴：{axis}")
        if x_min is not None and x_max is not None and x_min > x_max:
            raise ValueError("x_min 不能大于 x_max")
        max_points = max(10, min(int(max_points), 20000))
        with self.database.connection() as connection:
            run_row = connection.execute(
                "SELECT * FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if run_row is None:
                return {"run_id": run_id, "axis": axis, "series": [], "warnings": []}
            metadata = json.loads(run_row["metadata_json"])
            available = self._metric_keys_cached(connection, run_id, metadata)
            series = []
            warnings: list[dict] = []
            for key in series_keys:
                match = self._match_metric_key(available, key)
                if match is None:
                    warnings.append(
                        {
                            "code": "series_not_found",
                            "severity": "warning",
                            "message": f"该运行没有指标 {key}。",
                        }
                    )
                    continue
                resolved_axis = self._resolve_axis(match, axis)
                series.append(
                    self._series_payload(
                        connection,
                        run_id,
                        match,
                        resolved_axis,
                        max_points,
                        x_min,
                        x_max,
                    )
                )
            if not series and not warnings:
                warnings.append(
                    {
                        "code": "no_metrics",
                        "severity": "info",
                        "message": "该运行还没有可用指标。",
                    }
                )
        return {
            "run_id": run_id,
            "run_name": run_row["name"],
            "axis": axis,
            "series": series,
            "warnings": warnings,
        }

    @staticmethod
    def _resolve_axis(metric: dict, requested_axis: str) -> str:
        """按真实数据选择横轴；不存在 Step 时不伪造 Step。"""
        if requested_axis != "auto":
            return requested_axis
        if metric.get("step_point_count", 0) > 0:
            return "global_step"
        if metric.get("epoch_point_count", 0) > 0:
            return "epoch"
        if metric.get("time_point_count", 0) > 0:
            return "timestamp"
        return "global_step"

    def _activity_for(self, status: str, last_metric_at: str | None) -> str:
        """活动是“最近是否有新数据”的证据，不等于训练进程仍然存在。"""
        if status in TERMINAL_STATUSES:
            return "finished"
        if not last_metric_at:
            return "unknown"
        try:
            age = self._now().timestamp() - epoch_seconds_from_iso(last_metric_at)
        except ValueError:
            return "unknown"
        return "updating" if age <= 120 else "idle"

    def _match_metric_key(self, available: list[dict], key: str) -> dict | None:
        exact = [item for item in available if item["key"] == key]
        if len(exact) == 1:
            return exact[0]
        by_name = [item for item in available if item["metric_name"] == key]
        if len(by_name) == 1:
            return by_name[0]
        return None

    def _series_payload(
        self,
        connection,
        run_id: str,
        metric: dict,
        axis: str,
        max_points: int,
        x_min: float | None = None,
        x_max: float | None = None,
    ) -> dict:
        phase, metric_name = metric["phase"], metric["metric_name"]
        cache_key = (run_id, phase, metric_name, axis, max_points, x_min, x_max)
        cached = self._series_cache.get(cache_key)
        if cached is not None:
            return cached
        rows, total_points, downsampled = self._query_series_points(
            connection, run_id, phase, metric_name, axis, max_points, x_min, x_max
        )
        points = [self._point_payload(row, axis) for row in rows]
        if len(points) > max_points:
            points = self._downsample(points, max_points)
            downsampled = True
        warnings: list[dict] = []
        if not points:
            warnings.append(
                {
                    "code": "axis_unavailable",
                    "severity": "warning",
                    "message": (
                        f"指标 {metric['key']} 没有可用于"
                        f"{self._axis_label(axis)}横轴的记录。"
                    ),
                }
            )
        if metric["session_count"] > 1:
            warnings.append(
                {
                    "code": "multiple_sessions",
                    "severity": "info",
                    "message": (
                        f"该指标跨 {metric['session_count']} 个执行会话；"
                        "曲线按会话分段绘制，不合并 Step 回退。"
                    ),
                }
            )
        payload = {
            "key": metric["key"],
            "phase": phase,
            "metric_name": metric_name,
            "display_name": metric["display_name"],
            "unit": metric["unit"],
            "direction": metric["direction"],
            "definition": metric["definition"],
            "definition_key": metric["definition_key"],
            "axis": axis,
            "x_min": x_min,
            "x_max": x_max,
            "points": points,
            "total_points": total_points,
            "returned_points": len(points),
            "downsampled": downsampled,
            "best": metric["best"],
            "last": metric["last"],
            "warnings": warnings,
        }
        self._series_cache[cache_key] = payload
        if len(self._series_cache) > 512:
            self._series_cache.pop(next(iter(self._series_cache)))
        return payload

    @staticmethod
    def _range_clause(
        axis: str, x_min: float | None, x_max: float | None
    ) -> tuple[str, list]:
        clauses: list[str] = []
        params: list = []
        if axis == "timestamp":
            if x_min is not None:
                clauses.append("timestamp >= ?")
                params.append(
                    format_timestamp(datetime.fromtimestamp(x_min, tz=timezone.utc))
                )
            if x_max is not None:
                clauses.append("timestamp <= ?")
                params.append(
                    format_timestamp(datetime.fromtimestamp(x_max, tz=timezone.utc))
                )
        else:
            if x_min is not None:
                clauses.append(f"{axis} >= ?")
                params.append(x_min)
            if x_max is not None:
                clauses.append(f"{axis} <= ?")
                params.append(x_max)
        return (("AND " + " AND ".join(clauses)) if clauses else ""), params

    def _query_series_points(
        self,
        connection,
        run_id: str,
        phase: str,
        metric_name: str,
        axis: str,
        max_points: int,
        x_min: float | None = None,
        x_max: float | None = None,
    ) -> tuple[list, int, bool]:
        """优先使用物化桶；源数据不完整时回退 SQL 分桶。"""
        axis_conditions = {
            "global_step": "global_step IS NOT NULL",
            "epoch": "epoch IS NOT NULL",
            "timestamp": "timestamp IS NOT NULL",
        }[axis]
        range_sql, range_params = self._range_clause(axis, x_min, x_max)
        total = connection.execute(
            f"""
            SELECT COUNT(*) FROM metric_points
            WHERE run_id = ? AND phase = ? AND metric_name = ? AND {axis_conditions} {range_sql}
            """,
            (run_id, phase, metric_name, *range_params),
        ).fetchone()[0]
        if total <= max_points:
            rows = connection.execute(
                f"""
                SELECT value, global_step, epoch, timestamp, session_id, {axis} AS x
                FROM metric_points
                WHERE run_id = ? AND phase = ? AND metric_name = ? AND {axis_conditions} {range_sql}
                ORDER BY {axis}, timestamp, id
                """,
                (run_id, phase, metric_name, *range_params),
            ).fetchall()
            return list(rows), total, False
        rollups = connection.execute(
            """
            SELECT bucket, point_count, first_json, min_json, max_json, last_json
            FROM metric_rollups
            WHERE run_id = ? AND phase = ? AND metric_name = ? AND axis = ?
            ORDER BY bucket
            """,
            (run_id, phase, metric_name, axis),
        ).fetchall()
        if rollups and not range_params and sum(row["point_count"] for row in rollups) == total:
            points: list[dict] = []
            seen: set[tuple] = set()
            for row in rollups:
                for column in ("first_json", "min_json", "max_json", "last_json"):
                    point = json.loads(row[column])
                    key = (point["x"], point["value"], point.get("session_id"))
                    if key not in seen:
                        seen.add(key)
                        points.append(point)
            points.sort(key=lambda item: (item["x"], item["value"]))
            if len(points) > max_points:
                points = self._downsample(points, max_points)
            return points, total, len(points) < total
        bucket_count = max(1, max_points // 4)
        rows = connection.execute(
            f"""
            WITH filtered AS (
                SELECT id, value, global_step, epoch, timestamp, session_id, {axis} AS x
                FROM metric_points
                WHERE run_id = ? AND phase = ? AND metric_name = ? AND {axis_conditions} {range_sql}
            ),
            bounds AS (
                SELECT MIN(x) AS min_x, MAX(x) AS max_x FROM filtered
            ),
            scored AS (
                SELECT filtered.*,
                       CAST((x - bounds.min_x) * ? / NULLIF(bounds.max_x - bounds.min_x, 0) AS INTEGER) AS bucket
                FROM filtered CROSS JOIN bounds
            ),
            aggregates AS (
                SELECT bucket,
                       MIN(value) AS min_value,
                       MAX(value) AS max_value,
                       MIN(x) AS first_x,
                       MAX(x) AS last_x
                FROM scored
                GROUP BY bucket
            )
            SELECT DISTINCT scored.value, scored.global_step, scored.epoch,
                   scored.timestamp, scored.session_id, scored.x
            FROM scored JOIN aggregates ON scored.bucket = aggregates.bucket
            WHERE scored.value = aggregates.min_value
               OR scored.value = aggregates.max_value
               OR scored.x = aggregates.first_x
               OR scored.x = aggregates.last_x
            ORDER BY scored.x, scored.value
            """,
            (run_id, phase, metric_name, *range_params, bucket_count),
        ).fetchall()
        return list(rows), total, len(rows) < total

    @staticmethod
    def _point_payload(row, axis: str) -> dict:
        if isinstance(row, dict):
            return row
        if axis == "timestamp":
            x = epoch_seconds_from_iso(row["timestamp"]) if row["timestamp"] else None
        elif "x" in row.keys():
            x = row["x"]
        elif axis == "epoch":
            x = row["epoch"]
        else:
            x = row["global_step"]
        return {
            "x": x,
            "value": row["value"],
            "global_step": row["global_step"],
            "epoch": row["epoch"],
            "timestamp": row["timestamp"],
            "session_id": row["session_id"],
        }

    @staticmethod
    def _downsample(points: list[dict], max_points: int) -> list[dict]:
        """最小-最大分桶：比普通等距抽样更可靠地保留峰值与谷值。"""
        if len(points) <= max_points:
            return points
        bucket_count = max(1, max_points // 4)
        bucket_size = len(points) / bucket_count
        sampled: list[dict] = []
        for bucket_index in range(bucket_count):
            start = int(bucket_index * bucket_size)
            end = int((bucket_index + 1) * bucket_size)
            chunk = points[start:end]
            if not chunk:
                continue
            minimum_index = min(range(len(chunk)), key=lambda i: chunk[i]["value"])
            maximum_index = max(range(len(chunk)), key=lambda i: chunk[i]["value"])
            indexes = sorted({0, len(chunk) - 1, minimum_index, maximum_index})
            sampled.extend(chunk[index] for index in indexes)
        return sampled

    @staticmethod
    def _axis_label(axis: str) -> str:
        return {
            "global_step": "优化步（global_step）",
            "epoch": "训练轮次（epoch）",
            "timestamp": "时间",
        }.get(axis, axis)

    # ------------------------------------------------------------------ 多运行对比
    def compare(
        self,
        run_ids: list[str],
        series_keys: list[str],
        axis: str = "auto",
        max_points: int = 1500,
        x_min: float | None = None,
        x_max: float | None = None,
    ) -> dict:
        if axis not in AXIS_REQUESTS:
            raise ValueError(f"不支持的横轴：{axis}")
        if x_min is not None and x_max is not None and x_min > x_max:
            raise ValueError("x_min 不能大于 x_max")
        run_ids = list(dict.fromkeys(run_ids))
        if not run_ids:
            return {
                "axis": axis,
                "series": [],
                "runs": [],
                "hyperparameters": {"rows": []},
                "run_fields": {},
                "warnings": [{"code": "no_runs", "severity": "warning", "message": "未选择运行。"}],
            }
        max_points = max(10, min(int(max_points), 20000))
        with self.database.connection() as connection:
            run_rows = []
            for run_id in run_ids:
                row = connection.execute(
                    "SELECT * FROM runs WHERE run_id = ?", (run_id,)
                ).fetchone()
                if row is not None:
                    run_rows.append(row)
            warnings: list[dict] = []
            missing_runs = [run_id for run_id in run_ids if run_id not in {row["run_id"] for row in run_rows}]
            if missing_runs:
                warnings.append(
                    {
                        "code": "missing_runs",
                        "severity": "warning",
                        "message": f"找不到运行：{', '.join(missing_runs)}",
                    }
                )
            metric_maps = {
                row["run_id"]: self._metric_keys_cached(
                    connection, row["run_id"], json.loads(row["metadata_json"])
                )
                for row in run_rows
            }
            series_results = []
            requested = series_keys or sorted(
                {
                    metric["key"]
                    for metrics in metric_maps.values()
                    for metric in metrics
                    if metric.get("direction") in ("min", "max")
                }
            )[:1]
            for key in requested:
                series_results.append(
                    self._compare_series(
                        connection,
                        run_rows,
                        metric_maps,
                        key,
                        axis,
                        max_points,
                        x_min,
                        x_max,
                    )
                )
            hyperparameters = self._hyperparameter_comparison(run_rows)
            run_fields = self._run_field_comparison(run_rows)
        return {
            "axis": axis,
            "x_min": x_min,
            "x_max": x_max,
            "run_ids": [row["run_id"] for row in run_rows],
            "series": series_results,
            "runs": [
                {
                    "run_id": row["run_id"],
                    "name": row["name"],
                    "project": row["project"],
                    "experiment": row["experiment"],
                    "status": row["status"],
                    "status_label": STATUS_LABELS.get(row["status"], row["status"]),
                    "model": json.loads(row["metadata_json"]).get("model"),
                    "dataset": json.loads(row["metadata_json"]).get("dataset"),
                    "tags": json.loads(row["metadata_json"]).get("tags", []),
                }
                for row in run_rows
            ],
            "hyperparameters": hyperparameters,
            "run_fields": run_fields,
            "warnings": warnings,
        }

    def _compare_series(
        self,
        connection,
        run_rows,
        metric_maps: dict[str, list[dict]],
        key: str,
        axis: str,
        max_points: int,
        x_min: float | None = None,
        x_max: float | None = None,
    ) -> dict:
        matches = {
            row["run_id"]: self._match_metric_key(metric_maps[row["run_id"]], key)
            for row in run_rows
        }
        matches = {run_id: match for run_id, match in matches.items() if match is not None}
        resolved_axis = axis
        if axis == "auto":
            step_total = sum(match["step_point_count"] for match in matches.values())
            epoch_total = sum(match["epoch_point_count"] for match in matches.values())
            time_total = sum(match["time_point_count"] for match in matches.values())
            if step_total == 0 and epoch_total == 0 and time_total == 0:
                resolved_axis = "global_step"
            elif step_total >= max(epoch_total, time_total):
                resolved_axis = "global_step"
            elif epoch_total >= time_total:
                resolved_axis = "epoch"
            else:
                resolved_axis = "timestamp"
        runs = []
        warnings: list[dict] = []
        units: set[str] = set()
        definitions: set[str] = set()
        datasets: set[str] = set()
        directions: set[str | None] = set()
        tasks: set[str | None] = set()
        base_metric = None
        for row in run_rows:
            match = matches.get(row["run_id"])
            if match is None:
                warnings.append(
                    {
                        "code": "series_missing_in_run",
                        "severity": "warning",
                        "message": f"运行“{row['name']}”没有指标 {key}，不会被插值补齐。",
                    }
                )
                continue
            base_metric = base_metric or match
            payload = self._series_payload(
                connection,
                row["run_id"],
                match,
                resolved_axis,
                max_points,
                x_min,
                x_max,
            )
            if not payload["points"]:
                warnings.append(
                    {
                        "code": "axis_partial_coverage",
                        "severity": "warning",
                        "message": (
                            f"运行“{row['name']}”在{self._axis_label(resolved_axis)}横轴上没有该指标；"
                            "不会伪造或插值其它横轴的数据。"
                        ),
                    }
                )
            runs.append(
                {
                    "run_id": row["run_id"],
                    "name": row["name"],
                    "axis": resolved_axis,
                    "points": payload["points"],
                    "total_points": payload["total_points"],
                    "returned_points": payload["returned_points"],
                    "downsampled": payload["downsampled"],
                    "best": payload["best"],
                    "last": payload["last"],
                    "warnings": payload["warnings"],
                }
            )
            warnings.extend(
                {"code": item["code"], "severity": item["severity"], "message": f"运行“{row['name']}”：{item['message']}"}
                for item in payload["warnings"]
            )
            metadata = json.loads(row["metadata_json"])
            definition = _definition_for(metadata, match["phase"], match["metric_name"])[1]
            definitions.add(
                json.dumps(
                    {
                        "definition": definition.get("definition"),
                        "comparison_key": definition.get("comparison_key"),
                        "aggregation": definition.get("aggregation"),
                    },
                    sort_keys=True,
                    ensure_ascii=False,
                )
            )
            units.add(str(definition.get("unit")))
            directions.add(definition.get("direction"))
            tasks.add(metadata.get("task"))
            dataset = metadata.get("dataset") or {}
            datasets.add(
                json.dumps(
                    {
                        "name": dataset.get("name"),
                        "version": dataset.get("version"),
                        "split_definition": dataset.get("split_definition"),
                    },
                    sort_keys=True,
                    ensure_ascii=False,
                )
            )
        if len(units) > 1:
            warnings.append(
                {
                    "code": "unit_mismatch",
                    "severity": "error",
                    "message": f"指标 {key} 在各运行中的单位不同：{', '.join(sorted(units))}；不能直接比较数值。",
                }
            )
        if len(datasets) > 1:
            warnings.append(
                {
                    "code": "dataset_mismatch",
                    "severity": "error",
                    "message": f"指标 {key} 使用的数据集名称、版本或划分不同；数值不具直接可比性。",
                }
            )
        if len(definitions) > 1:
            warnings.append(
                {
                    "code": "definition_mismatch",
                    "severity": "error",
                    "message": f"指标 {key} 的定义或聚合方式不同；不能直接排名。",
                }
            )
        if len(tasks) > 1:
            warnings.append(
                {
                    "code": "task_mismatch",
                    "severity": "warning",
                    "message": (
                        f"指标 {key} 来自不同任务类型（{', '.join(sorted(str(task) for task in tasks))}）；"
                        "任务语义不同，数值不应直接比较或排名。"
                    ),
                }
            )
        if any(direction not in ("min", "max") for direction in directions):
            warnings.append(
                {
                    "code": "missing_direction",
                    "severity": "warning",
                    "message": f"指标 {key} 缺少 min/max 方向定义；可以绘制，但不能自动评优。",
                }
            )
        ranking_allowed = (
            len(runs) > 0
            and len(units) <= 1
            and len(datasets) <= 1
            and len(definitions) <= 1
            and len(tasks) <= 1
            and all(direction in ("min", "max") for direction in directions)
        )
        return {
            "key": key,
            "phase": base_metric["phase"] if base_metric else None,
            "metric_name": base_metric["metric_name"] if base_metric else key,
            "display_name": base_metric["display_name"] if base_metric else key,
            "unit": base_metric["unit"] if base_metric else None,
            "direction": base_metric["direction"] if base_metric else None,
            "definition": base_metric["definition"] if base_metric else None,
            "axis": resolved_axis,
            "runs": runs,
            "warnings": warnings,
            "ranking_allowed": ranking_allowed,
        }

    def _hyperparameter_comparison(self, run_rows) -> dict:
        values_by_run: dict[str, dict[str, Any]] = {}
        all_paths: set[str] = set()
        for row in run_rows:
            metadata = json.loads(row["metadata_json"])
            flattened = dict(_flatten_config(metadata.get("config") or {}))
            values_by_run[row["run_id"]] = flattened
            all_paths.update(flattened)
        rows = []
        for path in sorted(all_paths):
            values = {run_id: values_by_run[run_id].get(path) for run_id in values_by_run}
            distinct = {json.dumps(value, sort_keys=True, ensure_ascii=False) for value in values.values()}
            rows.append(
                {
                    "path": path,
                    "values": values,
                    "different": len(distinct) > 1,
                }
            )
        if len(rows) > 500:
            rows = rows[:500]
        return {"rows": rows}

    def _run_field_comparison(self, run_rows) -> dict:
        fields = ("project", "experiment", "task", "model", "dataset", "seed", "status")
        return {
            field: {
                row["run_id"]: (
                    (json.loads(row["metadata_json"]).get("source") or {}).get("seed")
                    if field == "seed"
                    else (
                        json.loads(row["metadata_json"]).get(field)
                        if field in ("model", "dataset")
                        else row[field]
                    )
                )
                for row in run_rows
            }
            for field in fields
        }

    # ------------------------------------------------------------------ 产物查询
    def list_artifacts(
        self,
        run_id: str,
        tag: str | None = None,
        sample_id: str | None = None,
        group_id: str | None = None,
        epoch: int | None = None,
        artifact_type: str | None = None,
    ) -> list[dict]:
        conditions = ["run_id = ?"]
        parameters: list[Any] = [run_id]
        for column, value in (
            ("tag", tag),
            ("sample_id", sample_id),
            ("group_id", group_id),
            ("artifact_type", artifact_type),
        ):
            if value is not None:
                conditions.append(f"{column} = ?")
                parameters.append(value)
        if epoch is not None:
            conditions.append("epoch = ?")
            parameters.append(epoch)
        with self.database.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT id, run_id, path, artifact_type, tag, phase, global_step, epoch,
                       group_id, sample_id, role, mime_type, metadata_json, timestamp,
                       session_id, exists_on_disk, size, mtime
                FROM artifacts WHERE {' AND '.join(conditions)}
                ORDER BY epoch IS NULL, epoch ASC, timestamp ASC, id ASC
                """,
                parameters,
            ).fetchall()
        return [self._artifact_payload(row) for row in rows]

    def get_artifact(self, artifact_id: int) -> dict | None:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT a.*, r.run_dir, r.run_id AS owner_run_id, r.name AS run_name
                FROM artifacts a JOIN runs r ON r.run_id = a.run_id
                WHERE a.id = ?
                """,
                (artifact_id,),
            ).fetchone()
        if row is None:
            return None
        payload = self._artifact_payload(row)
        payload["run_directory"] = row["run_dir"]
        payload["run_name"] = row["run_name"]
        return payload

    def artifact_groups(self, run_id: str, tag: str | None = None) -> list[dict]:
        artifacts = self.list_artifacts(run_id, tag=tag)
        groups: dict[str, dict] = {}
        for artifact in artifacts:
            group_key = artifact["group_id"] or f"artifact-{artifact['id']}"
            group = groups.setdefault(
                group_key,
                {
                    "group_id": group_key,
                    "sample_id": artifact["sample_id"],
                    "epoch": artifact["epoch"],
                    "phase": artifact["phase"],
                    "tag": artifact["tag"],
                    "roles": {},
                },
            )
            group["roles"].setdefault(artifact["role"] or "file", []).append(artifact)
        ordered = sorted(
            groups.values(),
            key=lambda group: (
                group["sample_id"] or "",
                group["epoch"] if group["epoch"] is not None else 0,
                group["group_id"],
            ),
        )
        return ordered

    @staticmethod
    def _artifact_payload(row) -> dict:
        return {
            "id": row["id"],
            "run_id": row["run_id"],
            "path": row["path"],
            "artifact_type": row["artifact_type"],
            "tag": row["tag"],
            "phase": row["phase"],
            "global_step": row["global_step"],
            "epoch": row["epoch"],
            "group_id": row["group_id"],
            "sample_id": row["sample_id"],
            "role": row["role"],
            "mime_type": row["mime_type"],
            "metadata": json.loads(row["metadata_json"] or "{}"),
            "timestamp": row["timestamp"],
            "session_id": row["session_id"],
            "exists_on_disk": bool(row["exists_on_disk"]),
            "size": row["size"],
            "content_url": f"/api/v1/artifacts/{row['id']}/content",
            "download_url": f"/api/v1/artifacts/{row['id']}/download",
        }

    # ------------------------------------------------------------------ 时间线与诊断
    def timeline(self, run_id: str) -> dict:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT event_type, status, timestamp, session_id, global_step, message
                FROM training_events WHERE run_id = ?
                ORDER BY timestamp ASC, id ASC LIMIT 5000
                """,
                (run_id,),
            ).fetchall()
            artifact_rows = connection.execute(
                """
                SELECT timestamp, session_id, global_step, epoch, tag, path, role, sample_id
                FROM artifacts WHERE run_id = ?
                ORDER BY timestamp ASC, id ASC LIMIT 5000
                """,
                (run_id,),
            ).fetchall()
        events = []
        for row in rows:
            events.append(
                {
                    "kind": row["event_type"],
                    "status": row["status"],
                    "timestamp": row["timestamp"],
                    "session_id": row["session_id"],
                    "global_step": row["global_step"],
                    "message": row["message"],
                    "epoch": None,
                    "tag": None,
                    "path": None,
                    "role": None,
                    "sample_id": None,
                }
            )
        for row in artifact_rows:
            events.append(
                {
                    "kind": "artifact",
                    "status": None,
                    "timestamp": row["timestamp"],
                    "session_id": row["session_id"],
                    "global_step": row["global_step"],
                    "message": None,
                    "epoch": row["epoch"],
                    "tag": row["tag"],
                    "path": row["path"],
                    "role": row["role"],
                    "sample_id": row["sample_id"],
                }
            )
        events.sort(key=lambda event: event["timestamp"] or "")
        return {"run_id": run_id, "events": events[:5000]}

    def facets(self) -> dict:
        with self.database.connection() as connection:
            models = [
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT model_name FROM runs WHERE model_name IS NOT NULL ORDER BY model_name"
                ).fetchall()
            ]
            datasets = [
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT dataset_name FROM runs WHERE dataset_name IS NOT NULL ORDER BY dataset_name"
                ).fetchall()
            ]
            tasks = [
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT task FROM runs WHERE task IS NOT NULL ORDER BY task"
                ).fetchall()
            ]
            tags = [
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT json_each.value FROM runs, json_each(runs.tags_json) "
                    "ORDER BY json_each.value"
                ).fetchall()
            ]
        return {"models": models, "datasets": datasets, "tasks": tasks, "tags": tags}

    def diagnostics(self) -> dict:
        with self.database.connection() as connection:
            scan_issues = connection.execute(
                """
                SELECT file_path, line_number, message, severity, created_at
                FROM ingestion_issues WHERE run_id IS NULL ORDER BY id DESC LIMIT 500
                """
            ).fetchall()
            conflicts = connection.execute(
                "SELECT * FROM run_conflicts ORDER BY detected_at DESC"
            ).fetchall()
            problem_runs = connection.execute(
                """
                SELECT r.run_id, r.name, r.status, r.status_reason,
                       (SELECT COUNT(*) FROM ingestion_issues i WHERE i.run_id = r.run_id) AS issue_count,
                       (SELECT COUNT(*) FROM artifacts a WHERE a.run_id = r.run_id AND a.exists_on_disk = 0) AS missing_artifact_count
                FROM runs r
                WHERE r.status IN ('unknown', 'failed')
                   OR r.directory_available = 0
                   OR EXISTS (SELECT 1 FROM ingestion_issues i WHERE i.run_id = r.run_id)
                ORDER BY r.last_updated_at DESC LIMIT 200
                """
            ).fetchall()
            totals = connection.execute(
                """
                SELECT COUNT(*) AS run_count,
                       SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) AS running_count,
                       SUM(CASE WHEN status = 'unknown' THEN 1 ELSE 0 END) AS unknown_count
                FROM runs
                """
            ).fetchone()
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "totals": dict(totals),
            "scan_issues": [dict(row) for row in scan_issues],
            "conflicts": [dict(row) for row in conflicts],
            "problem_runs": [dict(row) for row in problem_runs],
        }

    # ------------------------------------------------------------------ 用户界面数据
    def get_annotation(self, run_id: str) -> dict:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT note, favorite, updated_at FROM user_state.run_annotations WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return (
            dict(row)
            if row is not None
            else {"note": "", "favorite": 0, "updated_at": None}
        )

    def save_annotation(self, run_id: str, note: str | None, favorite: bool | None) -> dict:
        current = self.get_annotation(run_id)
        new_note = current["note"] if note is None else note
        new_favorite = current["favorite"] if favorite is None else int(bool(favorite))
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO user_state.run_annotations (run_id, note, favorite, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    note = excluded.note,
                    favorite = excluded.favorite,
                    updated_at = excluded.updated_at
                """,
                (run_id, new_note, new_favorite, datetime.now(timezone.utc).isoformat()),
            )
        return {"note": new_note, "favorite": bool(new_favorite)}

    def source_inventory(self) -> list[dict]:
        """来源清单：每个原始文件一行，说明它归入哪个逻辑 Run。"""
        with self.database.connection() as connection:
            runs = connection.execute(
                """
                SELECT run_id, name, project, run_dir, source_kind, metadata_json
                FROM runs ORDER BY project, name, run_id
                """
            ).fetchall()
            rows = []
            for run in runs:
                metadata = json.loads(run["metadata_json"])
                extensions = metadata.get("extensions") or {}
                point_count = connection.execute(
                    "SELECT COUNT(*) FROM metric_points WHERE run_id = ?", (run["run_id"],)
                ).fetchone()[0]
                cursors = connection.execute(
                    "SELECT file_path, file_kind, offset, size, mtime FROM ingestion_cursors WHERE run_id = ? ORDER BY file_path",
                    (run["run_id"],),
                ).fetchall()
                merged = extensions.get("merged_source_run_ids") or []
                confidence = (
                    extensions.get("merge_confidence")
                    or extensions.get("confidence")
                    or ("canonical" if run["source_kind"] == "tvlp" else "synthetic")
                )
                if not cursors:
                    rows.append(
                        {
                            "source_path": None,
                            "parser": run["source_kind"],
                            "run_id": run["run_id"],
                            "raw_run_identifier": extensions.get("source_run_id", run["run_id"]),
                            "logical_run_id": run["run_id"],
                            "merged": bool(merged),
                            "confidence": confidence,
                            "project": run["project"],
                            "name": run["name"],
                            "point_count": point_count,
                        }
                    )
                    continue
                for cursor in cursors:
                    rows.append(
                        {
                            "source_path": cursor["file_path"],
                            "parser": cursor["file_kind"],
                            "run_id": run["run_id"],
                            "raw_run_identifier": extensions.get("source_run_id", run["run_id"]),
                            "logical_run_id": run["run_id"],
                            "merged": bool(merged),
                            "confidence": confidence,
                            "project": run["project"],
                            "name": run["name"],
                            "point_count": point_count,
                            "bytes_read": cursor["offset"],
                            "file_size": cursor["size"],
                        }
                    )
        return rows

    def list_saved_views(self) -> list[dict]:
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT id, name, view_kind, payload_json, created_at FROM user_state.saved_views ORDER BY id DESC"
            ).fetchall()
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "view_kind": row["view_kind"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def get_saved_view(self, view_id: int) -> dict | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT id, name, view_kind, payload_json, created_at FROM user_state.saved_views WHERE id = ?",
                (view_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "name": row["name"],
            "view_kind": row["view_kind"],
            "payload": json.loads(row["payload_json"]),
            "created_at": row["created_at"],
        }

    def create_saved_view(self, name: str, view_kind: str, payload: dict) -> dict:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                "INSERT INTO user_state.saved_views (name, view_kind, payload_json, created_at) VALUES (?, ?, ?, ?)",
                (
                    name,
                    view_kind,
                    json.dumps(payload, ensure_ascii=False),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            view_id = cursor.lastrowid
        return {
            "id": view_id,
            "name": name,
            "view_kind": view_kind,
            "payload": payload,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    def delete_saved_view(self, view_id: int) -> bool:
        with self.database.transaction() as connection:
            cursor = connection.execute("DELETE FROM user_state.saved_views WHERE id = ?", (view_id,))
            return cursor.rowcount > 0


def _flatten_config(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    if isinstance(value, dict):
        flattened: list[tuple[str, Any]] = []
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            flattened.extend(_flatten_config(child, child_prefix))
        return flattened
    if isinstance(value, list):
        return [(prefix, value)]
    return [(prefix, value)]
