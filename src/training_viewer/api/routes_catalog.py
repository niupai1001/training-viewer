"""运行目录、项目树、设置、诊断与用户界面数据的 REST 路由。"""
from __future__ import annotations

import importlib.util

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import TVLP_SCHEMA_VERSION, __version__
from ..export.metric_exporters import MetricExporterRegistry
from ..service import TrainingViewerService
from .dependencies import get_exporter_registry, get_service
from .request_models import AnnotationUpdateRequest, RootCreateRequest, SavedViewCreateRequest

router = APIRouter(prefix="/api/v1")

SOURCE_KIND_LABELS = {
    "tvlp": "标准训练日志（TVLP 1.0）",
    "tensorboard": "TensorBoard 事件文件",
    "csv": "CSV 指标表",
}


@router.get("/health")
def health(service: TrainingViewerService = Depends(get_service)) -> dict:
    return service.health()


@router.get("/meta")
def meta(
    service: TrainingViewerService = Depends(get_service),
    exporters: MetricExporterRegistry = Depends(get_exporter_registry),
) -> dict:
    adapters = []
    for adapter in service.registry.adapters():
        available = True
        if adapter.adapter_id == "source.tensorboard_event_file":
            available = importlib.util.find_spec("tensorboard") is not None
        adapters.append(
            {
                "adapter_id": adapter.adapter_id,
                "display_name": adapter.display_name,
                "available": available,
            }
        )
    return {
        "application": "training-viewer",
        "version": __version__,
        "tvlp_schema_version": TVLP_SCHEMA_VERSION,
        "source_kinds": SOURCE_KIND_LABELS,
        "status_labels": {
            "running": "运行中",
            "completed": "已完成",
            "failed": "失败",
            "cancelled": "已取消",
            "unknown": "状态未知（可能中断）",
            "imported": "已导入（无生命周期事件）",
        },
        "adapters": adapters,
        "export_formats": exporters.formats(),
        "axes": ["global_step", "epoch", "timestamp"],
        "smoothing_methods": ["none", "moving_average", "ema"],
    }


@router.get("/projects")
def projects(service: TrainingViewerService = Depends(get_service)) -> dict:
    return service.queries.projects()


@router.get("/runs")
def list_runs(
    project: str | None = None,
    experiment: str | None = None,
    status: str | None = None,
    q: str | None = Query(default=None, max_length=200),
    tag: str | None = None,
    task: str | None = None,
    model: str | None = None,
    dataset: str | None = None,
    favorite: bool | None = None,
    sort: str = "-last_updated_at",
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    service: TrainingViewerService = Depends(get_service),
) -> dict:
    return service.queries.list_runs(
        project=project,
        experiment=experiment,
        status=status,
        query=q,
        tag=tag,
        task=task,
        model=model,
        dataset=dataset,
        favorite=favorite,
        sort=sort,
        limit=limit,
        offset=offset,
    )


@router.get("/runs/{run_id}")
def get_run(run_id: str, service: TrainingViewerService = Depends(get_service)) -> dict:
    run = service.queries.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"找不到运行：{run_id}")
    return run


@router.get("/runs/{run_id}/timeline")
def get_timeline(run_id: str, service: TrainingViewerService = Depends(get_service)) -> dict:
    if service.queries.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail=f"找不到运行：{run_id}")
    return service.queries.timeline(run_id)


@router.put("/runs/{run_id}/annotation")
def update_annotation(
    run_id: str,
    payload: AnnotationUpdateRequest,
    service: TrainingViewerService = Depends(get_service),
) -> dict:
    if service.queries.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail=f"找不到运行：{run_id}")
    return service.queries.save_annotation(run_id, payload.note, payload.favorite)


@router.get("/diagnostics")
def diagnostics(service: TrainingViewerService = Depends(get_service)) -> dict:
    return service.queries.diagnostics()


@router.get("/facets")
def facets(service: TrainingViewerService = Depends(get_service)) -> dict:
    return service.queries.facets()


@router.get("/roots")
def list_roots(service: TrainingViewerService = Depends(get_service)) -> dict:
    return {"roots": service.list_roots()}


@router.post("/roots", status_code=201)
def add_root(
    payload: RootCreateRequest,
    service: TrainingViewerService = Depends(get_service),
) -> dict:
    try:
        return service.add_root(payload.path)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.delete("/roots/{root_id}")
def remove_root(root_id: int, service: TrainingViewerService = Depends(get_service)) -> dict:
    if not service.remove_root(root_id):
        raise HTTPException(status_code=404, detail=f"找不到扫描根目录：{root_id}")
    return {"removed": True, "root_id": root_id}


@router.post("/rescan")
def rescan(service: TrainingViewerService = Depends(get_service)) -> dict:
    try:
        return service.synchronize()
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"扫描失败：{error}") from error


@router.get("/saved-views")
def list_saved_views(service: TrainingViewerService = Depends(get_service)) -> dict:
    return {"saved_views": service.queries.list_saved_views()}


@router.post("/saved-views", status_code=201)
def create_saved_view(
    payload: SavedViewCreateRequest,
    service: TrainingViewerService = Depends(get_service),
) -> dict:
    return service.queries.create_saved_view(payload.name, payload.view_kind, payload.payload)


@router.delete("/saved-views/{view_id}")
def delete_saved_view(
    view_id: int, service: TrainingViewerService = Depends(get_service)
) -> dict:
    if not service.queries.delete_saved_view(view_id):
        raise HTTPException(status_code=404, detail=f"找不到保存的视图：{view_id}")
    return {"removed": True, "view_id": view_id}
