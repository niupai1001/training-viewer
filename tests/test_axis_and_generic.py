"""自动横轴、通用日志接入、活动状态与增量扫描。"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from conftest import FIXED_NOW, make_run_directory, metric_record
from training_viewer.application_paths import ApplicationPaths
from training_viewer.indexing.database import IndexDatabase
from training_viewer.service import TrainingViewerService


def test_auto_axis_uses_epoch_when_step_does_not_exist(viewer) -> None:
    service, _ = viewer
    run_directory = make_run_directory(
        Path(service.paths.data_dir).parent / "logs",
        metrics=[
            metric_record("2026-10-31T08:00:00Z", "val", {"miou": 0.4}, epoch=1),
            metric_record("2026-10-31T08:05:00Z", "val", {"miou": 0.5}, epoch=2),
        ],
    )
    service.add_root(str(run_directory.parent))
    run_id = service.queries.list_runs()["runs"][0]["run_id"]
    series = service.queries.query_series(run_id, ["val/miou"], "auto", 100)["series"][0]
    assert series["axis"] == "epoch"
    assert [point["x"] for point in series["points"]] == [1, 2]
    assert series["total_points"] == 2


def test_auto_axis_resolves_per_metric_for_mixed_logs(viewer) -> None:
    service, _ = viewer
    run_directory = make_run_directory(
        Path(service.paths.data_dir).parent / "logs",
        metrics=[
            metric_record("2026-10-31T08:00:00Z", "train", {"loss": 0.9}, global_step=10),
            metric_record("2026-10-31T08:00:00Z", "val", {"miou": 0.4}, epoch=1),
        ],
    )
    service.add_root(str(run_directory.parent))
    run_id = service.queries.list_runs()["runs"][0]["run_id"]
    result = service.queries.query_series(run_id, ["train/loss", "val/miou"], "auto", 100)
    by_key = {series["key"]: series for series in result["series"]}
    assert by_key["train/loss"]["axis"] == "global_step"
    assert by_key["val/miou"]["axis"] == "epoch"
    assert by_key["val/miou"]["points"][0]["x"] == 1


def test_generic_csv_jsonl_and_plain_text_are_discovered(viewer) -> None:
    service, _ = viewer
    root = Path(service.paths.data_dir).parent / "generic-logs"
    run_directory = root / "alpha"
    run_directory.mkdir(parents=True)
    (run_directory / "train.log").write_text(
        "Epoch 1/2 step=100 loss=0.91 val_loss=0.88 val_miou=0.41\n"
        "Epoch 2/2 step=200 loss=0.72 val_loss=0.70 val_miou=0.52\n",
        encoding="utf-8",
    )
    (run_directory / "metrics-export.csv").write_text(
        "epoch,step,train_loss,val_accuracy\n"
        "1,100,0.8,0.61\n"
        "2,200,0.6,0.70\n",
        encoding="utf-8",
    )
    (run_directory / "trace.jsonl").write_text(
        "\n".join(
            json.dumps({"step": step, "epoch": 1, "loss": 1.0 / (step + 1), "accuracy": 0.2 + step / 100})
            for step in (10, 20)
        )
        + "\n",
        encoding="utf-8",
    )
    (run_directory / "business.csv").write_text(
        "name,price,step\nfoo,3.2,1\nbar,4.1,2\n", encoding="utf-8"
    )
    service.add_root(str(root))
    runs = service.queries.list_runs()["runs"]
    assert {run["name"] for run in runs} == {"train", "metrics-export", "trace"}
    plain_text = next(run for run in runs if run["name"] == "train")
    keys = {metric["key"] for metric in service.queries.metric_keys(plain_text["run_id"])}
    assert {"unlabeled/loss", "val/loss", "val/miou"}.issubset(keys)
    assert all(run["source_kind"] != "tvlp" for run in runs)


def test_activity_updates_but_status_does_not_claim_process_is_running(viewer) -> None:
    service, _ = viewer
    logs = Path(service.paths.data_dir).parent / "logs"
    make_run_directory(
        logs / "active",
        run_id="active-run",
        metrics=[metric_record("2026-10-31T08:59:30Z", "train", {"loss": 0.5}, global_step=100)],
    )
    make_run_directory(
        logs / "old",
        run_id="old-run",
        metrics=[metric_record("2026-10-31T06:00:00Z", "train", {"loss": 0.8}, global_step=100)],
    )
    service.add_root(str(logs))
    runs = {run["run_id"]: run for run in service.queries.list_runs()["runs"]}
    assert runs["active-run"]["status"] == "unknown"
    assert runs["active-run"]["activity"] == "updating"
    assert "没有近期心跳" in runs["active-run"]["status_reason"]
    assert runs["old-run"]["activity"] == "idle"


def test_v1_metric_table_is_migrated_without_data_loss(tmp_path: Path) -> None:
    paths = ApplicationPaths.resolve(tmp_path / "data")
    service = TrainingViewerService(paths, now=lambda: FIXED_NOW)
    make_run_directory(
        tmp_path / "logs",
        run_id="migration-run",
        metrics=[metric_record("2026-10-31T08:00:00Z", "train", {"loss": 0.5}, 10, 1)],
    )
    service.add_root(str(tmp_path / "logs"))
    with sqlite3.connect(paths.database_file) as connection:
        before = connection.execute("SELECT COUNT(*) FROM metric_points").fetchone()[0]
        connection.executescript(
            """
            ALTER TABLE metric_points RENAME TO metric_points_v2;
            CREATE TABLE metric_points (
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
            INSERT INTO metric_points SELECT * FROM metric_points_v2;
            DROP TABLE metric_points_v2;
            PRAGMA user_version=1;
            """
        )
    IndexDatabase(paths.database_file).initialize()
    with sqlite3.connect(paths.database_file) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM metric_points").fetchone()[0] == before
        schema = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name='metric_points'"
        ).fetchone()[0]
        assert "phase, metric_name" in schema


def test_incremental_sync_only_reindexes_known_runs_until_full_scan(tmp_path: Path) -> None:
    paths = ApplicationPaths.resolve(tmp_path / "data-incremental")
    service = TrainingViewerService(paths, now=lambda: FIXED_NOW, full_scan_interval_seconds=3600)
    root = tmp_path / "logs-incremental"
    make_run_directory(root, run_id="first-run", metrics=[metric_record("2026-10-31T08:00:00Z", "train", {"loss": 0.5}, 10, 1)])
    service.add_root(str(root))
    assert service.queries.list_runs()["total"] == 1

    make_run_directory(root, run_id="second-run", metrics=[metric_record("2026-10-31T08:01:00Z", "train", {"loss": 0.6}, 20, 1)])
    service.synchronize()
    assert service.queries.list_runs()["total"] == 1
    service.synchronize(force_full=True)
    assert service.queries.list_runs()["total"] == 2
