"""标准训练日志读取器：完整行、半行、坏行、截断与路径安全。"""
from __future__ import annotations

import json
from pathlib import Path

from training_viewer.log_readers.standard_training_log_reader import (
    StandardTrainingLogReader,
)


def _line(record: dict) -> bytes:
    return json.dumps(record, ensure_ascii=False).encode("utf-8")


def _metric_line(step: int, value: float, phase: str = "train", **extra) -> dict:
    record = {
        "timestamp": "2026-10-31T08:00:00Z",
        "session_id": "session-1",
        "global_step": step,
        "phase": phase,
        "metrics": {"loss": value},
    }
    record.update(extra)
    return record


def test_only_complete_lines_are_consumed_and_partial_line_is_completed(tmp_path: Path) -> None:
    run_directory = tmp_path / "run"
    run_directory.mkdir()
    path = run_directory / "metrics.jsonl"
    first = _line(_metric_line(1, 0.9))
    second = _line(_metric_line(2, 0.8))
    path.write_bytes(first + b"\n" + second[:-5])

    reader = StandardTrainingLogReader("metrics")
    first_result = reader.read_new_records(path, run_directory, None)
    assert len(first_result.records) == 1
    assert first_result.cursor is not None
    assert first_result.cursor.offset == len(first) + 1
    assert any("尚未写完" in issue.message for issue in first_result.issues)

    with path.open("ab") as handle:
        handle.write(second[-5:] + b"\n")
    second_result = reader.read_new_records(path, run_directory, first_result.cursor)
    assert len(second_result.records) == 1
    assert second_result.records[0].value == 0.8
    assert second_result.cursor is not None
    assert second_result.cursor.offset == path.stat().st_size


def test_invalid_lines_are_reported_with_line_numbers_and_skipped(tmp_path: Path) -> None:
    run_directory = tmp_path / "run"
    run_directory.mkdir()
    path = run_directory / "metrics.jsonl"
    path.write_bytes(
        _line(_metric_line(1, 0.9))
        + b"\n"
        + b'{"timestamp":"2026-10-31T08:00:00Z","phase":"train","metrics":{"loss":NaN},"global_step":2}\n'
        + _line(_metric_line(3, 0.7))
        + b"\n"
    )
    reader = StandardTrainingLogReader("metrics")
    result = reader.read_new_records(path, run_directory, None)
    assert [record.value for record in result.records] == [0.9, 0.7]
    assert len(result.issues) == 1
    assert result.issues[0].line_number == 2
    assert result.cursor is not None
    assert result.cursor.offset == path.stat().st_size


def test_partial_file_is_read_once_during_session_resume(tmp_path: Path) -> None:
    run_directory = tmp_path / "run"
    run_directory.mkdir()
    path = run_directory / "metrics.jsonl"
    line = _line(_metric_line(1, 0.9))
    path.write_bytes(line + b"\n")
    reader = StandardTrainingLogReader("metrics")
    first = reader.read_new_records(path, run_directory, None)
    second = reader.read_new_records(path, run_directory, first.cursor)
    assert second.records == []
    assert second.cursor is not None
    assert second.cursor.offset == len(line) + 1


def test_invalid_metric_values_and_missing_axis_are_rejected(tmp_path: Path) -> None:
    run_directory = tmp_path / "run"
    run_directory.mkdir()
    path = run_directory / "metrics.jsonl"
    records = [
        {
            "timestamp": "2026-10-31T08:00:00Z",
            "phase": "train",
            "metrics": {"loss": True},
            "global_step": 1,
        },
        {
            "timestamp": "2026-10-31T08:00:00",
            "phase": "train",
            "metrics": {"loss": 1.0},
            "global_step": 1,
        },
        {
            "timestamp": "2026-10-31T08:00:00Z",
            "phase": "train",
            "metrics": {"loss": 1.0},
        },
        {
            "timestamp": "2026-10-31T08:00:00Z",
            "phase": "train",
            "metrics": {},
            "global_step": 1,
        },
        {
            "timestamp": "2026-10-31T08:00:00Z",
            "phase": "train",
            "metrics": {"loss": 1.0},
            "global_step": 1,
            "unknown_field": 1,
        },
    ]
    path.write_bytes(b"".join(_line(record) + b"\n" for record in records))
    result = StandardTrainingLogReader("metrics").read_new_records(
        path, run_directory, None
    )
    assert result.records == []
    assert len(result.issues) == len(records)
    messages = " ".join(issue.message for issue in result.issues)
    assert "数字" in messages
    assert "时区" in messages
    assert "global_step 或 epoch" in messages
    assert "metrics 不能为空" in messages
    assert "未知字段" in messages


def test_artifact_event_path_traversal_is_rejected(tmp_path: Path) -> None:
    run_directory = tmp_path / "run"
    run_directory.mkdir()
    path = run_directory / "events.jsonl"
    artifact = {
        "type": "artifact",
        "timestamp": "2026-10-31T08:00:00Z",
        "path": "../outside.png",
        "artifact_type": "image",
        "tag": "preview",
    }
    path.write_bytes(_line(artifact) + b"\n")
    result = StandardTrainingLogReader("events").read_new_records(
        path, run_directory, None
    )
    assert result.records == []
    assert any("相对路径" in issue.message for issue in result.issues)


def test_truncated_file_resets_cursor(tmp_path: Path) -> None:
    run_directory = tmp_path / "run"
    run_directory.mkdir()
    path = run_directory / "metrics.jsonl"
    path.write_bytes(
        b"".join(_line(_metric_line(step, 0.9 - step / 100)) + b"\n" for step in (1, 2, 3))
    )
    reader = StandardTrainingLogReader("metrics")
    first = reader.read_new_records(path, run_directory, None)
    assert len(first.records) == 3
    path.write_bytes(_line(_metric_line(1, 0.5)) + b"\n")
    result = reader.read_new_records(path, run_directory, first.cursor)
    assert result.reset is True
    assert len(result.records) == 1
    assert result.records[0].value == 0.5
