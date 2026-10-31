"""应用服务层：协调目录扫描、增量索引、状态刷新与实时通知。

FastAPI 路由只调用这里，不直接操作文件或 SQL；后台轮询线程也调用同一个
synchronize()，因此手动刷新和自动刷新不会互相覆盖。
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from .application_paths import ApplicationPaths
from .discovery.run_directory_scanner import RunDirectoryScanner
from .indexing.database import IndexDatabase
from .indexing.index_queries import IndexQueries
from .indexing.training_metric_indexer import TrainingMetricIndexer
from .identity.logical_runs import LogicalRunOverride, LogicalRunOverrideStore
from .log_readers.base import ParseIssue
from .source_adapters.base import SourceAdapterRegistry
from .source_adapters.builtin_adapters import build_builtin_source_adapter_registry
from .user_state import UserStateStore

LOGGER = logging.getLogger("training_viewer.service")


class TrainingViewerService:
    """Training Viewer 的本机服务核心。"""

    def __init__(
        self,
        paths: ApplicationPaths,
        now=None,
        scan_interval_seconds: float = 2.0,
        source_adapter_registry: SourceAdapterRegistry | None = None,
        full_scan_interval_seconds: float = 300.0,
    ):
        self.paths = paths
        self.user_state = UserStateStore(paths.user_state_file)
        self.user_state.initialize()
        self.database = IndexDatabase(paths.database_file, paths.user_state_file)
        self.database.initialize()
        self.user_state.migrate_from_index(paths.database_file)
        self.registry = source_adapter_registry or build_builtin_source_adapter_registry()
        self.scanner = RunDirectoryScanner(self.registry)
        self.logical_runs = LogicalRunOverrideStore(paths.data_dir / "logical_runs.json")
        self.last_identity_audit: list[dict] = []
        self.indexer = TrainingMetricIndexer(self.database, now=now)
        self.queries = IndexQueries(self.database, now=now)
        self.scan_interval_seconds = scan_interval_seconds
        self.full_scan_interval_seconds = full_scan_interval_seconds
        self.version = 0
        self.last_sync_at: str | None = None
        self.last_full_scan_at: str | None = None
        self.last_sync_error: str | None = None
        self._last_full_scan_monotonic: float | None = None
        self._sync_lock = threading.Lock()
        self._watch_lock = threading.RLock()
        self._subscribers: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []
        self._watcher = None
        self._last_scan_issue_signature: tuple | None = None
        self._last_conflict_signature: tuple | None = None

    # ------------------------------------------------------------------ 根目录
    def list_roots(self) -> list[dict]:
        return self.user_state.list_roots()

    def add_root(self, path: str) -> dict:
        raw_path = Path(path).expanduser()
        if not raw_path.exists():
            raise ValueError(f"目录不存在：{raw_path}")
        if not raw_path.is_dir():
            raise ValueError(f"路径不是目录：{raw_path}")
        resolved = raw_path.resolve()
        existing = self.user_state.find_root_by_path(str(resolved))
        if existing is not None:
            return existing
        root = self.user_state.add_root(
            str(resolved), datetime.now(timezone.utc).isoformat()
        )
        LOGGER.info("已添加扫描根目录 %s", resolved)
        self.synchronize(force_full=True)
        self._refresh_watch_roots()
        return root

    def remove_root(self, root_id: int) -> bool:
        root = self.user_state.remove_root(root_id)
        if root is None:
            return False
        with self.database.transaction() as connection:
            connection.execute("DELETE FROM runs WHERE root_path = ?", (root["path"],))
            connection.execute("DELETE FROM run_conflicts")
        self.queries.invalidate_series_cache()
        LOGGER.info("已移除扫描根目录 %s（原始文件未删除）", root["path"])
        self._publish({"version": self.version, "removed_root": root_id, "changed_runs": []})
        self.synchronize(force_full=True)
        self._refresh_watch_roots()
        return True

    # ------------------------------------------------------------------ 逻辑实验
    def list_logical_overrides(self) -> list[dict]:
        return [
            {
                "logical_run_id": item.logical_run_id,
                "name": item.name,
                "files": item.files,
                "reason": item.reason,
                "created_at": item.created_at,
            }
            for item in self.logical_runs.load()
        ]

    def save_logical_override(
        self, logical_run_id: str, name: str, files: list[str], reason: str = "user-confirmed"
    ) -> dict:
        roots = [Path(root["path"]).resolve() for root in self.list_roots()]
        if not roots:
            raise ValueError("请先添加日志根目录，再建立逻辑实验归并")
        resolved_files: list[str] = []
        for item in files:
            path = Path(item).expanduser().resolve()
            if not path.is_file():
                raise ValueError(f"来源文件不存在：{path}")
            if not any(path.is_relative_to(root) for root in roots):
                raise ValueError(f"来源文件不在已添加的日志根目录内：{path}")
            resolved_files.append(str(path))
        if not resolved_files:
            raise ValueError("至少选择一个来源文件")
        override = LogicalRunOverride(
            logical_run_id=logical_run_id.strip(),
            name=name.strip(),
            files=resolved_files,
            reason=reason.strip() or "user-confirmed",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.logical_runs.upsert(override)
        self.synchronize(force_full=True)
        return next(
            item
            for item in self.list_logical_overrides()
            if item["logical_run_id"] == override.logical_run_id
        )

    def delete_logical_override(self, logical_run_id: str) -> bool:
        before = {item.logical_run_id for item in self.logical_runs.load()}
        if logical_run_id not in before:
            return False
        self.logical_runs.delete(logical_run_id)
        self.indexer.delete_run(logical_run_id)
        self.synchronize(force_full=True)
        return True

    def _apply_logical_overrides(self, discovered_runs: list[tuple]) -> list[tuple]:
        if not discovered_runs:
            return discovered_runs
        resolved, audit = self.logical_runs.resolve([item[0] for item in discovered_runs])
        self.last_identity_audit = audit
        root_by_directory = {
            str(item[0].run_directory): item[1] for item in discovered_runs
        }
        result = []
        for discovered in resolved:
            root_path = root_by_directory.get(str(discovered.run_directory))
            if root_path is None:
                continue
            merged = (discovered.metadata.get("extensions") or {}).get(
                "merged_source_run_ids"
            )
            if merged:
                if not self._run_exists(discovered.run_id):
                    file_paths = [
                        str(spec.file_path) for spec in discovered.log_files
                    ]
                    self.indexer.delete_runs_for_source_files(file_paths)
            result.append((discovered, root_path))
        return result

    def _run_exists(self, run_id: str) -> bool:
        with self.database.connection() as connection:
            return (
                connection.execute(
                    "SELECT 1 FROM runs WHERE run_id = ?", (run_id,)
                ).fetchone()
                is not None
            )

    # ------------------------------------------------------------------ 同步
    def synchronize(self, force_full: bool = False) -> dict:
        """同步目录。

        首次、手动刷新和达到全量间隔时重新发现目录；其余轮询只重读已知 Run 的
        文件，避免每 2 秒遍历整个目录树。已知目录消失时会立即升级为全量扫描，
        以发现移动后的位置。
        """
        with self._sync_lock:
            roots = self.list_roots()
            now_monotonic = time.monotonic()
            full_scan_due = (
                self._last_full_scan_monotonic is None
                or now_monotonic - self._last_full_scan_monotonic
                >= self.full_scan_interval_seconds
            )
            full_scan = bool(force_full or full_scan_due)
            changed_runs: set[str] = set()
            scan_issues: list[ParseIssue] = []
            discovered_runs: list[tuple] = []
            discovered_directories: set[str] = set()
            seen_run_ids: dict[str, str] = {}
            conflicts: list[dict] = []
            had_ingest_issues = False

            def add_discovered(discovered, root_path: Path) -> None:
                run_directory = str(discovered.run_directory)
                discovered_directories.add(run_directory)
                known_directory = seen_run_ids.get(discovered.run_id)
                if known_directory is not None:
                    if known_directory != run_directory:
                        conflicts.append(
                            {
                                "run_id": discovered.run_id,
                                "kept_run_dir": known_directory,
                                "conflicting_run_dir": run_directory,
                            }
                        )
                    return
                seen_run_ids[discovered.run_id] = run_directory
                discovered_runs.append((discovered, root_path))

            try:
                if not full_scan:
                    known = self._known_run_directories(roots)
                    if not known:
                        full_scan = True
                    else:
                        for known_directory, root_path in known:
                            try:
                                found = self.registry.find_adapters(Path(known_directory))
                            except Exception:  # noqa: BLE001 - 单目录失败升级为全量
                                found = []
                            if not found:
                                full_scan = True
                                break
                            for discovered in found:
                                add_discovered(discovered, root_path)

                if full_scan:
                    # 全量发现需要重新计算运行目录、冲突与目录级问题。
                    discovered_runs.clear()
                    discovered_directories.clear()
                    seen_run_ids.clear()
                    conflicts.clear()
                    for root in roots:
                        root_path = Path(root["path"])
                        root_result = self.scanner.scan(root_path)
                        for issue in root_result.issues:
                            scan_issues.append(
                                ParseIssue(issue.path, 0, issue.message, _severity(issue.severity))
                            )
                        for discovered in root_result.runs:
                            add_discovered(discovered, root_path)

                discovered_runs = self._apply_logical_overrides(discovered_runs)
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
                        had_ingest_issues = True
                        continue
                    if report.issues:
                        had_ingest_issues = True
                    for issue in report.issues:
                        scan_issues.append(issue)
                    if report.changed:
                        changed_runs.add(report.run_id)

                if full_scan:
                    self._mark_missing_directories(discovered_directories, changed_runs)
                changed_runs.update(self.indexer.refresh_statuses())
                if changed_runs:
                    self.queries.invalidate_series_cache()
                if full_scan:
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
                    self._last_full_scan_monotonic = now_monotonic
                    self.last_full_scan_at = datetime.now(timezone.utc).isoformat()
                else:
                    diagnostics_changed = had_ingest_issues
                    issue_signature = self._last_scan_issue_signature
                    conflict_signature = self._last_conflict_signature

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
                    "full_scan": full_scan,
                }
            except Exception as error:  # noqa: BLE001 - 后台线程必须保持存活
                self.last_sync_error = str(error)
                LOGGER.exception("同步失败")
                raise

    def _known_run_directories(self, roots: list[dict]) -> list[tuple[str, Path]]:
        if not roots:
            return []
        placeholders = ",".join("?" for _ in roots)
        with self.database.connection() as connection:
            rows = connection.execute(
                f"SELECT run_dir, root_path FROM runs WHERE root_path IN ({placeholders})",
                [root["path"] for root in roots],
            ).fetchall()
        seen: set[str] = set()
        known: list[tuple[str, Path]] = []
        for row in rows:
            if row["run_dir"] in seen:
                continue
            seen.add(row["run_dir"])
            known.append((row["run_dir"], Path(row["root_path"])))
        return known

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
            "last_full_scan_at": self.last_full_scan_at,
            "full_scan_interval_seconds": self.full_scan_interval_seconds,
            "last_sync_error": self.last_sync_error,
            "data_dir": str(self.paths.data_dir),
            "index_database": str(self.paths.database_file),
            "user_state_database": str(self.paths.user_state_file),
            "index_rebuildable": True,
            "user_state_rebuildable": False,
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
