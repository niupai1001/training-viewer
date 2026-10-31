"""内建的日志来源适配器：标准 TVLP、TensorBoard 事件文件、CSV 指标表。

优先级固定为 TVLP > TensorBoard > CSV：只要目录中存在 `run.json`，该目录就按
标准协议解释，不会再把其中的其它文件当作独立来源。
"""
from __future__ import annotations

import hashlib
import importlib.util
import logging
from datetime import datetime, timezone
from pathlib import Path

from ..log_readers.base import (
    InvalidRunDirectoryError,
    ReaderUnavailableError,
    format_timestamp,
)
from ..log_readers.csv_metric_reader import CsvMetricLogReader
from ..log_readers.standard_training_log_reader import StandardTrainingLogReader
from ..log_readers.tensorboard_event_reader import TensorBoardEventReader
from ..run_metadata import RunMetadataReader
from .base import DiscoveredRun, LogFileSpec, SourceAdapter, SourceAdapterRegistry
from .generic_log_file_adapter import GenericLogFileSourceAdapter

DEFAULT_SYNTHETIC_PROJECT = "未命名项目"

LOGGER = logging.getLogger("training_viewer.source_adapters")

PLUGIN_ENTRY_POINT_GROUP = "training_viewer.source_adapters"


def _is_regular_file(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()


def _synthetic_run_id(prefix: str, run_directory: Path) -> str:
    digest = hashlib.sha1(str(run_directory.resolve()).lower().encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:16]}"


def _synthetic_metadata(
    adapter_id: str,
    run_directory: Path,
    created_at_source: Path,
    project_name: str | None = None,
) -> dict:
    try:
        mtime = created_at_source.stat().st_mtime
    except OSError:
        mtime = datetime.now(timezone.utc).timestamp()
    created_at = format_timestamp(datetime.fromtimestamp(mtime, tz=timezone.utc))
    return {
        "schema_version": "1.0",
        "run_id": "",
        "project": project_name or (run_directory.parent.name or DEFAULT_SYNTHETIC_PROJECT),
        "name": run_directory.name,
        "created_at": created_at,
        "extensions": {
            "source_adapter": adapter_id,
            "synthetic_metadata": True,
            "note": "该目录没有 run.json，运行名称与项目由目录推导；原始日志未被修改。",
        },
    }


class StandardTvlpSourceAdapter:
    """标准训练日志来源：`run.json` + `metrics.jsonl` / `events.jsonl`。"""

    adapter_id = "source.standard_training_log"
    display_name = "标准训练日志（TVLP 1.0）"

    def __init__(self) -> None:
        self.metadata_reader = RunMetadataReader()

    def discover(self, run_directory: Path) -> DiscoveredRun | None:
        metadata_path = run_directory / "run.json"
        if not metadata_path.exists():
            return None
        # run.json 是运行身份的权威来源；读不出时明确报错，而不是猜测。
        metadata = self.metadata_reader.read(run_directory)
        log_files: list[LogFileSpec] = []
        metrics_jsonl = run_directory / "metrics.jsonl"
        events_jsonl = run_directory / "events.jsonl"
        if _is_regular_file(metrics_jsonl):
            log_files.append(LogFileSpec(metrics_jsonl, StandardTrainingLogReader("metrics")))
        elif _is_regular_file(run_directory / "metrics.csv"):
            mapping = metadata.get("extensions", {}).get("csv_metric_mapping")
            if mapping is not None and not isinstance(mapping, dict):
                raise InvalidRunDirectoryError("extensions.csv_metric_mapping 必须是 JSON 对象")
            log_files.append(
                LogFileSpec(run_directory / "metrics.csv", CsvMetricLogReader(mapping))
            )
        if _is_regular_file(events_jsonl):
            log_files.append(LogFileSpec(events_jsonl, StandardTrainingLogReader("events")))
        return DiscoveredRun(
            source_kind="tvlp",
            adapter_id=self.adapter_id,
            run_directory=run_directory,
            run_id=metadata["run_id"],
            metadata=metadata,
            log_files=log_files,
            metadata_file=metadata_path,
            metadata_synthetic=False,
        )


class TensorBoardSourceAdapter:
    """TensorBoard 事件文件来源。

    事件文件本身不含项目/运行名称，因此项目取上一级目录名、运行名取目录名。
    run_id 由目录绝对路径推导；移动目录会得到新的 run_id。需要稳定身份时应在
    同一目录补充标准 `run.json`。
    """

    adapter_id = "source.tensorboard_event_file"
    display_name = "TensorBoard 事件文件"

    def discover(self, run_directory: Path) -> DiscoveredRun | None:
        event_files = sorted(
            path
            for path in run_directory.glob("events.out.tfevents.*")
            if _is_regular_file(path)
        )
        if not event_files:
            return None
        if importlib.util.find_spec("tensorboard") is None:
            raise ReaderUnavailableError(
                "发现 TensorBoard 事件文件，但未安装可选依赖 tensorboard；"
                "请运行：pip install \"training-viewer[tensorboard]\""
            )
        metadata = _synthetic_metadata(self.adapter_id, run_directory, event_files[0])
        metadata["run_id"] = _synthetic_run_id("tensorboard", run_directory)
        reader = TensorBoardEventReader()
        return DiscoveredRun(
            source_kind="tensorboard",
            adapter_id=self.adapter_id,
            run_directory=run_directory,
            run_id=metadata["run_id"],
            metadata=metadata,
            log_files=[LogFileSpec(path, reader) for path in event_files],
            metadata_file=None,
            metadata_synthetic=True,
        )


class CsvSourceAdapter:
    """没有 run.json 的 CSV 指标目录。

    识别的固定文件名为 `metrics.csv`。列名按显式映射或常见英文列名别名推断；
    推断结果会显示在界面与诊断中，不会填补缺失的 Step/Epoch。
    """

    adapter_id = "source.csv_metric_log"
    display_name = "CSV 指标表"

    def discover(self, run_directory: Path) -> DiscoveredRun | None:
        csv_path = run_directory / "metrics.csv"
        if not _is_regular_file(csv_path):
            return None
        if (run_directory / "run.json").exists():
            # 有 run.json 时由标准 TVLP 适配器统一处理，避免同一目录出现两个 Run。
            return None
        metadata = _synthetic_metadata(self.adapter_id, run_directory, csv_path)
        metadata["run_id"] = _synthetic_run_id("csv", run_directory)
        return DiscoveredRun(
            source_kind="csv",
            adapter_id=self.adapter_id,
            run_directory=run_directory,
            run_id=metadata["run_id"],
            metadata=metadata,
            log_files=[LogFileSpec(csv_path, CsvMetricLogReader(None))],
            metadata_file=None,
            metadata_synthetic=True,
        )


def build_builtin_source_adapter_registry() -> SourceAdapterRegistry:
    registry = SourceAdapterRegistry()
    registry.register(StandardTvlpSourceAdapter())
    registry.register(TensorBoardSourceAdapter())
    registry.register(CsvSourceAdapter())
    registry.register(GenericLogFileSourceAdapter())
    _load_entry_point_adapters(registry)
    return registry


def _load_entry_point_adapters(registry: SourceAdapterRegistry) -> None:
    """加载通过 Python entry point 安装的第三方来源适配器。

    单个插件加载失败只记录警告，不阻止查看器启动；这保证一个坏插件不会
    破坏已有标准日志的浏览能力。
    """
    from importlib.metadata import entry_points

    for entry_point in entry_points(group=PLUGIN_ENTRY_POINT_GROUP):
        try:
            loaded = entry_point.load()
            adapter = loaded() if isinstance(loaded, type) else loaded
            registry.register(adapter)
            LOGGER.info("已加载第三方日志来源适配器：%s", entry_point.name)
        except Exception as error:  # noqa: BLE001 - 插件失败不能阻止主程序
            LOGGER.warning("加载日志来源插件 %s 失败：%s", entry_point.name, error)


__all__ = [
    "CsvSourceAdapter",
    "GenericLogFileSourceAdapter",
    "SourceAdapter",
    "StandardTvlpSourceAdapter",
    "TensorBoardSourceAdapter",
    "build_builtin_source_adapter_registry",
]
