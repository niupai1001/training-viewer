"""路径安全边界。

协议规定实验产物路径必须相对 Run 根目录。这里统一拒绝绝对路径、盘符、
`..` 穿越和指向 Run 目录之外的符号链接；API、索引器和产物预览都必须经过这里。
"""
from __future__ import annotations

import re
from pathlib import Path, PurePosixPath


class UnsafeArtifactPathError(ValueError):
    """实验产物路径越出允许范围时抛出。"""


_WINDOWS_DRIVE_PATTERN = re.compile(r"^[A-Za-z]:")


def normalize_relative_path(value: str) -> str:
    """把协议中的产物路径统一为使用 `/` 的相对路径；不解析到磁盘。"""
    return value.replace("\\", "/").strip()


def is_safe_relative_path(value: str) -> bool:
    """判断路径是否是允许的相对路径，不访问文件系统。"""
    if not isinstance(value, str):
        return False
    candidate = normalize_relative_path(value)
    if not candidate or "\x00" in candidate:
        return False
    if _WINDOWS_DRIVE_PATTERN.match(candidate):
        return False
    pure_path = PurePosixPath(candidate)
    if pure_path.is_absolute():
        return False
    if not pure_path.parts:
        return False
    if any(part == ".." for part in pure_path.parts):
        return False
    if pure_path.parts[0] == "~":
        return False
    return True


def resolve_artifact_path(run_directory: Path, relative_path: str) -> Path:
    """把产物相对路径解析为磁盘路径，并保证结果位于 Run 目录内。"""
    if not is_safe_relative_path(relative_path):
        raise UnsafeArtifactPathError(f"非法产物路径：{relative_path!r}")
    run_root = run_directory.resolve()
    candidate = (run_root / normalize_relative_path(relative_path)).resolve()
    if not candidate.is_relative_to(run_root):
        raise UnsafeArtifactPathError(f"产物路径越出 Run 目录：{relative_path!r}")
    return candidate


def is_path_within(candidate: Path, parent: Path) -> bool:
    """判断路径是否在给定父目录内（两者都会解析符号链接）。"""
    try:
        return candidate.resolve().is_relative_to(parent.resolve())
    except OSError:
        return False
