"""不可重建的用户状态：备注、收藏、保存的对比视图。

这些数据与可重建的指标索引分库保存。删除 `index.sqlite3` 不会清空本文件；
旧版本的 `run_annotations` / `saved_views` 会在启动时迁移过来。
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

USER_STATE_SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS watched_roots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    added_at TEXT NOT NULL
);
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
"""


class UserStateStore:
    """独立 SQLite 用户状态库；不保存指标或索引。"""

    def __init__(self, database_file: Path):
        self.database_file = database_file
        self._write_lock = threading.RLock()

    def initialize(self) -> None:
        with self.connection() as connection:
            connection.executescript(SCHEMA_SQL)
            connection.execute(f"PRAGMA user_version={USER_STATE_SCHEMA_VERSION}")

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.database_file, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

    def migrate_from_index(self, index_database_file: Path) -> int:
        """把旧 index.sqlite3 中的备注/收藏/保存视图复制过来；幂等。"""
        if not index_database_file.is_file():
            return 0
        source = sqlite3.connect(index_database_file)
        try:
            tables = {
                row[0]
                for row in source.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            annotations = (
                source.execute(
                    "SELECT run_id, note, favorite, updated_at FROM run_annotations"
                ).fetchall()
                if "run_annotations" in tables
                else []
            )
            views = (
                source.execute(
                    "SELECT name, view_kind, payload_json, created_at FROM saved_views"
                ).fetchall()
                if "saved_views" in tables
                else []
            )
            roots = (
                source.execute("SELECT path, added_at FROM watched_roots").fetchall()
                if "watched_roots" in tables
                else []
            )
        finally:
            source.close()
        migrated = 0
        with self.transaction() as connection:
            for run_id, note, favorite, updated_at in annotations:
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO run_annotations (run_id, note, favorite, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (run_id, note, favorite, updated_at),
                )
                migrated += cursor.rowcount
            existing_views = connection.execute("SELECT COUNT(*) FROM saved_views").fetchone()[0]
            if existing_views == 0:
                for name, view_kind, payload_json, created_at in views:
                    connection.execute(
                        "INSERT INTO saved_views (name, view_kind, payload_json, created_at) VALUES (?, ?, ?, ?)",
                        (name, view_kind, payload_json, created_at),
                    )
                    migrated += 1
            existing_roots = connection.execute("SELECT COUNT(*) FROM watched_roots").fetchone()[0]
            if existing_roots == 0:
                for path, added_at in roots:
                    connection.execute(
                        "INSERT OR IGNORE INTO watched_roots (path, added_at) VALUES (?, ?)",
                        (path, added_at),
                    )
                    migrated += 1
        return migrated

    def list_roots(self) -> list[dict]:
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT id, path, added_at FROM watched_roots ORDER BY id ASC"
            ).fetchall()
        return [dict(row) for row in rows]

    def find_root_by_path(self, path: str) -> dict | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT id, path, added_at FROM watched_roots WHERE path = ?", (path,)
            ).fetchone()
        return dict(row) if row is not None else None

    def add_root(self, path: str, added_at: str) -> dict:
        with self.transaction() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO watched_roots (path, added_at) VALUES (?, ?)",
                (path, added_at),
            )
            if cursor.rowcount == 0:
                row = connection.execute(
                    "SELECT id, path, added_at FROM watched_roots WHERE path = ?", (path,)
                ).fetchone()
                return dict(row)
            root_id = cursor.lastrowid
        return {"id": root_id, "path": path, "added_at": added_at}

    def remove_root(self, root_id: int) -> dict | None:
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT id, path, added_at FROM watched_roots WHERE id = ?", (root_id,)
            ).fetchone()
            if row is None:
                return None
            connection.execute("DELETE FROM watched_roots WHERE id = ?", (root_id,))
        return dict(row)

    def get_annotation(self, run_id: str) -> dict:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT note, favorite, updated_at FROM run_annotations WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return (
            dict(row) if row is not None else {"note": "", "favorite": 0, "updated_at": None}
        )

    def save_annotation(self, run_id: str, note: str | None, favorite: bool | None) -> dict:
        current = self.get_annotation(run_id)
        new_note = current["note"] if note is None else note
        new_favorite = current["favorite"] if favorite is None else int(bool(favorite))
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO run_annotations (run_id, note, favorite, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    note = excluded.note,
                    favorite = excluded.favorite,
                    updated_at = excluded.updated_at
                """,
                (run_id, new_note, new_favorite, datetime.now(timezone.utc).isoformat()),
            )
        return self.get_annotation(run_id)

    def list_saved_views(self) -> list[dict]:
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT id, name, view_kind, payload_json, created_at FROM saved_views ORDER BY id DESC"
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
        with self.connection() as connection:
            row = connection.execute(
                "SELECT id, name, view_kind, payload_json, created_at FROM saved_views WHERE id = ?",
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
        with self.transaction() as connection:
            cursor = connection.execute(
                "INSERT INTO saved_views (name, view_kind, payload_json, created_at) VALUES (?, ?, ?, ?)",
                (
                    name,
                    view_kind,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            view_id = cursor.lastrowid
        view = self.get_saved_view(view_id)
        assert view is not None
        return view

    def delete_saved_view(self, view_id: int) -> bool:
        with self.transaction() as connection:
            cursor = connection.execute("DELETE FROM saved_views WHERE id = ?", (view_id,))
        return cursor.rowcount > 0

    @contextmanager
    def transaction(self):
        connection = sqlite3.connect(self.database_file, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
