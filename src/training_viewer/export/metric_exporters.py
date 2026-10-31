"""指标导出插件：CSV 与 JSON。

导出保留横轴、运行集合、指标定义、抽样/平滑设置与生成时间，便于复现论文图表。
最佳/最终统计来自原始数据，导出注释会明确说明图中的点可能经过分桶抽样。
"""
from __future__ import annotations

import csv
import io
import json
import logging
from typing import Protocol

LOGGER = logging.getLogger("training_viewer.exporter")

PLUGIN_ENTRY_POINT_GROUP = "training_viewer.metric_exporters"


class MetricExporter(Protocol):
    format_id: str
    media_type: str
    file_extension: str

    def serialize(self, comparison: dict, metadata: dict) -> str: ...


class MetricCsvExporter:
    format_id = "csv"
    media_type = "text/csv; charset=utf-8"
    file_extension = "csv"

    def serialize(self, comparison: dict, metadata: dict) -> str:
        buffer = io.StringIO()
        for key in ("exported_at", "axis", "run_ids", "series_keys", "max_points", "smoothing_method", "smoothing_window", "scale"):
            if key in metadata:
                buffer.write(f"# {key}: {json.dumps(metadata[key], ensure_ascii=False)}\n")
        buffer.write(
            "# note: 最佳/最终统计基于原始采样；导出点可能经过最小-最大分桶抽样。"
            "不同运行之间没有插值。\n"
        )
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(
            [
                "run_id",
                "run_name",
                "metric_key",
                "axis",
                "x",
                "value",
                "global_step",
                "epoch",
                "timestamp",
                "session_id",
            ]
        )
        axis = comparison.get("axis")
        for series in comparison.get("series", []):
            for run in series.get("runs", []):
                for point in run.get("points", []):
                    writer.writerow(
                        [
                            run.get("run_id"),
                            run.get("name"),
                            series.get("key"),
                            axis,
                            point.get("x"),
                            point.get("value"),
                            point.get("global_step"),
                            point.get("epoch"),
                            point.get("timestamp"),
                            point.get("session_id"),
                        ]
                    )
        return buffer.getvalue()


class MetricJsonExporter:
    format_id = "json"
    media_type = "application/json; charset=utf-8"
    file_extension = "json"

    def serialize(self, comparison: dict, metadata: dict) -> str:
        payload = {
            "metadata": metadata,
            "axis": comparison.get("axis"),
            "series": comparison.get("series", []),
            "runs": comparison.get("runs", []),
            "hyperparameters": comparison.get("hyperparameters", {}),
            "warnings": comparison.get("warnings", []),
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)


class MetricExporterRegistry:
    """导出格式注册表；第三方导出器可注册新格式而不改 API。"""

    def __init__(self) -> None:
        self._exporters: dict[str, MetricExporter] = {}

    def register(self, exporter: MetricExporter) -> None:
        if exporter.format_id in self._exporters:
            raise ValueError(f"导出格式已注册：{exporter.format_id}")
        self._exporters[exporter.format_id] = exporter

    def get(self, format_id: str) -> MetricExporter | None:
        return self._exporters.get(format_id)

    def formats(self) -> list[str]:
        return sorted(self._exporters)


def build_builtin_metric_exporter_registry() -> MetricExporterRegistry:
    registry = MetricExporterRegistry()
    registry.register(MetricCsvExporter())
    registry.register(MetricJsonExporter())
    _load_entry_point_exporters(registry)
    return registry


def _load_entry_point_exporters(registry: MetricExporterRegistry) -> None:
    from importlib.metadata import entry_points

    for entry_point in entry_points(group=PLUGIN_ENTRY_POINT_GROUP):
        try:
            loaded = entry_point.load()
            exporter = loaded() if isinstance(loaded, type) else loaded
            registry.register(exporter)
            LOGGER.info("已加载第三方导出插件：%s", entry_point.name)
        except Exception as error:  # noqa: BLE001
            LOGGER.warning("加载导出插件 %s 失败：%s", entry_point.name, error)
