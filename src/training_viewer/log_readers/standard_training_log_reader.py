"""训练日志协议（TVLP）1.0 的 JSONL 读取器。

逐字节增量读取 `metrics.jsonl` / `events.jsonl`：只消费以换行结尾的完整行，
把尾部尚未写完的半行留给下一次读取。文件被截断、替换或轮转时重置游标，
由索引器删除该文件的旧索引后重新导入，原始文件不会被修改。
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from ..security.path_guard import is_safe_relative_path
from .base import (
    ArtifactRecord,
    FileCursor,
    HeartbeatRecord,
    LifecycleRecord,
    MetricPoint,
    ReadResult,
    file_identity,
    load_json_line,
    optional_integer,
    optional_number,
    optional_object,
    optional_string,
    parse_timestamp,
    relative_source_path,
    require_object,
    require_string,
)

_METRIC_RECORD_FIELDS = {
    "timestamp",
    "event_id",
    "session_id",
    "phase",
    "global_step",
    "epoch",
    "epoch_progress",
    "wall_time_sec",
    "metrics",
    "context",
    "extensions",
}
_EVENT_COMMON_FIELDS = {"type", "timestamp", "event_id", "session_id", "extensions"}
_LIFECYCLE_FIELDS = _EVENT_COMMON_FIELDS | {"status", "message"}
_HEARTBEAT_FIELDS = _EVENT_COMMON_FIELDS | {"global_step"}
_ARTIFACT_FIELDS = _EVENT_COMMON_FIELDS | {
    "path",
    "artifact_type",
    "tag",
    "phase",
    "global_step",
    "epoch",
    "group_id",
    "sample_id",
    "role",
    "mime_type",
    "metadata",
}
_LIFECYCLE_STATUSES = {"started", "resumed", "completed", "failed", "cancelled"}
_ARTIFACT_TYPES = {"image", "table", "figure", "html", "model", "file"}


def _reject_unknown_fields(payload: dict, allowed: set[str], label: str) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"{label} 含未知字段：{', '.join(unknown)}")


def _parse_metric_record(payload: dict, source_file: str, source_offset: int, line_number: int) -> list[MetricPoint]:
    _reject_unknown_fields(payload, _METRIC_RECORD_FIELDS, "指标记录")
    timestamp = parse_timestamp(payload.get("timestamp"))
    phase = require_string(payload.get("phase"), "phase")
    metrics = require_object(payload.get("metrics"), "metrics")
    if not metrics:
        raise ValueError("metrics 不能为空")
    global_step = optional_integer(payload.get("global_step"), "global_step", minimum=0)
    epoch = optional_integer(payload.get("epoch"), "epoch", minimum=1)
    if global_step is None and epoch is None:
        raise ValueError("指标记录必须至少包含 global_step 或 epoch")
    epoch_progress = optional_number(payload.get("epoch_progress"), "epoch_progress")
    if epoch_progress is not None and not 0.0 <= epoch_progress <= 1.0:
        raise ValueError("epoch_progress 必须在 [0, 1] 区间")
    optional_number(payload.get("wall_time_sec"), "wall_time_sec")
    session_id = optional_string(payload.get("session_id"), "session_id")
    event_id = optional_string(payload.get("event_id"), "event_id")
    optional_object(payload.get("context"), "context")
    optional_object(payload.get("extensions"), "extensions")

    points: list[MetricPoint] = []
    for metric_name, raw_value in metrics.items():
        require_string(metric_name, "metrics 的键")
        if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
            raise ValueError(f"指标 {metric_name} 的值必须是数字")
        value = float(raw_value)
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError(f"指标 {metric_name} 的值必须是有限数字")
        points.append(
            MetricPoint(
                phase=phase,
                metric_name=metric_name,
                value=value,
                timestamp=timestamp,
                global_step=global_step,
                epoch=epoch,
                session_id=session_id,
                event_id=event_id,
                source_file=source_file,
                source_offset=source_offset,
                line_number=line_number,
            )
        )
    return points


def _parse_event_record(
    payload: dict, source_file: str, source_offset: int, line_number: int
) -> LifecycleRecord | HeartbeatRecord | ArtifactRecord:
    event_type = payload.get("type")
    if event_type == "lifecycle":
        _reject_unknown_fields(payload, _LIFECYCLE_FIELDS, "lifecycle 事件")
        timestamp = parse_timestamp(payload.get("timestamp"))
        status = require_string(payload.get("status"), "status")
        if status not in _LIFECYCLE_STATUSES:
            raise ValueError(f"未知 lifecycle 状态：{status}")
        return LifecycleRecord(
            status=status,
            timestamp=timestamp,
            session_id=optional_string(payload.get("session_id"), "session_id"),
            message=optional_string(payload.get("message"), "message"),
            event_id=optional_string(payload.get("event_id"), "event_id"),
            source_file=source_file,
            source_offset=source_offset,
            line_number=line_number,
        )
    if event_type == "heartbeat":
        _reject_unknown_fields(payload, _HEARTBEAT_FIELDS, "heartbeat 事件")
        return HeartbeatRecord(
            timestamp=parse_timestamp(payload.get("timestamp")),
            session_id=optional_string(payload.get("session_id"), "session_id"),
            global_step=optional_integer(payload.get("global_step"), "global_step", minimum=0),
            event_id=optional_string(payload.get("event_id"), "event_id"),
            source_file=source_file,
            source_offset=source_offset,
            line_number=line_number,
        )
    if event_type == "artifact":
        _reject_unknown_fields(payload, _ARTIFACT_FIELDS, "artifact 事件")
        artifact_path = require_string(payload.get("path"), "path")
        if not is_safe_relative_path(artifact_path):
            raise ValueError(f"产物路径必须是 Run 目录内的相对路径：{artifact_path!r}")
        artifact_type = require_string(payload.get("artifact_type"), "artifact_type")
        if artifact_type not in _ARTIFACT_TYPES:
            raise ValueError(f"未知 artifact_type：{artifact_type}")
        optional_object(payload.get("metadata"), "metadata")
        optional_object(payload.get("extensions"), "extensions")
        return ArtifactRecord(
            path=artifact_path,
            artifact_type=artifact_type,
            tag=require_string(payload.get("tag"), "tag"),
            timestamp=parse_timestamp(payload.get("timestamp")),
            phase=optional_string(payload.get("phase"), "phase"),
            global_step=optional_integer(payload.get("global_step"), "global_step", minimum=0),
            epoch=optional_integer(payload.get("epoch"), "epoch", minimum=1),
            group_id=optional_string(payload.get("group_id"), "group_id"),
            sample_id=optional_string(payload.get("sample_id"), "sample_id"),
            role=optional_string(payload.get("role"), "role"),
            mime_type=optional_string(payload.get("mime_type"), "mime_type"),
            metadata=dict(optional_object(payload.get("metadata"), "metadata")),
            session_id=optional_string(payload.get("session_id"), "session_id"),
            event_id=optional_string(payload.get("event_id"), "event_id"),
            source_file=source_file,
            source_offset=source_offset,
            line_number=line_number,
        )
    raise ValueError(f"未知事件类型：{event_type!r}")


class StandardTrainingLogReader:
    """标准训练日志增量读取器：JSONL 文件 → 规范化指标/事件记录。"""

    adapter_id = "source.standard_training_log"

    def __init__(self, file_kind: Literal["metrics", "events"]):
        if file_kind not in ("metrics", "events"):
            raise ValueError("file_kind 只能是 metrics 或 events")
        self.file_kind = file_kind

    def read_new_records(
        self, file_path: Path, run_directory: Path, cursor: FileCursor | None
    ) -> ReadResult:
        result = ReadResult()
        try:
            file_stat = file_path.stat()
        except FileNotFoundError:
            result.add_issue(str(file_path), 0, "日志文件不存在或已被移动", "warning")
            return result

        identity = file_identity(file_stat)
        reset = (
            cursor is None
            or cursor.file_identity != identity
            or file_stat.st_size < cursor.offset
        )
        start_offset = 0 if reset else cursor.offset
        next_line_number = 1 if reset else cursor.line_number
        result.reset = reset

        with file_path.open("rb") as handle:
            handle.seek(start_offset)
            payload = handle.read()

        last_newline = payload.rfind(b"\n")
        if last_newline < 0:
            complete_bytes = b""
            new_offset = start_offset
        else:
            complete_bytes = payload[: last_newline + 1]
            new_offset = start_offset + last_newline + 1

        source_file = relative_source_path(run_directory, file_path)
        current_offset = start_offset
        current_line_number = next_line_number

        for raw_line in complete_bytes.splitlines(keepends=True):
            line_offset = current_offset
            current_offset += len(raw_line)
            line_number = current_line_number
            current_line_number += 1
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                parsed = load_json_line(stripped)
                payload_object = require_object(parsed, "日志行")
                if self.file_kind == "metrics":
                    result.records.extend(
                        _parse_metric_record(payload_object, source_file, line_offset, line_number)
                    )
                else:
                    result.records.append(
                        _parse_event_record(payload_object, source_file, line_offset, line_number)
                    )
            except (UnicodeDecodeError, ValueError) as error:
                result.add_issue(str(file_path), line_number, f"第 {line_number} 行无法导入：{error}")

        result.cursor = FileCursor(
            file_path=str(file_path),
            file_kind=self.file_kind,
            file_identity=identity,
            offset=new_offset,
            line_number=current_line_number,
            size=file_stat.st_size,
            mtime=file_stat.st_mtime,
        )
        if new_offset < file_stat.st_size:
            result.add_issue(
                str(file_path),
                current_line_number,
                "文件末尾存在尚未写完的 JSON 行，本次暂不导入，下次读取会补齐",
                "warning",
            )
        result.finalize_issues(str(file_path))
        return result
