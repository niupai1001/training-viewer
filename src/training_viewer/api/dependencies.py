"""API 共享依赖与安全校验。"""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import Request
from fastapi import HTTPException

from ..export.metric_exporters import MetricExporterRegistry
from ..security.path_guard import is_path_within
from ..service import TrainingViewerService

_SAFE_FILENAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


def get_service(request: Request) -> TrainingViewerService:
    return request.app.state.service


def get_exporter_registry(request: Request) -> MetricExporterRegistry:
    return request.app.state.exporter_registry


def ensure_run_directory_allowed(service: TrainingViewerService, run_directory: str) -> Path:
    """产物内容只能来自用户显式添加根目录内的运行目录。"""
    resolved_run = Path(run_directory).resolve()
    for root in service.list_roots():
        if is_path_within(resolved_run, Path(root["path"])):
            return resolved_run
    raise HTTPException(
        status_code=403,
        detail="运行目录不在已添加的扫描根目录内，拒绝读取产物内容。",
    )


def safe_filename(value: str, fallback: str = "training-viewer") -> str:
    cleaned = _SAFE_FILENAME_PATTERN.sub("_", value).strip("._")
    return cleaned[:80] or fallback
