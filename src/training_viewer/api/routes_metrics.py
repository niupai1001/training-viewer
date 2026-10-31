"""指标曲线、多运行对比与导出路由。"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from ..export.metric_exporters import MetricExporterRegistry
from ..indexing.index_queries import AXIS_REQUESTS
from ..service import TrainingViewerService
from .dependencies import get_exporter_registry, get_service, safe_filename
from .request_models import CompareRequest, ExportRequest

router = APIRouter(prefix="/api/v1")


def _validate_axis(axis: str) -> None:
    if axis not in AXIS_REQUESTS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的横轴：{axis}；允许 {', '.join(AXIS_REQUESTS)}",
        )


@router.get("/runs/{run_id}/metric-keys")
def metric_keys(run_id: str, service: TrainingViewerService = Depends(get_service)) -> dict:
    keys = service.queries.metric_keys(run_id)
    if keys is None:
        raise HTTPException(status_code=404, detail=f"找不到运行：{run_id}")
    return {"run_id": run_id, "metric_keys": keys}


@router.get("/runs/{run_id}/metrics")
def query_metrics(
    run_id: str,
    series: list[str] = Query(default=[]),
    axis: str = Query(default="auto"),
    max_points: int = Query(default=2000, ge=10, le=20000),
    x_min: float | None = Query(default=None),
    x_max: float | None = Query(default=None),
    service: TrainingViewerService = Depends(get_service),
) -> dict:
    _validate_axis(axis)
    try:
        result = service.queries.query_series(
            run_id, series, axis, max_points, x_min, x_max
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if not result["series"] and not result["warnings"]:
        raise HTTPException(status_code=404, detail=f"找不到运行：{run_id}")
    return result


@router.post("/compare/query")
def compare_query(
    payload: CompareRequest,
    service: TrainingViewerService = Depends(get_service),
) -> dict:
    _validate_axis(payload.axis)
    try:
        return service.queries.compare(
            payload.run_ids,
            payload.series,
            payload.axis,
            payload.max_points,
            payload.x_min,
            payload.x_max,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


def _export_metadata(
    axis: str,
    run_ids: list[str],
    series_keys: list[str],
    max_points: int,
    smoothing_method: str | None,
    smoothing_window: int | None,
    scale: str | None,
    comparison: dict,
) -> dict:
    downsampled = any(
        run.get("downsampled")
        for series in comparison.get("series", [])
        for run in series.get("runs", [])
    )
    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "axis": axis,
        "run_ids": run_ids,
        "series_keys": series_keys,
        "max_points": max_points,
        "downsampled": downsampled,
        "smoothing_method": smoothing_method or "none",
        "smoothing_window": smoothing_window or 0,
        "scale": scale or "linear",
        "tvlp_schema_version": "1.0",
    }


def _export_response(
    comparison: dict,
    metadata: dict,
    format_id: str,
    exporters: MetricExporterRegistry,
    file_stem: str,
) -> Response:
    exporter = exporters.get(format_id)
    if exporter is None:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的导出格式：{format_id}；允许 {', '.join(exporters.formats())}",
        )
    content = exporter.serialize(comparison, metadata)
    filename = f"{safe_filename(file_stem)}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.{exporter.file_extension}"
    return Response(
        content=content,
        media_type=exporter.media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/runs/{run_id}/metrics/export")
def export_run_metrics(
    run_id: str,
    series: list[str] = Query(default=[]),
    axis: str = Query(default="auto"),
    max_points: int = Query(default=1500, ge=10, le=20000),
    format: str = Query(default="csv"),
    smoothing_method: str | None = None,
    smoothing_window: int | None = Query(default=None, ge=0, le=1000),
    scale: str | None = None,
    service: TrainingViewerService = Depends(get_service),
    exporters: MetricExporterRegistry = Depends(get_exporter_registry),
) -> Response:
    _validate_axis(axis)
    if service.queries.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail=f"找不到运行：{run_id}")
    comparison = service.queries.compare([run_id], series, axis, max_points)
    metadata = _export_metadata(
        axis, [run_id], series, max_points, smoothing_method, smoothing_window, scale, comparison
    )
    stem = f"training-viewer_{run_id[:12]}"
    return _export_response(comparison, metadata, format, exporters, stem)


@router.post("/compare/export")
def export_comparison(
    payload: ExportRequest,
    service: TrainingViewerService = Depends(get_service),
    exporters: MetricExporterRegistry = Depends(get_exporter_registry),
) -> Response:
    _validate_axis(payload.axis)
    comparison = service.queries.compare(
        payload.run_ids, payload.series, payload.axis, payload.max_points
    )
    metadata = _export_metadata(
        payload.axis,
        payload.run_ids,
        payload.series,
        payload.max_points,
        payload.smoothing_method,
        payload.smoothing_window,
        payload.scale,
        comparison,
    )
    return _export_response(
        comparison, metadata, payload.format, exporters, "training-viewer_comparison"
    )
