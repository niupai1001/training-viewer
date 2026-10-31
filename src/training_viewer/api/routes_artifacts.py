"""实验产物查询、安全预览与下载路由。

所有文件内容都先确认运行目录位于用户添加的根目录内，再把协议中的相对路径
解析到 Run 目录内；HTML/SVG 默认不以可执行内容返回，避免本地脚本注入。
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from ..security.path_guard import UnsafeArtifactPathError, resolve_artifact_path
from ..results.discovery import discover_result_files
from ..service import TrainingViewerService
from .dependencies import ensure_run_directory_allowed, get_service

router = APIRouter(prefix="/api/v1")

_INLINE_IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}
_MAX_PREVIEW_BYTES = 5 * 1024 * 1024
_MAX_PREVIEW_ROWS = 200
_MAX_PREVIEW_COLUMNS = 40

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "sandbox; default-src 'none'; style-src 'unsafe-inline'",
}


@router.get("/runs/{run_id}/artifacts")
def list_artifacts(
    run_id: str,
    tag: str | None = None,
    sample_id: str | None = None,
    group_id: str | None = None,
    epoch: int | None = None,
    artifact_type: str | None = None,
    service: TrainingViewerService = Depends(get_service),
) -> dict:
    if service.queries.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail=f"找不到运行：{run_id}")
    artifacts = service.queries.list_artifacts(
        run_id,
        tag=tag,
        sample_id=sample_id,
        group_id=group_id,
        epoch=epoch,
        artifact_type=artifact_type,
    )
    return {"run_id": run_id, "artifacts": artifacts}


@router.get("/runs/{run_id}/artifact-groups")
def artifact_groups(
    run_id: str,
    tag: str | None = None,
    service: TrainingViewerService = Depends(get_service),
) -> dict:
    if service.queries.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail=f"找不到运行：{run_id}")
    return {"run_id": run_id, "groups": service.queries.artifact_groups(run_id, tag=tag)}


@router.get("/runs/{run_id}/result-candidates")
def result_candidates(
    run_id: str, service: TrainingViewerService = Depends(get_service)
) -> dict:
    run = service.queries.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"找不到运行：{run_id}")
    run_directory = ensure_run_directory_allowed(service, run["run_directory"])
    known_paths = {
        artifact["path"]
        for artifact in service.queries.list_artifacts(run_id)
        if artifact.get("path")
    }
    candidates = discover_result_files(run_directory, known_paths)
    for candidate in candidates:
        candidate["content_url"] = (
            f"/api/v1/runs/{run_id}/result-candidates/content"
            f"?path={candidate['path']}"
        )
    return {
        "run_id": run_id,
        "candidates": candidates,
        "note": "路径/文件名推断只是候选；确认前不要作为科学结论。",
    }


@router.get("/runs/{run_id}/result-candidates/content")
def result_candidate_content(
    run_id: str,
    path: str,
    service: TrainingViewerService = Depends(get_service),
) -> FileResponse:
    run = service.queries.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"找不到运行：{run_id}")
    run_directory = ensure_run_directory_allowed(service, run["run_directory"])
    try:
        resolved = resolve_artifact_path(run_directory, path)
    except UnsafeArtifactPathError as error:
        raise HTTPException(status_code=403, detail=f"结果路径被拒绝：{error}") from error
    suffix = resolved.suffix.lower()
    if suffix not in _INLINE_IMAGE_TYPES or not resolved.is_file():
        raise HTTPException(status_code=404, detail="结果图片不存在或类型不允许预览。")
    return FileResponse(
        resolved,
        media_type=_INLINE_IMAGE_TYPES[suffix],
        filename=resolved.name,
        content_disposition_type="inline",
        headers=_SECURITY_HEADERS,
    )


def _resolve_artifact_file(service: TrainingViewerService, artifact_id: int) -> tuple[dict, Path]:
    artifact = service.queries.get_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail=f"找不到产物记录：{artifact_id}")
    run_directory = ensure_run_directory_allowed(service, artifact["run_directory"])
    try:
        resolved = resolve_artifact_path(run_directory, artifact["path"])
    except UnsafeArtifactPathError as error:
        raise HTTPException(status_code=403, detail=f"产物路径被拒绝：{error}") from error
    if not resolved.is_file():
        raise HTTPException(
            status_code=404,
            detail="产物文件当前不存在；可能尚未写入、已被移动，或训练程序只记录了引用。",
        )
    return artifact, resolved


@router.get("/artifacts/{artifact_id}/content")
def artifact_content(
    artifact_id: int, service: TrainingViewerService = Depends(get_service)
) -> FileResponse:
    artifact, resolved = _resolve_artifact_file(service, artifact_id)
    suffix = resolved.suffix.lower()
    if artifact["artifact_type"] == "image" and suffix in _INLINE_IMAGE_TYPES:
        return FileResponse(
            resolved,
            media_type=_INLINE_IMAGE_TYPES[suffix],
            filename=resolved.name,
            content_disposition_type="inline",
            headers=_SECURITY_HEADERS,
        )
    if suffix in (".html", ".htm", ".svg"):
        # 可执行内容按不可信文本返回；浏览器会下载而不是直接执行脚本。
        return FileResponse(
            resolved,
            media_type="text/plain",
            filename=resolved.name + ".txt",
            content_disposition_type="attachment",
            headers=_SECURITY_HEADERS,
        )
    return FileResponse(
        resolved,
        media_type=artifact["mime_type"] or "application/octet-stream",
        filename=resolved.name,
        content_disposition_type="attachment",
        headers=_SECURITY_HEADERS,
    )


@router.get("/artifacts/{artifact_id}/download")
def artifact_download(
    artifact_id: int, service: TrainingViewerService = Depends(get_service)
) -> FileResponse:
    _, resolved = _resolve_artifact_file(service, artifact_id)
    return FileResponse(
        resolved,
        media_type="application/octet-stream",
        filename=resolved.name,
        content_disposition_type="attachment",
        headers=_SECURITY_HEADERS,
    )


@router.get("/artifacts/{artifact_id}/table-preview")
def artifact_table_preview(
    artifact_id: int, service: TrainingViewerService = Depends(get_service)
) -> dict:
    artifact, resolved = _resolve_artifact_file(service, artifact_id)
    if resolved.stat().st_size > _MAX_PREVIEW_BYTES:
        raise HTTPException(status_code=413, detail="文件大于 5 MiB，请直接下载后查看。")
    suffix = resolved.suffix.lower()
    if suffix in (".csv", ".tsv"):
        delimiter = "\t" if suffix == ".tsv" else ","
        return _preview_csv(resolved, delimiter)
    if suffix == ".json":
        return _preview_json(resolved)
    raise HTTPException(
        status_code=400,
        detail="该产物不是可预览的 CSV/TSV/JSON 表格；请下载查看。",
    )


def _preview_csv(path: Path, delimiter: str) -> dict:
    rows: list[list[str]] = []
    truncated = False
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle, delimiter=delimiter)
            for row in reader:
                if len(rows) > _MAX_PREVIEW_ROWS:
                    truncated = True
                    break
                rows.append([cell[:500] for cell in row[:_MAX_PREVIEW_COLUMNS]])
                if len(row) > _MAX_PREVIEW_COLUMNS:
                    truncated = True
    except (OSError, UnicodeDecodeError, csv.Error) as error:
        raise HTTPException(status_code=422, detail=f"表格无法解析：{error}") from error
    if not rows:
        return {"kind": "table", "columns": [], "rows": [], "truncated": False}
    return {
        "kind": "table",
        "columns": rows[0],
        "rows": rows[1:],
        "truncated": truncated,
    }


def _preview_json(path: Path) -> dict:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=f"JSON 无法解析：{error}") from error
    if isinstance(payload, list) and payload and all(isinstance(item, dict) for item in payload):
        columns: list[str] = []
        for item in payload[:_MAX_PREVIEW_ROWS]:
            for key in item:
                if key not in columns and len(columns) < _MAX_PREVIEW_COLUMNS:
                    columns.append(str(key))
        rows = [
            [_stringify(item.get(column)) for column in columns]
            for item in payload[:_MAX_PREVIEW_ROWS]
        ]
        return {
            "kind": "table",
            "columns": columns,
            "rows": rows,
            "truncated": len(payload) > _MAX_PREVIEW_ROWS,
        }
    if isinstance(payload, dict):
        rows = [
            [_stringify(key), _stringify(value)]
            for key, value in list(payload.items())[:_MAX_PREVIEW_ROWS]
        ]
        return {
            "kind": "table",
            "columns": ["键", "值"],
            "rows": rows,
            "truncated": len(payload) > _MAX_PREVIEW_ROWS,
        }
    raise HTTPException(
        status_code=400,
        detail="JSON 顶层既不是对象也不是对象数组，无法以表格预览。",
    )


def _stringify(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and not math.isfinite(value):
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)[:500]
    return str(value)[:500]
