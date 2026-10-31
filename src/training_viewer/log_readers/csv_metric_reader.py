"""逗号分隔值（CSV）指标日志读取器。

只读取用户在显式映射中指定的列，或全部能稳定解析为数字的列。
不猜测阶段含义、不填补缺失的 Step/Epoch，也不修改 CSV 文件本身。
"""
from __future__ import annotations

import csv
import math
from pathlib import Path

from .base import (
    FileCursor,
    MetricPoint,
    ParseIssue,
    ReadResult,
    file_identity,
    parse_timestamp,
    relative_source_path,
    timestamp_from_epoch_seconds,
)

MAX_REPORTED_ISSUES_PER_READ = 50

_STEP_ALIASES = ("global_step", "step", "iteration", "iter", "iters")
_EPOCH_ALIASES = ("epoch", "epochs")
_TIMESTAMP_ALIASES = ("timestamp", "time", "wall_time", "date", "datetime")
_PHASE_ALIASES = ("phase", "mode", "split")
_SESSION_ALIASES = ("session_id", "session", "run_id", "run")

_KNOWN_COLUMN_KEYS = {
    "step_column",
    "epoch_column",
    "timestamp_column",
    "phase_column",
    "session_column",
    "metric_columns",
}


def _normalize_header(value: str) -> str:
    return value.strip().lstrip("\ufeff").lower()


def _find_column(headers: list[str], aliases: tuple[str, ...]) -> int | None:
    normalized = [_normalize_header(header) for header in headers]
    for alias in aliases:
        if alias in normalized:
            return normalized.index(alias)
    return None


def _parse_float(value: str) -> float | None:
    text = value.strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if not math.isfinite(number):
        return None
    return number


def _parse_integer(value: str) -> int | None:
    number = _parse_float(value)
    if number is None or not number.is_integer():
        return None
    return int(number)


def _parse_timestamp_cell(value: str) -> str | None:
    text = value.strip()
    if not text:
        return None
    try:
        return parse_timestamp(text)
    except ValueError:
        pass
    try:
        seconds = float(text)
    except ValueError:
        return None
    if not math.isfinite(seconds):
        return None
    return timestamp_from_epoch_seconds(seconds)


class CsvMetricLogReader:
    """CSV 指标读取器：`metrics.csv` → 规范化指标记录。"""

    adapter_id = "source.csv_metric_log"
    file_kind = "csv"

    def __init__(self, column_mapping: dict | None = None, delimiter: str | None = None):
        self.column_mapping = column_mapping or {}
        self.delimiter = delimiter or ","
        if self.delimiter not in (",", "\t", ";"):
            raise ValueError(f"不支持的 CSV 分隔符：{self.delimiter!r}")
        unknown_keys = sorted(set(self.column_mapping) - _KNOWN_COLUMN_KEYS)
        if unknown_keys:
            raise ValueError(f"CSV 列映射含未知配置项：{', '.join(unknown_keys)}")

    def _resolve_columns(self, headers: list[str], issues: list[ParseIssue], file_path: Path) -> dict:
        mapping = self.column_mapping
        resolved: dict[str, int | list[int] | None] = {
            "step": None,
            "epoch": None,
            "timestamp": None,
            "phase": None,
            "session": None,
            "metrics": [],
        }
        explicit = {
            "step": mapping.get("step_column"),
            "epoch": mapping.get("epoch_column"),
            "timestamp": mapping.get("timestamp_column"),
            "phase": mapping.get("phase_column"),
            "session": mapping.get("session_column"),
        }
        normalized = {_normalize_header(header): index for index, header in enumerate(headers)}
        for role, column_name in explicit.items():
            if column_name is None:
                continue
            index = normalized.get(_normalize_header(str(column_name)))
            if index is None:
                issues.append(
                    ParseIssue(
                        str(file_path),
                        1,
                        f"CSV 列映射指定的 {role}_column={column_name!r} 不存在；"
                        "本文件暂不导入指标，请修正 run.json 的 extensions.csv_metric_mapping",
                    )
                )
                raise ValueError(f"CSV 列映射指定的列不存在：{column_name!r}")
            resolved[role] = index

        if resolved["step"] is None and resolved["epoch"] is None:
            resolved["step"] = _find_column(headers, _STEP_ALIASES)
            resolved["epoch"] = _find_column(headers, _EPOCH_ALIASES)
        if resolved["timestamp"] is None:
            resolved["timestamp"] = _find_column(headers, _TIMESTAMP_ALIASES)
        if resolved["phase"] is None:
            resolved["phase"] = _find_column(headers, _PHASE_ALIASES)
        if resolved["session"] is None:
            resolved["session"] = _find_column(headers, _SESSION_ALIASES)

        explicit_metrics = mapping.get("metric_columns")
        if explicit_metrics is not None:
            metric_indexes: list[int] = []
            for column_name in explicit_metrics:
                index = normalized.get(_normalize_header(str(column_name)))
                if index is None:
                    issues.append(
                        ParseIssue(
                            str(file_path),
                            1,
                            f"CSV 列映射指定的指标列不存在：{column_name!r}",
                        )
                    )
                    raise ValueError(f"CSV 指标列不存在：{column_name!r}")
                metric_indexes.append(index)
            resolved["metrics"] = metric_indexes
        return resolved

    def read_new_records(
        self, file_path: Path, run_directory: Path, cursor: FileCursor | None
    ) -> ReadResult:
        result = ReadResult()
        try:
            file_stat = file_path.stat()
        except FileNotFoundError:
            result.add_issue(str(file_path), 0, "CSV 文件不存在或已被移动", "warning")
            return result

        identity = file_identity(file_stat)
        reset = (
            cursor is None
            or cursor.file_identity != identity
            or file_stat.st_size < cursor.size
        )
        start_row = 0 if reset else cursor.offset
        result.reset = reset
        source_file = relative_source_path(run_directory, file_path)

        try:
            with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.reader(handle, delimiter=self.delimiter)
                headers = next(reader, None)
                if headers is None:
                    result.add_issue(str(file_path), 0, "CSV 文件为空", "warning")
                    result.cursor = FileCursor(
                        str(file_path), self.file_kind, identity, 0, 1, file_stat.st_size, file_stat.st_mtime
                    )
                    return result
                try:
                    columns = self._resolve_columns(headers, result.issues, file_path)
                except ValueError:
                    result.cursor = FileCursor(
                        str(file_path), self.file_kind, identity, 0, 1, file_stat.st_size, file_stat.st_mtime
                    )
                    return result
        except UnicodeDecodeError as error:
            result.add_issue(str(file_path), 0, f"CSV 不是有效的 UTF-8：{error}")
            return result

        metric_indexes = list(columns["metrics"])
        metric_names = [headers[index] for index in metric_indexes]

        if not metric_indexes:
            known = {columns[key] for key in ("step", "epoch", "timestamp", "phase", "session")}
            metric_indexes = []
            for index in range(len(headers)):
                if index in known:
                    continue
                if self._column_is_numeric(file_path, index, self.delimiter):
                    metric_indexes.append(index)
            metric_names = [headers[index] for index in metric_indexes]

        if not metric_indexes:
            result.add_issue(
                str(file_path),
                0,
                "CSV 没有可导入的数值指标列；请检查表头，或在 run.json 的 "
                "extensions.csv_metric_mapping 中指定 metric_columns",
            )

        step_index = columns["step"]
        epoch_index = columns["epoch"]
        timestamp_index = columns["timestamp"]
        phase_index = columns["phase"]
        session_index = columns["session"]
        if step_index is None and epoch_index is None:
            result.add_issue(
                str(file_path),
                0,
                "CSV 缺少 step/global_step 或 epoch 列，无法建立训练横轴；"
                "请在 run.json 的 extensions.csv_metric_mapping 中指定列名",
            )

        row_index = 0
        reported = 0
        try:
            with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.reader(handle, delimiter=self.delimiter)
                next(reader, None)
                for row in reader:
                    current_row = row_index
                    row_index += 1
                    if current_row < start_row:
                        continue
                    if not any(cell.strip() for cell in row):
                        continue
                    if reported >= MAX_REPORTED_ISSUES_PER_READ:
                        continue
                    line_number = current_row + 2
                    try:
                        global_step = (
                            _parse_integer(row[step_index]) if step_index is not None and step_index < len(row) else None
                        )
                        epoch = (
                            _parse_integer(row[epoch_index]) if epoch_index is not None and epoch_index < len(row) else None
                        )
                        if step_index is not None and global_step is None and (row[step_index].strip() if step_index < len(row) else ""):
                            raise ValueError(f"global_step 不是整数：{row[step_index]!r}")
                        if epoch_index is not None and epoch is None and (row[epoch_index].strip() if epoch_index < len(row) else ""):
                            raise ValueError(f"epoch 不是整数：{row[epoch_index]!r}")
                        if global_step is None and epoch is None:
                            raise ValueError("该行缺少 global_step 与 epoch")
                        if global_step is not None and global_step < 0:
                            raise ValueError("global_step 不能为负数")
                        if epoch is not None and epoch < 1:
                            raise ValueError("epoch 必须从 1 开始")
                        timestamp = None
                        if timestamp_index is not None and timestamp_index < len(row):
                            timestamp = _parse_timestamp_cell(row[timestamp_index])
                            if row[timestamp_index].strip() and timestamp is None:
                                result.add_issue(
                                    str(file_path),
                                    line_number,
                                    f"时间戳无法解析，该行按无时间戳导入：{row[timestamp_index]!r}",
                                    "warning",
                                )
                        phase = "unlabeled"
                        if phase_index is not None and phase_index < len(row) and row[phase_index].strip():
                            phase = row[phase_index].strip()
                        session_id = None
                        if session_index is not None and session_index < len(row) and row[session_index].strip():
                            session_id = row[session_index].strip()
                        for metric_index, metric_name in zip(metric_indexes, metric_names):
                            if metric_index >= len(row):
                                continue
                            value = _parse_float(row[metric_index])
                            if value is None:
                                continue
                            metric_phase, final_metric_name = _phase_and_metric_name(
                                phase, metric_name
                            )
                            result.records.append(
                                MetricPoint(
                                    phase=metric_phase,
                                    metric_name=final_metric_name,
                                    value=value,
                                    timestamp=timestamp or None,
                                    global_step=global_step,
                                    epoch=epoch,
                                    session_id=session_id,
                                    event_id=None,
                                    source_file=source_file,
                                    source_offset=current_row,
                                    line_number=line_number,
                                )
                            )
                    except (ValueError, IndexError) as error:
                        reported += 1
                        result.add_issue(
                            str(file_path), line_number, f"第 {line_number} 行无法导入：{error}"
                        )
        except UnicodeDecodeError as error:
            result.add_issue(str(file_path), row_index + 2, f"CSV 不是有效的 UTF-8：{error}")

        if reported >= MAX_REPORTED_ISSUES_PER_READ:
            result.add_issue(
                str(file_path), 0, "本文件一次读取错误过多，其余错误已省略", "warning"
            )
        result.cursor = FileCursor(
            file_path=str(file_path),
            file_kind=self.file_kind,
            file_identity=identity,
            offset=row_index,
            line_number=row_index + 2,
            size=file_stat.st_size,
            mtime=file_stat.st_mtime,
        )
        return result

    @staticmethod
    def _column_is_numeric(file_path: Path, column_index: int, delimiter: str = ",") -> bool:
        """判断一列是否全部为非空数字；混合内容列不当作指标。"""
        saw_value = False
        try:
            with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.reader(handle, delimiter=delimiter)
                next(reader, None)
                for row in reader:
                    if column_index >= len(row) or not row[column_index].strip():
                        continue
                    if _parse_float(row[column_index]) is None:
                        return False
                    saw_value = True
        except (OSError, UnicodeDecodeError):
            return False
        return saw_value


_PHASE_PREFIXES = {
    "train": "train",
    "training": "train",
    "val": "val",
    "valid": "val",
    "validation": "val",
    "test": "test",
    "eval": "eval",
}


def _phase_and_metric_name(phase: str, metric_name: str) -> tuple[str, str]:
    """有阶段列时保留原列名；没有阶段时从 train_/val_ 前缀推导（不伪造指标）。"""
    if phase != "unlabeled":
        return phase, metric_name
    normalized = metric_name.strip()
    lowered = normalized.lower()
    for prefix, phase_name in _PHASE_PREFIXES.items():
        token = f"{prefix}_"
        if lowered.startswith(token) and len(normalized) > len(token):
            return phase_name, normalized[len(token):]
    return phase, metric_name
