from __future__ import annotations

from pathlib import Path

from conftest import make_run_directory, metric_record
from training_viewer.application_paths import ApplicationPaths
from training_viewer.service import TrainingViewerService


def _service(tmp_path: Path) -> TrainingViewerService:
    service = TrainingViewerService(ApplicationPaths.resolve(tmp_path / "data"))
    directory = tmp_path / "logs"
    records = []
    for step in range(1, 6):
        records.append(metric_record("2026-10-31T08:00:00Z", "train", {"loss": 1.0 / step}, step, 1))
    for step in range(1, 4):
        records.append(metric_record("2026-10-31T08:00:01Z", "val", {"loss": 1.1 / step, "miou": step / 10}, step, 1))
    records.append(metric_record("2026-10-31T08:00:02Z", "train", {"epoch_QUIVALENT": 1.0}, 1, 1))
    records.append(metric_record("2026-10-31T08:00:02Z", "train", {"epoch_QUIVALENT": 2.0}, 2, 1))
    records.append(metric_record("2026-10-31T08:00:03Z", "train", {"repeat": 1.0}, 9, 1))
    records.append(metric_record("2026-10-31T08:00:03Z", "train", {"repeat": 2.0}, 9, 1))
    records.append(metric_record("2026-10-31T08:00:03Z", "train", {"repeat": 3.0}, 9, 1))
    records.append(metric_record("2026-10-31T08:00:04Z", "train", {"capacity/peak_gpu_MiB": 1024}, 1, 1))
    records.append(metric_record("2026-10-31T08:00:04Z", "train", {"capacity/peak_gpu_MiB": 2048}, 2, 1))
    records.append(metric_record("2026-10-31T08:00:05Z", "val", {"combo_SWIR_pair/L8/SR_B6/mae": 0.3}, 7, 1))
    records.append(metric_record("2026-10-31T08:00:05Z", "val", {"combo_SWIR_pair/L8/SR_B6/rmse": 0.4}, 7, 1))
    make_run_directory(
        directory,
        run_id="catalog-run",
        metrics=records,
        metric_definitions={
            "train/loss": {"display_name": "训练损失", "direction": "min", "unit": "none"},
            "val/loss": {"display_name": "验证损失", "direction": "min", "unit": "none"},
            "val/miou": {
                "display_name": "验证平均交并比",
                "direction": "max",
                "unit": "ratio",
            },
        },
    )
    service.add_root(str(tmp_path / "logs"))
    return service


def _catalog(tmp_path: Path) -> dict:
    return _service(tmp_path).queries.metric_catalog("catalog-run", limit=100)


def test_catalog_splits_single_point_and_repeated_x(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    items = {item["raw_key"]: item for item in catalog["items"]}
    assert items["train/loss"]["value_kind"] == "continuous"
    assert items["train/loss"]["role"] == "train_loss"
    assert items["val/loss"]["role"] == "val_loss"
    assert items["val/miou"]["role"] == "validation_score"
    assert items["val/miou"]["source"] == "declared"
    assert items["train/repeat"]["value_kind"] == "single_point"
    assert items["train/repeat"]["distinct_x_count"] == 1
    assert items["val/combo_SWIR_pair/L8/SR_B6/mae"]["value_kind"] == "single_point"
    assert items["val/combo_SWIR_pair/L8/SR_B6/mae"]["semantic_group"] == "evaluation"
    assert items["train/capacity/peak_gpu_MiB"]["category"] == "performance"


def test_catalog_does_not_guess_unknown_fields(tmp_path: Path) -> None:
    items = {item["raw_key"]: item for item in _catalog(tmp_path)["items"]}
    unknown = items["train/epoch_QUIVALENT"]
    assert unknown["source"] == "unknown"
    assert unknown["display_name_zh"] == "epoch_QUIVALENT"
    assert unknown["direction"] == "none"
    assert unknown["role"] == "other"


def test_catalog_search_filter_and_cursor(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    service = _service(tmp_path)
    rmse = service.queries.metric_catalog("catalog-run", query="rmse")
    assert rmse["total"] == 1
    assert rmse["items"][0]["value_kind"] == "single_point"
    path_hit = service.queries.metric_catalog("catalog-run", query="SR_B6")
    assert path_hit["total"] == 2
    miou = service.queries.metric_catalog("catalog-run", query="训练损失")
    assert miou["total"] == 1
    first = service.queries.metric_catalog("catalog-run", limit=2)
    assert first["total"] == catalog["total"]
    assert len(first["items"]) == 2
    assert first["next_cursor"] == 2
    second = service.queries.metric_catalog("catalog-run", limit=2, cursor=2)
    assert len(second["items"]) == 2
    assert first["items"][0]["raw_key"] != second["items"][0]["raw_key"]


def test_catalog_thousand_single_point_fields_is_paged(tmp_path: Path) -> None:
    service = TrainingViewerService(ApplicationPaths.resolve(tmp_path / "data"))
    metrics = {f"combo_SWIR_pair/L8/SR_B6/field_{index}": float(index) for index in range(1000)}
    make_run_directory(
        tmp_path / "logs",
        run_id="many-metrics",
        metrics=[metric_record("2026-10-31T08:00:00Z", "val", metrics, 1, 1)],
    )
    service.add_root(str(tmp_path / "logs"))
    first = service.queries.metric_catalog("many-metrics", limit=40)
    assert first["total"] == 1000
    assert len(first["items"]) == 40
    assert first["next_cursor"] == 40
    assert all(item["value_kind"] == "single_point" for item in first["items"])
    search = service.queries.metric_catalog("many-metrics", query="field_99", limit=40)
    assert search["total"] == 11  # field_99, field_990..field_999
    assert len(search["items"]) <= 40
