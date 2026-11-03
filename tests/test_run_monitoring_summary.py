from __future__ import annotations

from pathlib import Path

from conftest import make_run_directory, metric_record
from training_viewer.application_paths import ApplicationPaths
from training_viewer.service import TrainingViewerService


def _summary(tmp_path: Path, events=None, metrics=None):
    service = TrainingViewerService(ApplicationPaths.resolve(tmp_path / "data"))
    make_run_directory(
        tmp_path / "logs",
        run_id="summary-run",
        metrics=metrics
        or [
            metric_record("2026-10-31T08:05:00Z", "train", {"loss": 1.0}, 1, 1),
            metric_record("2026-10-31T08:15:00Z", "val", {"loss": 0.8, "miou": 0.4}, 2, 1),
            metric_record("2026-10-31T08:25:00Z", "train", {"loss": 0.7, "lr": 0.001}, 3, 1),
        ],
        events=events,
    )
    service.add_root(str(tmp_path / "logs"))
    return service.queries.get_monitoring_summary("summary-run")


def test_summary_uses_lifecycle_active_time_not_metric_span(tmp_path: Path) -> None:
    summary = _summary(
        tmp_path,
        events=[
            {"type": "lifecycle", "status": "started", "timestamp": "2026-10-31T08:00:00Z", "session_id": "s1"},
            {"type": "lifecycle", "status": "completed", "timestamp": "2026-10-31T08:10:00Z", "session_id": "s1"},
            {"type": "lifecycle", "status": "resumed", "timestamp": "2026-10-31T09:00:00Z", "session_id": "s2"},
            {"type": "lifecycle", "status": "completed", "timestamp": "2026-10-31T09:10:00Z", "session_id": "s2"},
        ],
    )
    assert summary["timing"]["active_training_seconds"] == 1200
    assert summary["timing"]["wall_span_seconds"] == 4200
    assert summary["timing"]["source"] == "lifecycle_events"
    assert summary["timing"]["quality"] == "complete"
    assert summary["train_loss"]["latest"]["value"] == 0.7
    assert summary["val_loss"]["latest"]["value"] == 0.8
    assert summary["primary_validation_metric"]["best"]["value"] == 0.4
    assert summary["learning_rate"]["latest"]["value"] == 0.001


def test_summary_without_events_labels_metric_span(tmp_path: Path) -> None:
    summary = _summary(tmp_path)
    assert summary["timing"]["active_training_seconds"] is None
    assert summary["timing"]["source"] == "metric_timestamps"
    assert summary["timing"]["wall_span_seconds"] == 1200
    assert summary["timing"]["quality"] == "partial"


def test_summary_open_session_is_estimate(tmp_path: Path) -> None:
    summary = _summary(
        tmp_path,
        events=[
            {"type": "lifecycle", "status": "started", "timestamp": "2026-10-31T08:00:00Z", "session_id": "s1"},
        ],
        metrics=[
            metric_record("2026-10-31T08:05:00Z", "train", {"loss": 1.0}, 1, 1),
            metric_record("2026-10-31T08:10:00Z", "train", {"loss": 0.9}, 2, 1),
        ],
    )
    assert summary["timing"]["open_session"] is True
    assert summary["timing"]["quality"] == "partial"
    assert summary["timing"]["active_training_seconds"] == 600
