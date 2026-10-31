"""日志来源适配器（Source Adapter）的公共类型和注册表。

适配器只负责“发现目录中的 Run”和“为每个文件提供读取器”；它们不写数据库，
也不生成图表数据。第三方来源可以通过 register() 追加，而无需修改索引器。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from ..log_readers.base import FileCursor, ReadResult


class LogFileReader(Protocol):
    """单个日志文件的增量读取器。"""

    file_kind: str

    def read_new_records(
        self, file_path: Path, run_directory: Path, cursor: FileCursor | None
    ) -> ReadResult: ...


@dataclass(frozen=True)
class LogFileSpec:
    file_path: Path
    reader: LogFileReader


@dataclass
class DiscoveredRun:
    """目录扫描发现的一个 Run 及其日志文件。"""

    source_kind: str
    adapter_id: str
    run_directory: Path
    run_id: str
    metadata: dict
    log_files: list[LogFileSpec] = field(default_factory=list)
    metadata_file: Path | None = None
    metadata_synthetic: bool = False


class SourceAdapter(Protocol):
    adapter_id: str
    display_name: str

    def discover(self, run_directory: Path) -> DiscoveredRun | None:
        """目录属于该来源时返回 Run，否则返回 None。"""
        ...


class SourceAdapterRegistry:
    """按优先级排列的日志来源注册表。"""

    def __init__(self) -> None:
        self._adapters: list[SourceAdapter] = []
        self.plugin_records: list[dict] = []

    def register(
        self, adapter: SourceAdapter, manifest: dict | None = None, builtin: bool = False
    ) -> None:
        if any(existing.adapter_id == adapter.adapter_id for existing in self._adapters):
            raise ValueError(f"日志来源适配器已注册：{adapter.adapter_id}")
        self._adapters.append(adapter)
        self.plugin_records.append(
            {
                "adapter_id": adapter.adapter_id,
                "display_name": getattr(adapter, "display_name", adapter.adapter_id),
                "manifest": manifest or {},
                "status": "builtin" if builtin else ("loaded" if manifest else "missing-manifest"),
                "error": None,
            }
        )

    def record_plugin_failure(self, name: str, error: str) -> None:
        self.plugin_records.append(
            {
                "adapter_id": name,
                "display_name": name,
                "manifest": {},
                "status": "failed",
                "error": error,
            }
        )

    def adapters(self) -> list[SourceAdapter]:
        return list(self._adapters)

    def find_adapters(self, run_directory: Path) -> list[DiscoveredRun]:
        """返回该目录下匹配来源的全部 Run（通用文件来源可能一个目录多个文件）。"""
        for adapter in self._adapters:
            discover_many = getattr(adapter, "discover_many", None)
            if discover_many is not None:
                discovered = list(discover_many(run_directory))
            else:
                single = adapter.discover(run_directory)
                discovered = [single] if single is not None else []
            if discovered:
                return discovered
        return []

    def find_adapter(self, run_directory: Path) -> DiscoveredRun | None:
        discovered = self.find_adapters(run_directory)
        return discovered[0] if discovered else None
