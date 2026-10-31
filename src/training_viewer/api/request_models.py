"""API 请求体模型。

只校验用户输入的结构；响应直接使用查询层字典，避免为每个页面重复定义模型。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RootCreateRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4096)


class AnnotationUpdateRequest(BaseModel):
    note: str | None = Field(default=None, max_length=20000)
    favorite: bool | None = None


class SavedViewCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    view_kind: str = Field(default="comparison", max_length=50)
    payload: dict = Field(default_factory=dict)


class LogicalRunOverrideRequest(BaseModel):
    logical_run_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    files: list[str] = Field(min_length=1, max_length=200)
    reason: str = Field(default="user-confirmed", max_length=500)


class CompareRequest(BaseModel):
    run_ids: list[str] = Field(min_length=1, max_length=50)
    series: list[str] = Field(default_factory=list, max_length=50)
    axis: Literal["global_step", "epoch", "timestamp", "auto"] = "auto"
    max_points: int = Field(default=1500, ge=10, le=20000)
    x_min: float | None = None
    x_max: float | None = None


class ExportRequest(CompareRequest):
    format: Literal["csv", "json"] = "csv"
    smoothing_method: str | None = Field(default=None, max_length=50)
    smoothing_window: int | None = Field(default=None, ge=0, le=1000)
    scale: str | None = Field(default=None, max_length=20)
