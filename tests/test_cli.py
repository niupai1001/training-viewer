"""命令行：validate 的成功、失败与 JSON 输出。"""
from __future__ import annotations

import json
import shutil
import socket
from pathlib import Path

from conftest import EXAMPLE_RUNS
from training_viewer.cli import _find_available_port, main


def test_validate_command_accepts_example(tmp_path: Path, capsys) -> None:
    exit_code = main(
        [
            "validate",
            str(EXAMPLE_RUNS / "segformer_baseline"),
            "--data-dir",
            str(tmp_path / "data"),
        ]
    )
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "协议校验通过" in output


def test_validate_command_reports_errors(tmp_path: Path, capsys) -> None:
    run_copy = tmp_path / "run"
    shutil.copytree(EXAMPLE_RUNS / "segformer_baseline", run_copy)
    metadata = json.loads((run_copy / "run.json").read_text(encoding="utf-8"))
    metadata["schema_version"] = "2.0"
    (run_copy / "run.json").write_text(json.dumps(metadata), encoding="utf-8")
    exit_code = main(
        ["validate", str(run_copy), "--data-dir", str(tmp_path / "data")]
    )
    output = capsys.readouterr().out
    assert exit_code == 1
    assert "[ERROR]" in output
    assert "schema_version" in output


def test_validate_command_json_output(tmp_path: Path, capsys) -> None:
    exit_code = main(
        [
            "validate",
            str(EXAMPLE_RUNS / "segformer_baseline"),
            "--json",
            "--data-dir",
            str(tmp_path / "data"),
        ]
    )
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert exit_code == 0
    assert payload["error_count"] == 0
    assert payload["checked_records"] > 0
    assert payload["run_directory"].endswith("segformer_baseline")


def test_port_probe_does_not_pick_an_already_listening_port() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        occupied = listener.getsockname()[1]
        chosen = _find_available_port("127.0.0.1", occupied)
        assert chosen != occupied
