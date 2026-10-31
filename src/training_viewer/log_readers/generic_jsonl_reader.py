"""通用 JSONL 指标读取器。

用于没有 run.json、字段也不完全遵循 TVLP 的 JSONL 日志。支持两种形态：
- 类 TVLP：含 `phase` 与 `metrics` 字典；
- 扁平记录：含 `step`/`epoch` 和若干数值字段，例如 {"step": 10, "loss": 0.5}。
只导入真实存在的数值字段，不推断缺失指标。
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from .base import (
    FileCursor,
    MetricPoint,
    ReadResult,
    file_identity,
    load_json_line,
    parse_timestamp,
    relative_source_path,
)
from .csv_metric_reader import _phase_and_metric_name

_METADATA_KEYS = {
    "timestamp",
    "time",
    "created_at",
    "datetime",
    "global_step",
    "step",
    "iteration",
    "iter",
    "epoch",
    "phase",
    "split",
    "session_id",
    "event_id",
    "wall_time_sec",
    "epoch_progress",
    "context",
    "extensions",
    "metrics",
    "message",
}


def _integer(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("Step/Epoch 不能是布尔值")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            number = float(value.strip())
        except ValueError:
            return None
        return int(number) if number.is_integer() else None
    return None


class GenericJsonlMetricReader:
    """扁平/类 TVLP JSONL → 指标记录；只读新增完整行。"""

    adapter_id = "source.generic_jsonl"
    file_kind = "generic-jsonl"

    def read_new_records(
        self, file_path: Path, run_directory: Path, cursor: FileCursor | None
    ) -> ReadResult:
        result = ReadResult()
        try:
            file_stat = file_path.stat()
        except FileNotFoundError:
            result.add_issue(str(file_path), 0, "JSONL 文件不存在或已被移动", "warning")
            return result
        identity = file_identity(file_stat)
        reset = (
            cursor is None
            or cursor.file_identity != identity
            or file_stat.st_size < cursor.offset
        )
        start_offset = 0 if reset else cursor.offset
        line_number = 1 if reset else cursor.line_number
        result.reset = reset
        with file_path.open("rb") as handle:
            handle.seek(start_offset)
            payload = handle.read()
        last_newline = payload.rfind(b"\n")
        if last_newline < 0:
            complete = b""
            new_offset = start_offset
        else:
            complete = payload[: last_newline + 1]
            new_offset = start_offset + last_newline + 1
        source_file = relative_source_path(run_directory, file_path)
        current_offset = start_offset
        current_line = line_number
        for raw_line in complete.splitlines(keepends=True):
            offset = current_offset
            current_offset += len(raw_line)
            current_line += 1
            if not raw_line.strip():
                continue
            try:
                payload_object = load_json_line(raw_line.strip())
                if not isinstance(payload_object, dict):
                    raise ValueError("每行必须是 JSON 对象")
                records = self._parse_record(
                    payload_object, source_file, offset, current_line - 1
                )
                result.records.extend(records)
            except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
                result.add_issue(
                    str(file_path),
                    current_line - 1,
                    f"第 {current_line - 1} 行无法导入：{error}",
                )
        result.cursor = FileCursor(
            file_path=str(file_path),
            file_kind=self.file_kind,
            file_identity=identity,
            offset=new_offset,
            line_number=current_line,
            size=file_stat.st_size,
            mtime=file_stat.st_mtime,
        )
        if new_offset < file_stat.st_size:
            result.add_issue(
                str(file_path), current_line, "文件末尾存在尚未写完的 JSON 行，等待补齐", "warning"
            )
        result.finalize_issues(str(file_path))
        return result

    def _parse_record(
        self, payload: dict, source_file: str, offset: int, line_number: int
    ) -> list[MetricPoint]:
        timestamp = None
        if payload.get("timestamp") is not None:
            timestamp = parse_timestamp(payload["timestamp"])
        phase = payload.get("phase") or "unlabeled"
        if not isinstance(phase, str) or not phase.strip():
            raise ValueError("phase 必须是非空字符串")
        global_step = _integer(
            payload.get("global_step")
            if payload.get("global_step") is not None
            else payload.get("step")
        )
        epoch = _integer(payload.get("epoch"))
        if global_step is None and epoch is None:
            raise ValueError("记录必须包含 step/global_step 或 epoch")
        if global_step is not None and global_step < 0:
            raise ValueError("global_step 不能为负数")
        if epoch is not None and epoch < 1:
            raise ValueError("epoch 必须从 1 开始")
        session_id = payload.get("session_id")
        if session_id is not None and not isinstance(session_id, str):
            raise ValueError("session_id 必须是字符串")
        metrics = payload.get("metrics")
        if isinstance(metrics, dict):
            metric_items = metrics.items()
            phase_for_metric = phase
        else:
            metric_items = [
                (key, value)
                for key, value in payload.items()
                if key not in _METADATA_KEYS and not key.startswith("_")
            ]
            phase_for_metric = phase
        points: list[MetricPoint] = []
        for metric_name, value in metric_items:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            number = float(value)
            if not math.isfinite(number):
                raise ValueError(f"指标 {metric_name} 必须是有限数字")
            resolved_phase, resolved_name = _phase_and_metric_name(
                phase_for_metric, str(metric_name)
            )
            points.append(
                MetricPoint(
                    phase=resolved_phase,
                    metric_name=resolved_name,
                    value=number,
                    timestamp=timestamp,
                    global_step=global_step,
                    epoch=epoch,
                    session_id=session_id,
                    event_id=None,
                    source_file=source_file,
                    source_offset=offset,
                    line_number=line_number,
                )
            )
        if not points:
            raise ValueError("没有可导入的数值指标")
        return points
