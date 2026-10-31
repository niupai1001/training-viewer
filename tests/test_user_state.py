"""用户状态与可重建索引分离：删索引不能丢备注/收藏/保存视图。"""
from __future__ import annotations

from pathlib import Path

from training_viewer.application_paths import ApplicationPaths
from training_viewer.service import TrainingViewerService


def test_user_state_survives_index_database_deletion(tmp_path: Path) -> None:
    paths = ApplicationPaths.resolve(tmp_path / "data")
    service = TrainingViewerService(paths)
    root = tmp_path / "logs"
    root.mkdir()
    service.add_root(str(root))
    service.queries.save_annotation("run-kept", "重要结论", True)
    view = service.queries.create_saved_view(
        "对比基线", "comparison", {"run_ids": ["run-kept"], "series": ["val/miou"]}
    )
    assert paths.user_state_file.is_file()
    paths.database_file.unlink()

    reopened = TrainingViewerService(paths)
    assert reopened.list_roots()[0]["path"] == str(root.resolve())
    annotation = reopened.queries.get_annotation("run-kept")
    assert annotation["note"] == "重要结论"
    assert annotation["favorite"] == 1
    restored = reopened.queries.get_saved_view(view["id"])
    assert restored is not None
    assert restored["payload"]["run_ids"] == ["run-kept"]


def test_old_index_annotations_are_migrated_once(tmp_path: Path) -> None:
    paths = ApplicationPaths.resolve(tmp_path / "data")
    service = TrainingViewerService(paths)
    with service.database.transaction() as connection:
        connection.execute("DELETE FROM run_annotations")
        connection.execute(
            "INSERT INTO run_annotations (run_id, note, favorite, updated_at) VALUES (?, ?, ?, ?)",
            ("legacy-run", "旧备注", 1, "2026-10-31T00:00:00Z"),
        )
    # 清空新库模拟从旧版本升级。
    with service.user_state.transaction() as connection:
        connection.execute("DELETE FROM run_annotations")
    service.user_state.migrate_from_index(paths.database_file)
    assert service.queries.get_annotation("legacy-run")["note"] == "旧备注"
