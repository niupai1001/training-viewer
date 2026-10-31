"""索引与实时同步：去重、半行、截断、会话、状态、CSV 与 TensorBoard 来源。"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from conftest import (
    EXAMPLE_RUNS,
    FIXED_NOW,
    make_run_directory,
    metric_record,
)
from training_viewer.application_paths import ApplicationPaths
from training_viewer.run_metadata import RunMetadataReader
from training_viewer.service import TrainingViewerService
from training_viewer.source_adapters.base import DiscoveredRun, SourceAdapterRegistry


def _metric_line(record: dict) -> bytes:
    return json.dumps(record, ensure_ascii=False).encode("utf-8")


def test_ingestion_is_idempotent_and_keeps_same_step_across_phases(viewer) -> None:
    service, _ = viewer
    run_directory = make_run_directory(
        Path(service.paths.data_dir).parent / "logs",
        metrics=[
            metric_record("2026-10-31T08:00:00Z", "train", {"loss": 0.9}, 100, 1),
            metric_record("2026-10-31T08:00:30Z", "val", {"loss": 0.8, "miou": 0.4}, 100, 1),
        ],
    )
    service.add_root(str(run_directory.parent))
    first = service.queries.list_runs()
    assert first["total"] == 1
    run = first["runs"][0]
    detail = service.queries.get_run(run["run_id"])
    assert detail is not None
    assert detail["counts"]["metric_point_count"] == 3

    service.synchronize()
    service.synchronize()
    detail_again = service.queries.get_run(run["run_id"])
    assert detail_again is not None
    assert detail_again["counts"]["metric_point_count"] == 3
    series = service.queries.query_series(
        run["run_id"], ["train/loss", "val/loss"], "global_step", 100
    )
    assert {item["key"] for item in series["series"]} == {"train/loss", "val/loss"}


def test_append_and_trailing_partial_line(viewer) -> None:
    service, _ = viewer
    run_directory = make_run_directory(
        Path(service.paths.data_dir).parent / "logs",
        metrics=[metric_record("2026-10-31T08:00:00Z", "train", {"loss": 0.9}, 100, 1)],
    )
    service.add_root(str(run_directory.parent))
    run_id = service.queries.list_runs()["runs"][0]["run_id"]
    metrics_path = run_directory / "metrics.jsonl"
    with metrics_path.open("ab") as handle:
        handle.write(_metric_line(metric_record("2026-10-31T08:00:10Z", "train", {"loss": 0.85}, 200, 1)))
        handle.write(b"\n")
        handle.write(b'{"timestamp":"2026-10-31T08:00:20Z","phase":"train","global_step":300,"metrics":{"loss":0.8')
    service.synchronize()
    detail = service.queries.get_run(run_id)
    assert detail is not None
    assert detail["counts"]["metric_point_count"] == 2
    assert any("尚未写完" in issue["message"] for issue in detail["issues"])

    with metrics_path.open("ab") as handle:
        handle.write(b"}}\n")
    service.synchronize()
    detail = service.queries.get_run(run_id)
    assert detail is not None
    assert detail["counts"]["metric_point_count"] == 3
    assert not any("尚未写完" in issue["message"] for issue in detail["issues"])


def test_truncation_rebuilds_index_without_duplicates(viewer) -> None:
    service, _ = viewer
    run_directory = make_run_directory(
        Path(service.paths.data_dir).parent / "logs",
        metrics=[
            metric_record("2026-10-31T08:00:00Z", "train", {"loss": 0.9}, 100, 1),
            metric_record("2026-10-31T08:01:00Z", "train", {"loss": 0.7}, 200, 1),
            metric_record("2026-10-31T08:02:00Z", "train", {"loss": 0.6}, 300, 1),
        ],
    )
    service.add_root(str(run_directory.parent))
    run_id = service.queries.list_runs()["runs"][0]["run_id"]
    (run_directory / "metrics.jsonl").write_text(
        json.dumps(metric_record("2026-10-31T08:03:00Z", "train", {"loss": 0.55}, 50, 1))
        + "\n",
        encoding="utf-8",
    )
    service.synchronize()
    detail = service.queries.get_run(run_id)
    assert detail is not None
    assert detail["counts"]["metric_point_count"] == 1
    assert any("截断" in issue["message"] for issue in detail["issues"])
    assert not any("重复" in issue["message"] for issue in detail["issues"])


def test_status_completed_and_running_from_heartbeat(viewer) -> None:
    service, _ = viewer
    make_run_directory(
        Path(service.paths.data_dir).parent / "logs" / "completed",
        run_id="completed-run",
        metrics=[metric_record("2026-10-31T08:00:00Z", "train", {"loss": 0.5}, 100, 1)],
        events=[
            {"type": "lifecycle", "timestamp": "2026-10-31T08:00:00Z", "session_id": "s1", "status": "started"},
            {"type": "lifecycle", "timestamp": "2026-10-31T08:05:00Z", "session_id": "s1", "status": "completed"},
        ],
    )
    make_run_directory(
        Path(service.paths.data_dir).parent / "logs" / "running",
        run_id="running-run",
        metrics=[metric_record("2026-10-31T08:59:00Z", "train", {"loss": 0.9}, 100, 1)],
        events=[
            {"type": "lifecycle", "timestamp": "2026-10-31T08:58:00Z", "session_id": "s1", "status": "started"},
            {"type": "heartbeat", "timestamp": "2026-10-31T08:59:30Z", "session_id": "s1", "global_step": 100},
        ],
    )
    service.add_root(str(Path(service.paths.data_dir).parent / "logs"))
    runs = {run["run_id"]: run for run in service.queries.list_runs()["runs"]}
    assert runs["completed-run"]["status"] == "completed"
    assert runs["running-run"]["status"] == "running"
    assert runs["running-run"]["status_label"] == "运行中"

    # 状态依据注入的 FIXED_NOW（09:00:00Z）计算；心跳已是 30 秒前。
    assert "最近 120 秒" in runs["running-run"]["status_reason"]


def test_stale_run_is_unknown_not_failed(viewer) -> None:
    service, _ = viewer
    run_directory = make_run_directory(
        Path(service.paths.data_dir).parent / "logs",
        metrics=[metric_record("2026-10-31T06:00:00Z", "train", {"loss": 0.9}, 100, 1)],
        events=[
            {"type": "lifecycle", "timestamp": "2026-10-31T06:00:00Z", "session_id": "s1", "status": "started"},
            {"type": "heartbeat", "timestamp": "2026-10-31T06:01:00Z", "session_id": "s1", "global_step": 100},
        ],
    )
    service.add_root(str(run_directory.parent))
    run = service.queries.list_runs()["runs"][0]
    assert run["status"] == "unknown"
    assert "不能证明训练失败" in run["status_reason"]


def test_resumed_sessions_are_preserved_and_step_regression_is_per_session(viewer) -> None:
    service, _ = viewer
    run_directory = make_run_directory(
        Path(service.paths.data_dir).parent / "logs",
        metrics=[
            metric_record("2026-10-31T08:00:00Z", "train", {"loss": 0.9}, 100, 1, session_id="s1"),
            metric_record("2026-10-31T08:01:00Z", "train", {"loss": 0.8}, 200, 2, session_id="s1"),
            metric_record("2026-10-31T08:10:00Z", "train", {"loss": 0.75}, 100, 3, session_id="s2"),
            metric_record("2026-10-31T08:11:00Z", "train", {"loss": 0.7}, 200, 4, session_id="s2"),
        ],
    )
    service.add_root(str(run_directory.parent))
    run = service.queries.list_runs()["runs"][0]
    detail = service.queries.get_run(run["run_id"])
    assert detail is not None
    assert detail["counts"]["metric_point_count"] == 4
    assert [session["session_id"] for session in detail["sessions"]] == ["s1", "s2"]
    assert detail["step_warnings"] == []
    series = service.queries.query_series(run["run_id"], ["train/loss"], "global_step", 100)
    assert len(series["series"][0]["points"]) == 4
    assert any("执行会话" in warning["message"] for warning in series["series"][0]["warnings"])


def test_step_regression_within_one_session_is_reported(viewer) -> None:
    service, _ = viewer
    run_directory = make_run_directory(
        Path(service.paths.data_dir).parent / "logs",
        metrics=[
            metric_record("2026-10-31T08:00:00Z", "train", {"loss": 0.9}, 200, 1, session_id="s1"),
            metric_record("2026-10-31T08:01:00Z", "train", {"loss": 0.8}, 100, 1, session_id="s1"),
        ],
    )
    service.add_root(str(run_directory.parent))
    run = service.queries.list_runs()["runs"][0]
    detail = service.queries.get_run(run["run_id"])
    assert detail is not None
    assert len(detail["step_warnings"]) == 1
    assert detail["step_warnings"][0]["previous_step"] == 200


def test_csv_metrics_with_explicit_column_mapping(viewer) -> None:
    service, _ = viewer
    logs = Path(service.paths.data_dir).parent / "logs"
    run_directory = logs / "csv_run"
    run_directory.mkdir(parents=True)
    metadata = {
        "schema_version": "1.0",
        "run_id": "csv-run-1",
        "project": "CSV 项目",
        "name": "CSV 映射运行",
        "created_at": "2026-10-31T08:00:00Z",
        "metric_definitions": {
            "train/loss": {"direction": "min", "unit": "none"},
            "val/accuracy": {"direction": "max", "unit": "ratio"},
        },
        "extensions": {
            "csv_metric_mapping": {
                "step_column": "step",
                "epoch_column": "epoch",
                "timestamp_column": "timestamp",
                "phase_column": "phase",
                "metric_columns": ["loss", "accuracy"],
            }
        },
    }
    (run_directory / "run.json").write_text(json.dumps(metadata), encoding="utf-8")
    (run_directory / "metrics.csv").write_text(
        "timestamp,epoch,step,phase,loss,accuracy\n"
        "2026-10-31T08:00:30Z,1,100,train,0.8,\n"
        "2026-10-31T08:00:40Z,1,100,val,,0.62\n"
        "2026-10-31T08:01:30Z,2,200,train,0.6,\n",
        encoding="utf-8",
    )
    service.add_root(str(logs))
    run = service.queries.list_runs()["runs"][0]
    detail = service.queries.get_run(run["run_id"])
    assert detail is not None
    assert {key["key"] for key in detail["metric_keys"]} == {"train/loss", "val/accuracy"}
    assert detail["counts"]["metric_point_count"] == 3
    assert run["source_kind"] == "tvlp"

    # 再次同步不会重复导入 CSV 行。
    service.synchronize()
    assert service.queries.get_run(run["run_id"])["counts"]["metric_point_count"] == 3


def test_csv_without_run_json_uses_synthetic_metadata(viewer) -> None:
    service, _ = viewer
    logs = Path(service.paths.data_dir).parent / "logs"
    run_directory = logs / "plain_csv"
    run_directory.mkdir(parents=True)
    (run_directory / "metrics.csv").write_text(
        "epoch,step,phase,loss,accuracy\n"
        "1,100,train,0.8,\n"
        "1,100,val,,0.62\n",
        encoding="utf-8",
    )
    service.add_root(str(logs))
    run = service.queries.list_runs()["runs"][0]
    assert run["source_kind"] == "csv"
    assert run["metadata_synthetic"] is True
    assert run["status"] == "imported"
    assert run["project"] == "logs"
    assert service.queries.get_run(run["run_id"])["counts"]["metric_point_count"] == 2


def test_csv_without_step_or_epoch_is_reported_not_invented(viewer) -> None:
    service, _ = viewer
    logs = Path(service.paths.data_dir).parent / "logs"
    run_directory = logs / "bad_csv"
    run_directory.mkdir(parents=True)
    (run_directory / "metrics.csv").write_text(
        "loss,accuracy\n0.8,0.62\n",
        encoding="utf-8",
    )
    service.add_root(str(logs))
    run = service.queries.list_runs()["runs"][0]
    detail = service.queries.get_run(run["run_id"])
    assert detail is not None
    assert detail["counts"]["metric_point_count"] == 0
    assert any("step" in issue["message"] for issue in detail["issues"])
    assert detail["metric_keys"] == []


def test_tensorboard_scalars_are_ingested(tmp_path, viewer) -> None:
    pytest.importorskip("tensorboard")
    service, _ = viewer
    source = EXAMPLE_RUNS / "tensorboard_scalars"
    if not source.is_dir():
        pytest.skip("没有 TensorBoard 示例事件文件")
    destination = Path(service.paths.data_dir).parent / "logs" / "tb"
    shutil.copytree(source, destination)
    service.add_root(str(destination.parent))
    runs = service.queries.list_runs()["runs"]
    assert len(runs) == 1
    run = runs[0]
    assert run["source_kind"] == "tensorboard"
    assert run["metadata_synthetic"] is True
    detail = service.queries.get_run(run["run_id"])
    assert detail is not None
    assert {key["key"] for key in detail["metric_keys"]} == {
        "train/loss",
        "val/miou",
        "val/f1",
    }
    series = service.queries.query_series(run["run_id"], ["train/loss"], "global_step", 100)
    assert len(series["series"][0]["points"]) == 11
    service.synchronize()
    assert service.queries.get_run(run["run_id"])["counts"]["metric_point_count"] == 33


def test_duplicate_run_id_is_reported_and_not_silently_merged(viewer) -> None:
    service, _ = viewer
    logs = Path(service.paths.data_dir).parent / "logs"
    make_run_directory(
        logs / "a",
        run_id="duplicate-run",
        metrics=[metric_record("2026-10-31T08:00:00Z", "train", {"loss": 0.9}, 100, 1)],
    )
    make_run_directory(
        logs / "b",
        run_id="duplicate-run",
        name="另一个同名运行",
        metrics=[metric_record("2026-10-31T08:00:00Z", "train", {"loss": 0.1}, 100, 1)],
    )
    service.add_root(str(logs))
    runs = service.queries.list_runs()["runs"]
    assert len(runs) == 1
    diagnostics = service.queries.diagnostics()
    assert len(diagnostics["conflicts"]) == 1
    assert diagnostics["conflicts"][0]["run_id"] == "duplicate-run"
    detail = service.queries.get_run("duplicate-run")
    assert detail is not None
    assert any(warning["code"] == "run_id_conflict" for warning in detail["warnings"])


def test_moved_run_directory_is_marked_unavailable_without_deleting_index(viewer) -> None:
    service, _ = viewer
    logs = Path(service.paths.data_dir).parent / "logs"
    run_directory = make_run_directory(
        logs,
        metrics=[metric_record("2026-10-31T08:00:00Z", "train", {"loss": 0.9}, 100, 1)],
    )
    service.add_root(str(logs))
    run_id = service.queries.list_runs()["runs"][0]["run_id"]
    moved = logs.parent / "moved_away"
    run_directory.rename(moved)
    service.synchronize()
    detail = service.queries.get_run(run_id)
    assert detail is not None
    assert detail["directory_available"] is False
    assert detail["status"] == "unknown"
    assert any(warning["code"] == "directory_unavailable" for warning in detail["warnings"])

    moved.rename(run_directory)
    service.synchronize()
    detail = service.queries.get_run(run_id)
    assert detail is not None
    assert detail["directory_available"] is True


def test_invalid_run_json_becomes_directory_diagnostic(viewer) -> None:
    service, _ = viewer
    logs = Path(service.paths.data_dir).parent / "logs"
    broken = logs / "broken"
    broken.mkdir(parents=True)
    (broken / "run.json").write_text('{"schema_version":"1.0"}', encoding="utf-8")
    service.add_root(str(logs))
    diagnostics = service.queries.diagnostics()
    assert any("run_id" in issue["message"] for issue in diagnostics["scan_issues"])
    assert diagnostics["totals"]["run_count"] is None or diagnostics["totals"]["run_count"] == 0


def test_annotations_survive_rescan(viewer) -> None:
    service, _ = viewer
    run_directory = make_run_directory(
        Path(service.paths.data_dir).parent / "logs",
        metrics=[metric_record("2026-10-31T08:00:00Z", "train", {"loss": 0.9}, 100, 1)],
    )
    service.add_root(str(run_directory.parent))
    run_id = service.queries.list_runs()["runs"][0]["run_id"]
    service.queries.save_annotation(run_id, "关键备注", True)
    service.synchronize()
    detail = service.queries.get_run(run_id)
    assert detail is not None
    assert detail["note"] == "关键备注"
    assert detail["favorite"] is True


def test_run_metadata_reader_rejects_unknown_fields(tmp_path: Path) -> None:
    run_directory = tmp_path / "run"
    run_directory.mkdir()
    (run_directory / "run.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": "x",
                "project": "p",
                "name": "n",
                "created_at": "2026-10-31T08:00:00Z",
                "mystery": 1,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(Exception, match="未知字段"):
        RunMetadataReader().read(run_directory)


def test_custom_source_adapter_can_register_without_core_changes(tmp_path: Path) -> None:
    class MarkerSourceAdapter:
        adapter_id = "test.marker_source"
        display_name = "测试标记来源"

        def discover(self, run_directory: Path):
            marker = run_directory / "marker.json"
            if not marker.is_file():
                return None
            payload = json.loads(marker.read_text(encoding="utf-8"))
            metadata = {
                "schema_version": "1.0",
                "run_id": payload["run_id"],
                "project": payload.get("project", "标记项目"),
                "name": payload.get("name", "标记运行"),
                "created_at": "2026-10-31T08:00:00Z",
                "extensions": {"source_adapter": self.adapter_id},
            }
            return DiscoveredRun(
                source_kind="marker",
                adapter_id=self.adapter_id,
                run_directory=run_directory,
                run_id=payload["run_id"],
                metadata=metadata,
                log_files=[],
                metadata_synthetic=True,
            )

    paths = ApplicationPaths.resolve(tmp_path / "custom-data")
    registry = SourceAdapterRegistry()
    registry.register(MarkerSourceAdapter())
    service = TrainingViewerService(
        paths, now=lambda: FIXED_NOW, source_adapter_registry=registry
    )
    try:
        root = tmp_path / "custom-logs"
        run_directory = root / "marker-run"
        run_directory.mkdir(parents=True)
        (run_directory / "marker.json").write_text(
            json.dumps({"run_id": "marker-1", "name": "标记来源运行"}), encoding="utf-8"
        )
        service.add_root(str(root))
        runs = service.queries.list_runs()["runs"]
        assert len(runs) == 1
        assert runs[0]["adapter_id"] == "test.marker_source"
        assert runs[0]["run_id"] == "marker-1"
        assert runs[0]["name"] == "标记来源运行"
    finally:
        service.stop_background_sync()
