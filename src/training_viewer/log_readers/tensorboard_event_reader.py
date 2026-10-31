"""TensorBoard 事件文件读取器。

复用 TensorBoard 官方的事件文件解析与张量转换实现，只提取标量（scalar）指标。
非标量事件（图像、直方图等）不由本读取器导入，避免把二进制内容误当指标。
TensorBoard 包是可选依赖，未安装时给出明确的安装说明。
"""
from __future__ import annotations

import math
from pathlib import Path

from .base import (
    FileCursor,
    MetricPoint,
    ReadResult,
    ReaderUnavailableError,
    file_identity,
    relative_source_path,
    timestamp_from_epoch_seconds,
)


class TensorBoardEventReader:
    """TensorBoard 标量读取器：`events.out.tfevents.*` → 规范化指标记录。"""

    adapter_id = "source.tensorboard_event_file"
    file_kind = "tensorboard"

    def __init__(self) -> None:
        try:
            from tensorboard.backend.event_processing.event_file_loader import EventFileLoader
            from tensorboard.util import tensor_util
        except ImportError as error:  # pragma: no cover - 取决于可选依赖
            raise ReaderUnavailableError(
                "读取 TensorBoard 事件文件需要可选依赖 tensorboard。"
                "请运行：pip install \"training-viewer[tensorboard]\""
            ) from error
        self._event_file_loader = EventFileLoader
        self._tensor_util = tensor_util

    def read_new_records(
        self, file_path: Path, run_directory: Path, cursor: FileCursor | None
    ) -> ReadResult:
        result = ReadResult()
        try:
            file_stat = file_path.stat()
        except FileNotFoundError:
            result.add_issue(str(file_path), 0, "TensorBoard 事件文件不存在或已被移动", "warning")
            return result

        identity = file_identity(file_stat)
        reset = (
            cursor is None
            or cursor.file_identity != identity
            or file_stat.st_size < cursor.size
        )
        start_index = 0 if reset else cursor.offset
        result.reset = reset
        source_file = relative_source_path(run_directory, file_path)

        event_index = 0
        skipped_non_scalar = 0
        try:
            loader = self._event_file_loader(str(file_path))
            for event in loader.Load():
                current_index = event_index
                event_index += 1
                if current_index < start_index:
                    continue
                if not event.HasField("summary"):
                    continue
                timestamp = timestamp_from_epoch_seconds(event.wall_time)
                for value in event.summary.value:
                    scalar = self._scalar_value(value)
                    if scalar is None:
                        skipped_non_scalar += 1
                        continue
                    phase, metric_name = self._split_tag(value.tag)
                    result.records.append(
                        MetricPoint(
                            phase=phase,
                            metric_name=metric_name,
                            value=scalar,
                            timestamp=timestamp,
                            global_step=int(event.step),
                            epoch=None,
                            session_id=None,
                            event_id=None,
                            source_file=source_file,
                            source_offset=current_index,
                            line_number=current_index + 1,
                        )
                    )
        except Exception as error:  # noqa: BLE001 - 事件文件可能被训练进程写一半
            result.add_issue(
                str(file_path),
                event_index + 1,
                f"事件文件读取中断，已保留已解析部分记录：{error}",
                "warning",
            )

        if skipped_non_scalar:
            result.add_issue(
                str(file_path),
                0,
                f"已跳过 {skipped_non_scalar} 个非标量事件（图像、直方图等不由指标读取器导入）",
                "warning",
            )

        result.cursor = FileCursor(
            file_path=str(file_path),
            file_kind=self.file_kind,
            file_identity=identity,
            offset=event_index,
            line_number=event_index + 1,
            size=file_stat.st_size,
            mtime=file_stat.st_mtime,
        )
        return result

    def _scalar_value(self, value) -> float | None:
        which = value.WhichOneof("value")
        if which == "simple_value":
            number = float(value.simple_value)
            return number if math.isfinite(number) else None
        if which == "tensor":
            tensor = value.tensor
            if tensor is None:
                return None
            try:
                array = self._tensor_util.make_ndarray(tensor)
            except (ValueError, TypeError):
                return None
            if array.size != 1 or array.dtype.kind not in ("f", "i", "u"):
                return None
            number = float(array.reshape(-1)[0])
            return number if math.isfinite(number) else None
        return None

    @staticmethod
    def _split_tag(tag: str) -> tuple[str, str]:
        """把 `<phase>/<metric>` 拆成阶段与指标名；没有斜杠时阶段记为 unlabeled。"""
        normalized = tag.strip("/")
        if "/" in normalized:
            phase, metric_name = normalized.split("/", 1)
            if phase and metric_name:
                return phase, metric_name
        return "unlabeled", normalized or tag

    def list_event_files(self, run_directory: Path) -> list[Path]:
        return sorted(
            path
            for path in run_directory.glob("events.out.tfevents.*")
            if path.is_file() and not path.is_symlink()
        )
