"""Run 目录扫描器。

从用户显式添加的根目录递归查找 Run。不跟随符号链接目录，跳过常见的依赖和缓存
目录；一旦某个目录被识别为 Run，就不再向下扫描它的产物目录。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from ..log_readers.base import InvalidRunDirectoryError, ReaderUnavailableError
from ..source_adapters.base import DiscoveredRun, SourceAdapterRegistry

EXCLUDED_DIRECTORY_NAMES = frozenset(
    {
        "__pycache__",
        ".git",
        ".hg",
        ".svn",
        ".idea",
        ".vscode",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "venv",
        "env",
        "node_modules",
        "site-packages",
        "dist",
        "build",
        "System Volume Information",
        "$RECYCLE.BIN",
    }
)


@dataclass(frozen=True)
class ScanIssue:
    path: str
    message: str
    severity: str = "error"


@dataclass
class RootScanResult:
    runs: list[DiscoveredRun] = field(default_factory=list)
    issues: list[ScanIssue] = field(default_factory=list)
    scanned_directory_count: int = 0
    truncated: bool = False


class RunDirectoryScanner:
    """日志目录扫描器：根目录 → 发现的 Run 与目录级问题。"""

    def __init__(
        self,
        registry: SourceAdapterRegistry,
        max_directories: int = 50000,
        max_depth: int = 12,
    ):
        self.registry = registry
        self.max_directories = max_directories
        self.max_depth = max_depth

    def scan(self, root_directory: Path) -> RootScanResult:
        result = RootScanResult()
        if not root_directory.is_dir():
            result.issues.append(
                ScanIssue(str(root_directory), "扫描根目录不存在或不可访问（可能被移动或卸载）")
            )
            return result

        pending: list[tuple[Path, int]] = [(root_directory, 0)]
        while pending:
            directory, depth = pending.pop()
            if result.scanned_directory_count >= self.max_directories:
                result.truncated = True
                result.issues.append(
                    ScanIssue(
                        str(root_directory),
                        f"扫描目录数达到上限 {self.max_directories}，其余目录未检查；"
                        "请缩小根目录范围",
                        "warning",
                    )
                )
                break
            result.scanned_directory_count += 1
            try:
                discovered_runs = self.registry.find_adapters(directory)
            except (InvalidRunDirectoryError, ReaderUnavailableError) as error:
                result.issues.append(ScanIssue(str(directory), str(error)))
                # 已知是 Run 目录但元数据/依赖有问题：不再向下扫描它的产物目录。
                continue
            except OSError as error:
                result.issues.append(ScanIssue(str(directory), f"目录读取失败：{error}", "warning"))
                continue
            if discovered_runs:
                result.runs.extend(discovered_runs)
                continues_into_children = all(
                    run.metadata_synthetic
                    and (run.source_kind.startswith("generic-") or run.source_kind == "plain-text")
                    for run in discovered_runs
                )
                if not continues_into_children:
                    continue
            if depth >= self.max_depth:
                result.issues.append(
                    ScanIssue(
                        str(directory),
                        f"达到扫描深度上限 {self.max_depth}，未继续向下查找 Run",
                        "warning",
                    )
                )
                continue
            child_directories: list[Path] = []
            try:
                with os.scandir(directory) as entries:
                    for entry in entries:
                        if entry.name in EXCLUDED_DIRECTORY_NAMES or entry.name.startswith("."):
                            continue
                        try:
                            if entry.is_dir(follow_symlinks=False):
                                child_directories.append(Path(entry.path))
                        except OSError:
                            continue
            except OSError as error:
                result.issues.append(ScanIssue(str(directory), f"目录读取失败：{error}", "warning"))
                continue
            # 排序后倒序入栈，使扫描结果与目录创建顺序无关且可复现。
            for child in sorted(child_directories, reverse=True):
                pending.append((child, depth + 1))
        return result
