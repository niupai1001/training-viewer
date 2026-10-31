"""SQLite 索引数据库。

这里保存的全部内容都可以从原始日志重建：运行列表、指标点、产物引用、事件、
文件游标和解析问题。用户备注与保存的对比视图也存放在同一个本地数据库中，
但删除数据库只会丢失界面数据，不会影响原始实验目录。
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS watched_roots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    added_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    source_kind TEXT NOT NULL,
    adapter_id TEXT NOT NULL,
    run_dir TEXT NOT NULL,
    root_path TEXT NOT NULL,
    project TEXT NOT NULL,
    experiment TEXT,
    name TEXT NOT NULL,
    task TEXT,
    created_at TEXT,
    metadata_json TEXT NOT NULL,
    model_name TEXT,
    model_architecture TEXT,
    dataset_name TEXT,
    tags_json TEXT NOT NULL DEFAULT '[]',
    seed INTEGER,
    status TEXT NOT NULL,
    status_reason TEXT NOT NULL,
    last_updated_at TEXT,
    discovered_at TEXT NOT NULL,
    directory_available INTEGER NOT NULL DEFAULT 1,
    metadata_synthetic INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_runs_project_experiment ON runs(project, experiment);
CREATE INDEX IF NOT EXISTS idx_runs_root ON runs(root_path);
CREATE INDEX IF NOT EXISTS idx_runs_run_dir ON runs(run_dir);
CREATE INDEX IF NOT EXISTS idx_runs_model ON runs(model_name);
CREATE INDEX IF NOT EXISTS idx_runs_dataset ON runs(dataset_name);

CREATE TABLE IF NOT EXISTS metric_points (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    phase TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    global_step INTEGER,
    epoch INTEGER,
    timestamp TEXT,
    session_id TEXT,
    value REAL NOT NULL,
    event_id TEXT,
    source_file TEXT NOT NULL,
    source_offset INTEGER NOT NULL,
    line_number INTEGER,
    UNIQUE(run_id, source_file, source_offset, metric_name)
);
CREATE INDEX IF NOT EXISTS idx_metric_points_series
    ON metric_points(run_id, phase, metric_name, global_step);
CREATE INDEX IF NOT EXISTS idx_metric_points_epoch
    ON metric_points(run_id, phase, metric_name, epoch);
CREATE INDEX IF NOT EXISTS idx_metric_points_time
    ON metric_points(run_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_metric_points_run_id ON metric_points(run_id, id);

CREATE TABLE IF NOT EXISTS artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    tag TEXT NOT NULL,
    phase TEXT,
    global_step INTEGER,
    epoch INTEGER,
    group_id TEXT,
    sample_id TEXT,
    role TEXT,
    mime_type TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    timestamp TEXT,
    session_id TEXT,
    event_id TEXT,
    source_file TEXT NOT NULL,
    source_offset INTEGER NOT NULL,
    exists_on_disk INTEGER NOT NULL DEFAULT 1,
    size INTEGER,
    mtime REAL,
    UNIQUE(run_id, source_file, source_offset)
);
CREATE INDEX IF NOT EXISTS idx_artifacts_run_tag ON artifacts(run_id, tag);
CREATE INDEX IF NOT EXISTS idx_artifacts_group ON artifacts(run_id, group_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_sample ON artifacts(run_id, sample_id);

CREATE TABLE IF NOT EXISTS training_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    status TEXT,
    timestamp TEXT NOT NULL,
    session_id TEXT,
    global_step INTEGER,
    message TEXT,
    event_id TEXT,
    source_file TEXT NOT NULL,
    source_offset INTEGER NOT NULL,
    UNIQUE(run_id, source_file, source_offset)
);
CREATE INDEX IF NOT EXISTS idx_training_events_run ON training_events(run_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_training_events_status ON training_events(run_id, event_type, status);

CREATE TABLE IF NOT EXISTS ingestion_cursors (
    file_path TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    file_kind TEXT NOT NULL,
    file_identity TEXT NOT NULL,
    offset INTEGER NOT NULL,
    line_number INTEGER NOT NULL,
    size INTEGER NOT NULL,
    mtime REAL NOT NULL,
    updated_at TEXT NOT NULL,
    health TEXT NOT NULL DEFAULT 'ok'
);
CREATE INDEX IF NOT EXISTS idx_ingestion_cursors_run ON ingestion_cursors(run_id);

CREATE TABLE IF NOT EXISTS ingestion_issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_key TEXT NOT NULL UNIQUE,
    run_id TEXT REFERENCES runs(run_id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    line_number INTEGER NOT NULL DEFAULT 0,
    message TEXT NOT NULL,
    severity TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ingestion_issues_run ON ingestion_issues(run_id);

CREATE TABLE IF NOT EXISTS run_annotations (
    run_id TEXT PRIMARY KEY,
    note TEXT NOT NULL DEFAULT '',
    favorite INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS saved_views (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    view_kind TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_conflicts (
    run_id TEXT PRIMARY KEY,
    kept_run_dir TEXT NOT NULL,
    conflicting_run_dir TEXT NOT NULL,
    detected_at TEXT NOT NULL
);
"""


class IndexDatabase:
    """索引数据库连接与事务边界。"""

    def __init__(self, database_file: Path):
        self.database_file = database_file
        self._write_lock = threading.RLock()

    def initialize(self) -> None:
        with self.connection() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            current_version = connection.execute("PRAGMA user_version").fetchone()[0]
            if current_version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"索引数据库版本 {current_version} 高于本程序支持的 {SCHEMA_VERSION}；"
                    "请升级 Training Viewer，或删除索引数据库后重建。"
                )
            connection.executescript(SCHEMA_SQL)
            connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.database_file, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self):
        with self._write_lock:
            with self.connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    yield connection
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
                else:
                    connection.execute("COMMIT")
