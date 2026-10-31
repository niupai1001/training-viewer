"""训练侧写入器：创建标准 Run、指标、产物、恢复会话与失败状态。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from training_viewer.application_paths import ApplicationPaths
from training_viewer.log_validation import validate_run_directory
from training_viewer.writer import TrainingRunWriter


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_writer_creates_valid_run_with_metrics_and_artifact(tmp_path: Path) -> None:
    run_id = "writer-run-0001"
    with TrainingRunWriter(
        tmp_path / "experiments",
        project="写入器测试",
        name="写入器示例运行",
        run_id=run_id,
        experiment="接入测试",
        task="semantic-segmentation",
        model={"name": "测试模型"},
        dataset={"name": "测试数据集", "version": "v1"},
        config={"epochs": 1, "batch_size": 2},
        metric_definitions={
            "train/loss": {"direction": "min", "unit": "none"},
            "val/miou": {"direction": "max", "unit": "ratio"},
        },
        heartbeat_interval_seconds=0,
    ) as run:
        run.log_metrics("train", {"loss": 0.9}, global_step=10, epoch=1)
        run.log_metrics("val", {"loss": 0.8, "miou": 0.4}, global_step=10, epoch=1)
        artifact_file = run.artifact_path("artifacts/predictions/sample-001.png")
        artifact_file.write_bytes(b"not-a-real-png")
        run.log_artifact(
            "artifacts/predictions/sample-001.png",
            artifact_type="image",
            tag="segmentation-preview",
            phase="val",
            epoch=1,
            global_step=10,
            group_id="sample-001-epoch-1",
            sample_id="sample-001",
            role="prediction",
        )

    run_directory = tmp_path / "experiments" / run_id
    report = validate_run_directory(
        run_directory, ApplicationPaths.resolve(tmp_path / "data").schema_dir
    )
    assert report.error_count == 0, [message.__dict__ for message in report.messages]
    metadata = json.loads((run_directory / "run.json").read_text(encoding="utf-8"))
    assert metadata["run_id"] == run_id
    assert metadata["metric_definitions"]["val/miou"]["direction"] == "max"
    metrics = read_jsonl(run_directory / "metrics.jsonl")
    assert len(metrics) == 2
    assert metrics[0]["phase"] == "train"
    assert metrics[0]["metrics"]["loss"] == 0.9
    assert metrics[1]["global_step"] == 10
    events = read_jsonl(run_directory / "events.jsonl")
    assert [event["status"] for event in events if event["type"] == "lifecycle"] == [
        "started",
        "completed",
    ]
    artifact_event = next(event for event in events if event["type"] == "artifact")
    assert artifact_event["path"] == "artifacts/predictions/sample-001.png"
    assert artifact_event["role"] == "prediction"


def test_writer_normalizes_missing_metric_direction(tmp_path: Path) -> None:
    writer = TrainingRunWriter(
        log_root=tmp_path / "logs",
        project="demo",
        name="directions",
        metric_definitions={
            "train/loss": {"direction": None},
            "train/lr": {},
        },
    )
    assert writer.metric_definitions["train/loss"]["direction"] == "none"
    assert writer.metric_definitions["train/lr"]["direction"] == "none"
    with pytest.raises(ValueError):
        TrainingRunWriter(
            log_root=tmp_path / "logs",
            project="demo",
            name="bad-direction",
            metric_definitions={"train/loss": {"direction": "up"}},
        )


def test_writer_resume_creates_new_session_and_keeps_metrics(tmp_path: Path) -> None:
    run_directory = tmp_path / "experiments" / "resume-run"
    first = TrainingRunWriter(
        project="写入器测试",
        name="恢复运行",
        run_id="resume-run",
        run_directory=run_directory,
        heartbeat_interval_seconds=0,
    )
    first.start()
    first.log_metrics("train", {"loss": 0.9}, global_step=100, epoch=1)
    first.finish("completed")
    first_metrics = read_jsonl(run_directory / "metrics.jsonl")
    assert len(first_metrics) == 1
    first_session = first_metrics[0]["session_id"]

    second = TrainingRunWriter(
        project="写入器测试",
        name="恢复运行",
        run_id="resume-run",
        run_directory=run_directory,
        resume=True,
        heartbeat_interval_seconds=0,
    )
    second.start()
    second.log_metrics("train", {"loss": 0.7}, global_step=100, epoch=2)
    second.finish("completed")

    metrics = read_jsonl(run_directory / "metrics.jsonl")
    assert len(metrics) == 2
    assert metrics[0]["session_id"] == first_session
    assert metrics[1]["session_id"] != first_session
    events = read_jsonl(run_directory / "events.jsonl")
    statuses = [event["status"] for event in events if event["type"] == "lifecycle"]
    assert statuses == ["started", "completed", "resumed", "completed"]


def test_writer_marks_exception_as_failed(tmp_path: Path) -> None:
    run_directory = tmp_path / "experiments" / "failed-run"
    with pytest.raises(RuntimeError):
        with TrainingRunWriter(
            project="写入器测试",
            name="失败运行",
            run_id="failed-run",
            run_directory=run_directory,
            heartbeat_interval_seconds=0,
        ):
            raise RuntimeError("模拟训练失败")
    events = read_jsonl(run_directory / "events.jsonl")
    assert any(
        event["type"] == "lifecycle" and event["status"] == "failed" for event in events
    )


def test_writer_rejects_invalid_metric_values_and_unsafe_artifact_paths(tmp_path: Path) -> None:
    run = TrainingRunWriter(
        tmp_path / "experiments",
        project="写入器测试",
        name="非法输入",
        run_id="invalid-run",
        heartbeat_interval_seconds=0,
    )
    run.start()
    try:
        with pytest.raises(ValueError):
            run.log_metrics("train", {"loss": float("nan")}, global_step=1)
        with pytest.raises(ValueError):
            run.log_metrics("train", {"loss": 1.0})
        with pytest.raises(ValueError):
            run.log_metrics("train", {"loss": True}, global_step=1)
        with pytest.raises(ValueError):
            run.log_metrics("train", {"loss": 1.0}, global_step=1, wall_time_sec=-1)
        with pytest.raises(ValueError):
            run.log_artifact("../escape.png", artifact_type="image", tag="x")
        with pytest.raises(ValueError):
            run.log_artifact("x.png", artifact_type="image", tag="x", epoch=0)
        with pytest.raises(ValueError):
            run.log_heartbeat(-1)
    finally:
        run.finish("cancelled")
    assert (tmp_path / "experiments" / "invalid-run" / "run.json").is_file()


def test_writer_refuses_existing_directory_without_resume(tmp_path: Path) -> None:
    run_directory = tmp_path / "experiments" / "exists-run"
    first = TrainingRunWriter(
        project="写入器测试",
        name="已存在",
        run_id="exists-run",
        run_directory=run_directory,
        heartbeat_interval_seconds=0,
    )
    first.start()
    first.finish()
    with pytest.raises(FileExistsError):
        TrainingRunWriter(
            project="写入器测试",
            name="已存在",
            run_id="exists-run",
            run_directory=run_directory,
            heartbeat_interval_seconds=0,
        ).start()
