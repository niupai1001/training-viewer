"""测试公共设备：临时日志目录、可注入时钟的服务实例、TestClient。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from training_viewer.api.app import create_application
from training_viewer.application_paths import ApplicationPaths
from training_viewer.service import TrainingViewerService

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_RUNS = REPOSITORY_ROOT / "examples"
FIXED_NOW = datetime(2026, 10, 31, 9, 0, 0, tzinfo=timezone.utc)


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def make_run_directory(
    parent: Path,
    run_id: str = "run-0001",
    name: str = "测试运行",
    metrics: list[dict] | None = None,
    events: list[dict] | None = None,
    **overrides,
) -> Path:
    run_directory = parent / f"run_{run_id}"
    run_directory.mkdir(parents=True, exist_ok=True)
    metadata = {
        "schema_version": "1.0",
        "run_id": run_id,
        "project": "测试项目",
        "experiment": "测试实验组",
        "name": name,
        "created_at": "2026-10-31T08:00:00Z",
        "task": "semantic-segmentation",
        "model": {"name": "测试模型"},
        "dataset": {"name": "测试数据集", "version": "v1", "split_definition": "split-v1"},
        "config": {"epochs": 3, "batch_size": 4, "optimizer": {"lr": 0.001}},
        "source": {"seed": 42},
        "tags": ["unit-test"],
        "metric_definitions": {
            "train/loss": {"direction": "min", "unit": "none"},
            "val/miou": {"direction": "max", "unit": "ratio", "definition": "classes 0..4"},
        },
    }
    metadata.update(overrides)
    (run_directory / "run.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if metrics is not None:
        write_jsonl(run_directory / "metrics.jsonl", metrics)
    if events is not None:
        write_jsonl(run_directory / "events.jsonl", events)
    return run_directory


def metric_record(
    timestamp: str,
    phase: str,
    metrics: dict,
    global_step: int | None = None,
    epoch: int | None = None,
    session_id: str = "session-1",
) -> dict:
    record = {
        "timestamp": timestamp,
        "session_id": session_id,
        "phase": phase,
        "metrics": metrics,
    }
    if global_step is not None:
        record["global_step"] = global_step
    if epoch is not None:
        record["epoch"] = epoch
    return record


@pytest.fixture
def viewer(tmp_path: Path):
    paths = ApplicationPaths.resolve(tmp_path / "app-data")
    service = TrainingViewerService(paths, now=lambda: FIXED_NOW)
    yield service, paths
    service.stop_background_sync()


@pytest.fixture
def client(viewer):
    service, paths = viewer
    application = create_application(paths, service, start_background_sync=False)
    with TestClient(application) as test_client:
        yield test_client, service
