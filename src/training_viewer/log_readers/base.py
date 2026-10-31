"""日志读取器的公共数据结构和文件游标。

读取器只负责把“文件新增的完整行”转换成与来源无关的标准化记录；
它不写数据库、不生成界面数据，也不修改原始文件。
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Union

SCHEMA_VERSION = "1.0"

RecordSeverity = Literal["error", "warning"]


class ReaderUnavailableError(RuntimeError):
    """日志来源所需的可选依赖未安装。"""


class InvalidRunDirectoryError(ValueError):
    """目录中的运行元数据不满足 TVLP 1.0。"""


@dataclass(frozen=True, slots=True)
class ParseIssue:
    """一条解析或校验问题。行号从 1 开始，文件级问题使用 0。"""

    file_path: str
    line_number: int
    message: str
    severity: RecordSeverity = "error"


@dataclass(frozen=True, slots=True)
class MetricPoint:
    phase: str
    metric_name: str
    value: float
    timestamp: str | None
    global_step: int | None
    epoch: int | None
    session_id: str | None
    event_id: str | None
    source_file: str
    source_offset: int
    line_number: int


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    path: str
    artifact_type: str
    tag: str
    timestamp: str
    phase: str | None
    global_step: int | None
    epoch: int | None
    group_id: str | None
    sample_id: str | None
    role: str | None
    mime_type: str | None
    metadata: dict
    session_id: str | None
    event_id: str | None
    source_file: str
    source_offset: int
    line_number: int


@dataclass(frozen=True, slots=True)
class LifecycleRecord:
    status: str
    timestamp: str
    session_id: str | None
    message: str | None
    event_id: str | None
    source_file: str
    source_offset: int
    line_number: int


@dataclass(frozen=True, slots=True)
class HeartbeatRecord:
    timestamp: str
    session_id: str | None
    global_step: int | None
    event_id: str | None
    source_file: str
    source_offset: int
    line_number: int


NormalizedRecord = Union[MetricPoint, ArtifactRecord, LifecycleRecord, HeartbeatRecord]


@dataclass(frozen=True, slots=True)
class FileCursor:
    """一个日志文件已经消费到的位置。

    offset 的语义由读取器决定：标准 JSONL 使用字节偏移，CSV 使用数据行号，
    TensorBoard 事件文件使用事件序号。line_number 只用于报告问题。
    """

    file_path: str
    file_kind: str
    file_identity: str
    offset: int
    line_number: int
    size: int
    mtime: float


@dataclass(slots=True)
class ReadResult:
    records: list[NormalizedRecord] = field(default_factory=list)
    issues: list[ParseIssue] = field(default_factory=list)
    cursor: FileCursor | None = None
    reset: bool = False

    def add_issue(self, file_path: str, line_number: int, message: str, severity: str = "error") -> None:
        self.issues.append(ParseIssue(file_path, line_number, message, severity))  # type: ignore[arg-type]


def utc_now_iso() -> str:
    return format_timestamp(datetime.now(timezone.utc))


def format_timestamp(value: datetime) -> str:
    """统一成固定宽度 UTC 字符串，保证 SQLite 中的字典序等于时间顺序。"""
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def parse_timestamp(value: object, field_name: str = "timestamp") -> str:
    """解析带时区的 RFC 3339 时间并转为 UTC 字符串。"""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 必须是非空字符串")
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise ValueError(f"{field_name} 不是合法的 RFC 3339 时间：{value!r}") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} 缺少时区，协议要求带时区的 RFC 3339 时间")
    return format_timestamp(parsed)


def timestamp_from_epoch_seconds(value: float) -> str:
    return format_timestamp(datetime.fromtimestamp(value, tz=timezone.utc))


def epoch_seconds_from_iso(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def load_json_line(raw: bytes) -> object:
    """解析一行 JSON；拒绝 NaN/Infinity，它们是无效 JSON 数字。"""

    def reject_constant(text: str) -> float:
        raise ValueError(f"不允许的非有限数字：{text}")

    return json.loads(raw.decode("utf-8"), parse_constant=reject_constant)


def require_object(value: object, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} 必须是 JSON 对象")
    return value


def require_string(value: object, field_name: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} 必须是字符串")
    if not allow_empty and not value.strip():
        raise ValueError(f"{field_name} 不能为空")
    return value


def optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return require_string(value, field_name)


def optional_integer(value: object, field_name: str, minimum: int | None = None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} 必须是整数")
    if minimum is not None and value < minimum:
        raise ValueError(f"{field_name} 不能小于 {minimum}")
    return value


def optional_number(value: object, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} 必须是数字")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field_name} 必须是有限数字")
    return number


def optional_object(value: object, field_name: str) -> dict:
    if value is None:
        return {}
    return require_object(value, field_name)


def file_identity(stat_result) -> str:
    """文件身份用于检测日志被替换或轮转；inode 在 Windows 上同样可用。"""
    identity = getattr(stat_result, "st_ino", 0)
    if identity:
        return f"{stat_result.st_dev}:{identity}"
    return f"{stat_result.st_dev}:{stat_result.st_ctime_ns}"


def relative_source_path(run_directory: Path, file_path: Path) -> str:
    """数据库中保存相对 Run 目录的路径，便于整体移动后仍能显示来源。"""
    try:
        return file_path.resolve().relative_to(run_directory.resolve()).as_posix()
    except ValueError:
        return str(file_path)
