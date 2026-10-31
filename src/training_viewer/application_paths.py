"""应用数据目录、前端静态资源与协议 Schema 的定位规则。

应用数据目录保存 SQLite 索引、根目录配置和界面备注；原始训练日志永远保持只读。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DATA_DIR_ENVIRONMENT_VARIABLE = "TRAINING_VIEWER_DATA_DIR"


class ApplicationDataDirectoryError(RuntimeError):
    """应用数据目录无法创建或不可写。"""


def _ensure_writable_directory(directory: Path) -> None:
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise ApplicationDataDirectoryError(
            f"无法创建应用数据目录 {directory}：{error}。"
            "请用 --data-dir 或环境变量 TRAINING_VIEWER_DATA_DIR 指定可写目录。"
        ) from error
    probe = directory / f".training-viewer-write-test-{os.getpid()}"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as error:
        raise ApplicationDataDirectoryError(
            f"应用数据目录不可写 {directory}：{error}。"
            "请用 --data-dir 或环境变量 TRAINING_VIEWER_DATA_DIR 指定可写目录。"
        ) from error


def _default_data_dir() -> Path:
    configured = os.environ.get(DATA_DIR_ENVIRONMENT_VARIABLE)
    if configured:
        return Path(configured).expanduser()
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "TrainingViewer"
    return Path.home() / ".training_viewer"


@dataclass(frozen=True)
class ApplicationPaths:
    """Training Viewer 使用的所有本机路径。"""

    data_dir: Path
    database_file: Path
    instance_file: Path
    web_dir: Path
    schema_dir: Path

    @classmethod
    def resolve(cls, data_dir: str | Path | None = None) -> "ApplicationPaths":
        package_dir = Path(__file__).resolve().parent
        resolved_data_dir = (
            Path(data_dir).expanduser().resolve()
            if data_dir is not None
            else _default_data_dir().resolve()
        )
        # 目录由应用自己创建；默认 mode 在 Windows 上遵循父目录继承规则。
        _ensure_writable_directory(resolved_data_dir)
        return cls(
            data_dir=resolved_data_dir,
            database_file=resolved_data_dir / "index.sqlite3",
            instance_file=resolved_data_dir / "instance.json",
            web_dir=package_dir / "web",
            schema_dir=package_dir / "schemas",
        )
