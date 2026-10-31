"""路径安全：相对路径白名单、目录穿越和符号链接边界。"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from training_viewer.security.path_guard import (
    UnsafeArtifactPathError,
    is_safe_relative_path,
    resolve_artifact_path,
)


@pytest.mark.parametrize(
    "value",
    [
        "artifacts/predictions/a.png",
        "artifacts\\labels\\a.png",
        "a.csv",
        "dir/with space/file.txt",
    ],
)
def test_safe_relative_paths(value: str) -> None:
    assert is_safe_relative_path(value) is True


@pytest.mark.parametrize(
    "value",
    [
        "",
        "/etc/passwd",
        "C:\\Windows\\System32\\config",
        "../secret.txt",
        "artifacts/../../secret.txt",
        "~/secret.txt",
        "a/../../b",
        "file\x00.png",
    ],
)
def test_unsafe_relative_paths(value: str) -> None:
    assert is_safe_relative_path(value) is False


def test_resolve_artifact_path_rejects_traversal(tmp_path: Path) -> None:
    run_directory = tmp_path / "run"
    run_directory.mkdir()
    (run_directory / "image.png").write_bytes(b"x")
    assert resolve_artifact_path(run_directory, "image.png") == (run_directory / "image.png").resolve()
    with pytest.raises(UnsafeArtifactPathError):
        resolve_artifact_path(run_directory, "../image.png")


def test_resolve_artifact_path_rejects_symlink_escape(tmp_path: Path) -> None:
    run_directory = tmp_path / "run"
    run_directory.mkdir()
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"secret")
    link = run_directory / "link.png"
    try:
        os.symlink(outside, link)
    except OSError:
        pytest.skip("当前 Windows 环境不允许创建符号链接")
    with pytest.raises(UnsafeArtifactPathError):
        resolve_artifact_path(run_directory, "link.png")


def test_resolve_artifact_path_allows_symlink_inside_run(tmp_path: Path) -> None:
    run_directory = tmp_path / "run"
    run_directory.mkdir()
    target = run_directory / "target.png"
    target.write_bytes(b"x")
    link = run_directory / "link.png"
    try:
        os.symlink(target, link)
    except OSError:
        pytest.skip("当前 Windows 环境不允许创建符号链接")
    assert resolve_artifact_path(run_directory, "link.png") == target.resolve()
