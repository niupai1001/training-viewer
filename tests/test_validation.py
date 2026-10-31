"""协议校验器：示例通过、坏字段、半行、缺失产物与路径穿越。"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from conftest import EXAMPLE_RUNS
from training_viewer.application_paths import ApplicationPaths
from training_viewer.log_validation import validate_run_directory

BASELINE = EXAMPLE_RUNS / "segformer_baseline"


def test_example_run_validates_without_errors(tmp_path: Path) -> None:
    schema_directory = ApplicationPaths.resolve(tmp_path / "data").schema_dir
    report = validate_run_directory(BASELINE, schema_directory)
    assert report.error_count == 0, [message.__dict__ for message in report.messages]
    assert report.checked_records > 0


def test_packaged_schemas_match_repository_schemas(tmp_path: Path) -> None:
    schema_directory = ApplicationPaths.resolve(tmp_path / "data").schema_dir
    repository_schemas = Path(__file__).resolve().parents[1] / "schemas"
    for name in ("run.schema.json", "metrics.schema.json", "events.schema.json"):
        assert (schema_directory / name).read_bytes() == (repository_schemas / name).read_bytes(), (
            f"{name} 在安装包与仓库 schemas/ 之间不一致，请同步后重新测试"
        )


def test_broken_run_json_reports_schema_error(tmp_path: Path) -> None:
    run_copy = tmp_path / "run"
    shutil.copytree(BASELINE, run_copy)
    metadata = json.loads((run_copy / "run.json").read_text(encoding="utf-8"))
    metadata.pop("name")
    (run_copy / "run.json").write_text(json.dumps(metadata), encoding="utf-8")
    report = validate_run_directory(
        run_copy, ApplicationPaths.resolve(tmp_path / "data").schema_dir
    )
    assert report.error_count >= 1
    assert any("name" in message.message for message in report.messages)


def test_partial_jsonl_line_is_informational_not_error(tmp_path: Path) -> None:
    run_copy = tmp_path / "run"
    shutil.copytree(BASELINE, run_copy)
    with (run_copy / "metrics.jsonl").open("ab") as handle:
        handle.write(b'{"timestamp":"2026-10-31T08:03:00Z","phase":"train"')
    report = validate_run_directory(
        run_copy, ApplicationPaths.resolve(tmp_path / "data").schema_dir
    )
    assert report.error_count == 0
    assert any("尚未写完" in message.message for message in report.messages)


def test_missing_artifact_is_warning(tmp_path: Path) -> None:
    run_copy = tmp_path / "run"
    shutil.copytree(BASELINE, run_copy)
    (run_copy / "artifacts" / "predictions" / "sample-001.png").unlink()
    report = validate_run_directory(
        run_copy, ApplicationPaths.resolve(tmp_path / "data").schema_dir
    )
    assert report.error_count == 0
    assert any("不存在" in message.message for message in report.messages)


def test_artifact_path_traversal_is_error(tmp_path: Path) -> None:
    run_copy = tmp_path / "run"
    shutil.copytree(BASELINE, run_copy)
    event = {
        "type": "artifact",
        "timestamp": "2026-10-31T08:10:00Z",
        "path": "../escape.png",
        "artifact_type": "image",
        "tag": "preview",
    }
    with (run_copy / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event) + "\n")
    report = validate_run_directory(
        run_copy, ApplicationPaths.resolve(tmp_path / "data").schema_dir
    )
    assert report.error_count >= 1
    assert any("相对路径" in message.message for message in report.messages)
