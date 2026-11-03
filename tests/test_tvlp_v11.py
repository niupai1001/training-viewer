from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import REPOSITORY_ROOT

from training_viewer.log_readers.base import InvalidRunDirectoryError
from training_viewer.log_validation import validate_run_directory
from training_viewer.run_metadata import RunMetadataReader
from training_viewer.writer import TrainingRunWriter

DESCRIPTION = {
    "data_description": "Sentinel-2 十波段，10m，split-v1",
    "model_architecture": "SegFormer-B2 / MiT-B2",
    "modification_plan": "输入端波长条件化嵌入，保留原解码器",
    "research_objective": "验证多光谱分割精度与收敛变化",
}


def test_v11_writer_roundtrip_and_schema(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "v11"
    with TrainingRunWriter(
        project="disaster-detection",
        name="Sentinel-2十波段｜SegFormer-B2｜波长条件化输入",
        run_id="v11-run",
        run_directory=run_dir,
        schema_version="1.1",
        experiment_description=DESCRIPTION,
        metric_definitions={
            "val/miou": {
                "display_name": "验证平均交并比",
                "direction": "max",
                "unit": "ratio",
                "category": "validation_score",
                "is_primary": True,
                "default_visibility": True,
            }
        },
        heartbeat_interval_seconds=0,
    ) as writer:
        writer.log_metrics("train", {"loss": 1.0}, global_step=1, epoch=1)

    payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.1"
    assert payload["experiment_description"] == DESCRIPTION
    assert RunMetadataReader().read(run_dir)["experiment_description"]["model_architecture"] == "SegFormer-B2 / MiT-B2"
    report = validate_run_directory(run_dir, REPOSITORY_ROOT / "schemas")
    assert report.error_count == 0, [message.message for message in report.messages]


def test_v11_requires_all_four_sections(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="model_architecture"):
        TrainingRunWriter(
            project="p",
            name="n",
            run_directory=tmp_path / "runs" / "bad",
            schema_version="1.1",
            experiment_description={**DESCRIPTION, "model_architecture": ""},
        )


def test_v10_still_accepts_old_metadata_and_rejects_v11_fields(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "v10"
    with TrainingRunWriter(
        project="p",
        name="v10",
        run_id="v10-run",
        run_directory=run_dir,
        heartbeat_interval_seconds=0,
    ) as writer:
        writer.log_metrics("train", {"loss": 1.0}, global_step=1)
    assert RunMetadataReader().read(run_dir)["schema_version"] == "1.0"
    assert validate_run_directory(run_dir, REPOSITORY_ROOT / "schemas").error_count == 0

    payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    payload["metric_groups"] = {"combo": {"label": "组合"}}
    with pytest.raises(InvalidRunDirectoryError, match="metric_groups"):
        RunMetadataReader().validate(payload)
