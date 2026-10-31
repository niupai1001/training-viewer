"""逻辑实验归并、侧车覆盖与扫描不遗漏子目录 Run。"""
from __future__ import annotations

import json
from pathlib import Path

from conftest import make_run_directory, metric_record
from training_viewer.application_paths import ApplicationPaths
from training_viewer.service import TrainingViewerService


def _generic_csv(path: Path, values: list[float]) -> None:
    path.write_text(
        "step,loss\n" + "\n".join(f"{index + 1},{value}" for index, value in enumerate(values)) + "\n",
        encoding="utf-8",
    )


def test_explicit_logical_run_merges_files_without_touching_raw_logs(tmp_path: Path) -> None:
    paths = ApplicationPaths.resolve(tmp_path / "data")
    service = TrainingViewerService(paths)
    directory = tmp_path / "logs" / "alpha"
    directory.mkdir(parents=True)
    first = directory / "train.csv"
    second = directory / "val.csv"
    _generic_csv(first, [1.0, 0.5])
    _generic_csv(second, [0.8, 0.4])
    first_before = first.read_bytes()
    service.add_root(str(tmp_path / "logs"))
    assert service.queries.list_runs()["total"] == 2

    service.save_logical_override(
        "logical-alpha",
        "Alpha 合并实验",
        [str(first), str(second)],
        reason="用户确认这两个文件属于同一次训练",
    )
    runs = service.queries.list_runs()["runs"]
    assert len(runs) == 1
    assert runs[0]["run_id"] == "logical-alpha"
    detail = service.queries.get_run("logical-alpha")
    assert len(detail["data_sources"]) == 2
    assert first.read_bytes() == first_before
    assert (paths.data_dir / "logical_runs.json").is_file()
    assert not (tmp_path / "logs" / "logical_runs.json").exists()

    inventory = service.queries.source_inventory()
    assert {row["logical_run_id"] for row in inventory} == {"logical-alpha"}
    assert all(row["merged"] for row in inventory)
    assert all(row["confidence"] == "user-confirmed" for row in inventory)

    assert service.delete_logical_override("logical-alpha")
    assert service.queries.list_runs()["total"] == 2
    assert first.read_bytes() == first_before


def test_scanner_continues_into_children_after_generic_parent_run(tmp_path: Path) -> None:
    paths = ApplicationPaths.resolve(tmp_path / "data")
    service = TrainingViewerService(paths)
    root = tmp_path / "logs"
    parent = root / "parent"
    parent.mkdir(parents=True)
    (parent / "train.log").write_text("step=1 loss=0.9\n", encoding="utf-8")
    make_run_directory(
        parent / "child",
        run_id="child-tvlp",
        metrics=[metric_record("2026-10-31T08:00:00Z", "train", {"loss": 0.5}, 1, 1)],
    )
    service.add_root(str(root))
    run_ids = {run["run_id"] for run in service.queries.list_runs()["runs"]}
    assert "child-tvlp" in run_ids
    assert any(run_id.startswith("text-") for run_id in run_ids)


def test_explicit_jsonl_run_id_is_inventoried_without_silent_merge(tmp_path: Path) -> None:
    paths = ApplicationPaths.resolve(tmp_path / "data")
    service = TrainingViewerService(paths)
    root = tmp_path / "logs"
    root.mkdir()
    for name in ("train.jsonl", "val.jsonl"):
        (root / name).write_text(
            json.dumps({"run_id": "experiment-42", "step": 1, "loss": 0.5}) + "\n",
            encoding="utf-8",
        )
    service.add_root(str(root))
    assert service.queries.list_runs()["total"] == 2
    inventory = service.queries.source_inventory()
    assert {row["raw_run_identifier"] for row in inventory} == {"experiment-42"}
    assert all(not row["merged"] for row in inventory)
