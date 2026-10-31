"""普通文本训练日志读取器。

用规则模板从 `.log` / `.txt` 中提取明确写出的 Step/Epoch 和指标键值，例如：

    Epoch 3/10 step=1200 loss=0.42 val_loss=0.38 miou: 0.61
    {"loss": 0.42, "learning_rate": 1e-4, "epoch": 3}

只提取日志中真实出现的数值；不会补全缺失指标、不会从行号伪造 Step。
覆盖常见 PyTorch / Lightning / Transformers 输出风格，复杂格式需要显式映射。
"""
from __future__ import annotations

import math
import re
from pathlib import Path

from .base import (
    FileCursor,
    MetricPoint,
    ReadResult,
    file_identity,
    parse_timestamp,
    relative_source_path,
)
from .csv_metric_reader import _phase_and_metric_name

MAX_REPORTED_ISSUES_PER_READ = 50
_METRIC_TOKENS = {
    "loss",
    "accuracy",
    "acc",
    "miou",
    "f1",
    "dice",
    "psnr",
    "ssim",
    "lr",
    "learning_rate",
    "precision",
    "recall",
    "auc",
    "mae",
    "mse",
}
_PAIR_RE = re.compile(
    r"['\"]?([A-Za-z][A-Za-z0-9_/]*)['\"]?\s*[:=]\s*"
    r"(-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
)
_EPOCH_RE = re.compile(r"\bepoch\s*[:=]?\s*(\d+)", re.IGNORECASE)
_STEP_RE = re.compile(r"\b(?:global_step|step|iteration|iter)\s*[:=]?\s*(\d+)", re.IGNORECASE)
_PHASE_RE = re.compile(r"\b(?:phase|mode|split)\s*[:=]\s*(train|training|val|valid|validation|test|eval)\b", re.IGNORECASE)
_TIMESTAMP_RE = re.compile(
    r"\[?(\d{4}-\d{2}-\d{2}[T ][0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?(?:Z|[+-]\d{2}:?\d{2})?)\]?"
)
_EXCLUDED_KEYS = {
    "epoch",
    "step",
    "global_step",
    "iteration",
    "iter",
    "batch",
    "batch_size",
    "epochs",
    "time",
    "wall_time",
    "duration",
    "phase",
    "mode",
    "split",
}


def _is_metric_key(value: str) -> bool:
    lowered = value.strip().lower()
    base = lowered.rsplit("/", 1)[-1]
    if base in _METRIC_TOKENS:
        return True
    for suffix in ("_loss", "_accuracy", "_acc", "_miou", "_f1", "_lr", "_precision", "_recall"):
        if base.endswith(suffix) and base[: -len(suffix)]:
            return True
    return False


def _number(value: str) -> float | None:
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _integer_value(value: str | None) -> int | None:
    number = _number(value) if value is not None else None
    if number is None or not number.is_integer():
        return None
    return int(number)


class PlainTextLogReader:
    """规则模板文本日志读取器：文本行 → 指标记录。"""

    adapter_id = "source.plain_text_log"
    file_kind = "plain-text"

    @classmethod
    def looks_like_training_log(cls, file_path: Path, max_lines: int = 120) -> bool:
        try:
            with file_path.open("r", encoding="utf-8", errors="replace") as handle:
                for index, line in enumerate(handle):
                    if index >= max_lines:
                        break
                    if cls._parse_line(line, "candidate", 0, index + 1):
                        return True
        except OSError:
            return False
        return False

    @staticmethod
    def _parse_line(
        line: str, source_file: str, offset: int, line_number: int
    ) -> list[MetricPoint]:
        values = {
            key.lower(): value for key, value in _PAIR_RE.findall(line)
        }
        metric_values = {
            key: value
            for key, value in values.items()
            if _is_metric_key(key) and key.lower() not in _EXCLUDED_KEYS
        }
        if not metric_values:
            return []
        epoch_match = _EPOCH_RE.search(line)
        step_match = _STEP_RE.search(line)
        epoch = int(epoch_match.group(1)) if epoch_match else None
        global_step = int(step_match.group(1)) if step_match else None
        if epoch is None and values.get("epoch") is not None:
            epoch = _integer_value(values["epoch"])
        if global_step is None:
            global_step = _integer_value(
                values.get("global_step") or values.get("step") or values.get("iteration")
            )
        if epoch is None and global_step is None:
            return []
        if epoch is not None and epoch < 1:
            epoch = None
        phase_match = _PHASE_RE.search(line)
        explicit_phase = phase_match.group(1).lower() if phase_match else "unlabeled"
        if explicit_phase == "training":
            explicit_phase = "train"
        elif explicit_phase in ("valid", "validation"):
            explicit_phase = "val"
        timestamp = None
        timestamp_match = _TIMESTAMP_RE.search(line)
        if timestamp_match:
            candidate = timestamp_match.group(1).replace(" ", "T")
            try:
                timestamp = parse_timestamp(candidate)
            except ValueError:
                timestamp = None
        points: list[MetricPoint] = []
        for key, raw_value in metric_values.items():
            value = _number(raw_value)
            if value is None:
                continue
            phase, metric_name = _phase_and_metric_name(explicit_phase, key)
            points.append(
                MetricPoint(
                    phase=phase,
                    metric_name=metric_name,
                    value=value,
                    timestamp=timestamp,
                    global_step=global_step,
                    epoch=epoch,
                    session_id=None,
                    event_id=None,
                    source_file=source_file,
                    source_offset=offset,
                    line_number=line_number,
                )
            )
        return points

    def read_new_records(
        self, file_path: Path, run_directory: Path, cursor: FileCursor | None
    ) -> ReadResult:
        result = ReadResult()
        try:
            file_stat = file_path.stat()
        except FileNotFoundError:
            result.add_issue(str(file_path), 0, "文本日志不存在或已被移动", "warning")
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
        with file_path.open("r", encoding="utf-8", errors="replace") as handle:
            handle.seek(start_offset)
            text = handle.read()
        last_newline = text.rfind("\n")
        if last_newline < 0:
            complete = ""
            new_offset = start_offset
        else:
            complete = text[: last_newline + 1]
            new_offset = start_offset + len(complete.encode("utf-8", errors="replace"))
        source_file = relative_source_path(run_directory, file_path)
        reported = 0
        current_offset = start_offset
        current_line = line_number
        for raw_line in complete.splitlines(keepends=True):
            offset = current_offset
            current_offset += len(raw_line.encode("utf-8", errors="replace"))
            current_line += 1
            if reported >= MAX_REPORTED_ISSUES_PER_READ:
                continue
            try:
                records = self._parse_line(raw_line.rstrip("\r\n"), source_file, offset, current_line - 1)
                result.records.extend(records)
            except (ValueError, UnicodeError) as error:
                reported += 1
                result.add_issue(
                    str(file_path),
                    current_line - 1,
                    f"第 {current_line - 1} 行无法解析：{error}",
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
                str(file_path), current_line, "文件末尾行尚未写完，等待补齐", "warning"
            )
        return result
