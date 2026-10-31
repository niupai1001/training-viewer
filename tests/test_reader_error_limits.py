"""P0 数据正确性：错误详情截断不能跳过后续有效记录。"""
from __future__ import annotations

import json
from pathlib import Path

from training_viewer.log_readers.csv_metric_reader import CsvMetricLogReader
from training_viewer.log_readers.generic_jsonl_reader import GenericJsonlMetricReader
from training_viewer.log_readers.plain_text_log_reader import PlainTextLogReader
from training_viewer.log_readers.standard_training_log_reader import StandardTrainingLogReader


def _assert_reader_kept_valid_records(result, expected: int = 1000) -> None:
    assert len(result.records) == expected
    assert result.total_issue_count == 60
    assert result.suppressed_issue_count == 10
    assert len(result.issues) == 51
    assert "有效记录未跳过" in result.issues[-1].message


def test_standard_jsonl_continues_after_error_limit(tmp_path: Path) -> None:
    path = tmp_path / "metrics.jsonl"
    lines = [json.dumps({"phase": "train", "global_step": index}) for index in range(60)]
    lines.extend(
        json.dumps(
            {
                "timestamp": "2026-10-31T08:00:00Z",
                "phase": "train",
                "global_step": index,
                "metrics": {"loss": 1.0 / (index + 1)},
            }
        )
        for index in range(1000)
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    reader = StandardTrainingLogReader("metrics")
    first = reader.read_new_records(path, tmp_path, None)
    _assert_reader_kept_valid_records(first)
    second = reader.read_new_records(path, tmp_path, first.cursor)
    assert second.records == []
    assert second.total_issue_count == 0


def test_csv_continues_after_error_limit(tmp_path: Path) -> None:
    path = tmp_path / "metrics.csv"
    rows = ["global_step,loss"] + ["bad,0.5"] * 60
    rows.extend(f"{index},{1.0 / (index + 1)}" for index in range(1000))
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    reader = CsvMetricLogReader()
    first = reader.read_new_records(path, tmp_path, None)
    _assert_reader_kept_valid_records(first)
    second = reader.read_new_records(path, tmp_path, first.cursor)
    assert second.records == []


def test_generic_jsonl_continues_after_error_limit(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    lines = ["not-json"] * 60
    lines.extend(json.dumps({"step": index, "loss": 1.0 / (index + 1)}) for index in range(1000))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    reader = GenericJsonlMetricReader()
    first = reader.read_new_records(path, tmp_path, None)
    _assert_reader_kept_valid_records(first)
    second = reader.read_new_records(path, tmp_path, first.cursor)
    assert second.records == []


def test_plain_text_continues_after_invalid_utf8_lines(tmp_path: Path) -> None:
    path = tmp_path / "train.log"
    payload = b"\xff\xfe broken\n" * 60
    payload += b"".join(
        f"step={index} loss={1.0 / (index + 1):.8f}\n".encode("utf-8")
        for index in range(1000)
    )
    path.write_bytes(payload)
    reader = PlainTextLogReader()
    first = reader.read_new_records(path, tmp_path, None)
    _assert_reader_kept_valid_records(first)
    second = reader.read_new_records(path, tmp_path, first.cursor)
    assert second.records == []


def test_plain_text_crlf_and_multibyte_offsets_are_physical_bytes(tmp_path: Path) -> None:
    path = tmp_path / "train.log"
    first_line = "步骤=1 中文说明；step=1 loss=0.9\r\n".encode("utf-8")
    second_line = "步骤=2 中文说明；step=2 loss=0.8\r\n".encode("utf-8")
    path.write_bytes(first_line + second_line + b"step=3 loss=0.")
    reader = PlainTextLogReader()
    first = reader.read_new_records(path, tmp_path, None)
    assert [point.value for point in first.records] == [0.9, 0.8]
    assert first.cursor is not None
    assert first.cursor.offset == len(first_line + second_line)
    second = reader.read_new_records(path, tmp_path, first.cursor)
    assert second.records == []
    assert "尚未写完" in second.issues[0].message
