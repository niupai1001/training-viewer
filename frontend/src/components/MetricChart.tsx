import { useEffect, useMemo, useRef } from "react";
import type { EChartsCoreOption } from "echarts/core";
import { echarts } from "../charts/echarts";
import type { Axis, SeriesPoint, SmoothingMethod } from "../types";
import {
  axisShortLabel,
  formatAxisTime,
  formatAxisTimestampLong,
  formatMetricValue,
  formatNumber,
  unitLabel,
} from "../utils/format";
import { splitBySession, smoothPoints, smoothingLabel } from "../utils/smoothing";
import { downloadBlob, sanitizeFilename } from "../utils/download";

const PALETTE = [
  "#2563eb",
  "#db2777",
  "#16a34a",
  "#d97706",
  "#7c3aed",
  "#0891b2",
  "#dc2626",
  "#4b5563",
  "#059669",
  "#9333ea",
];

export interface ChartLine {
  id: string;
  label: string;
  points: SeriesPoint[];
  unit?: string | null;
}

interface MetricChartProps {
  title: string;
  subtitle?: string;
  lines: ChartLine[];
  axis: Axis;
  smoothing: SmoothingMethod;
  smoothingWindow: number;
  logScale: boolean;
  showRaw: boolean;
  height?: number;
  group?: string;
  emptyMessage?: string;
  downsampled?: boolean;
  onRangeChange?: (range: { min: number; max: number } | null) => void;
}

type TooltipParameter = {
  seriesName: string;
  marker: string;
  data: { meta?: SeriesPoint };
};

export function MetricChart({
  title,
  subtitle,
  lines,
  axis,
  smoothing,
  smoothingWindow,
  logScale,
  showRaw,
  height = 380,
  group,
  emptyMessage = "当前没有可绘制的数据点。",
  downsampled = false,
  onRangeChange,
}: MetricChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<ReturnType<typeof echarts.init> | null>(null);
  const optionRef = useRef<EChartsCoreOption | null>(null);
  const rangeCallbackRef = useRef(onRangeChange);
  rangeCallbackRef.current = onRangeChange;

  const built = useMemo(
    () => buildChartOption({ lines, axis, smoothing, smoothingWindow, logScale, showRaw }),
    [lines, axis, smoothing, smoothingWindow, logScale, showRaw],
  );

  useEffect(() => {
    if (!containerRef.current) {
      return;
    }
    const chart = echarts.init(containerRef.current, undefined, { renderer: "canvas" });
    chartRef.current = chart;
    if (group) {
      chart.group = group;
      echarts.connect(group);
    }
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(containerRef.current);
    const zoomHandler = () => {
      const callback = rangeCallbackRef.current;
      if (!callback) {
        return;
      }
      const option = chart.getOption() as {
        dataZoom?: {
          startValue?: number;
          endValue?: number;
          start?: number;
          end?: number;
        }[];
        series?: { data?: { value?: [number, number] }[] }[];
      };
      const dataZoom = option.dataZoom?.[0];
      let min = dataZoom?.startValue;
      let max = dataZoom?.endValue;
      if (typeof min !== "number" || typeof max !== "number") {
        const xs = (option.series ?? [])
          .flatMap((series) => series.data ?? [])
          .map((item) => item.value?.[0])
          .filter((value): value is number => typeof value === "number");
        const start = dataZoom?.start;
        const end = dataZoom?.end;
        if (xs.length === 0 || typeof start !== "number" || typeof end !== "number") {
          return;
        }
        const dataMin = Math.min(...xs);
        const dataMax = Math.max(...xs);
        min = dataMin + ((dataMax - dataMin) * start) / 100;
        max = dataMin + ((dataMax - dataMin) * end) / 100;
      }
      callback({ min, max });
    };
    chart.on("datazoom", zoomHandler);
    return () => {
      chart.off("datazoom", zoomHandler);
      observer.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, [group]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) {
      return;
    }
    optionRef.current = built.option;
    chart.setOption(built.option, { notMerge: true });
  }, [built]);

  const hasPoints = built.mainSeriesCount > 0;

  function exportPng() {
    const chart = chartRef.current;
    if (!chart) {
      return;
    }
    const url = chart.getDataURL({ type: "png", pixelRatio: 2, backgroundColor: "#ffffff" });
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${sanitizeFilename(title)}.png`;
    anchor.click();
  }

  function exportSvg() {
    if (!optionRef.current) {
      return;
    }
    const holder = document.createElement("div");
    holder.style.position = "fixed";
    holder.style.left = "-99999px";
    holder.style.top = "0";
    holder.style.width = "1200px";
    holder.style.height = `${height}px`;
    document.body.append(holder);
    const svgChart = echarts.init(holder, undefined, {
      renderer: "svg",
      width: 1200,
      height,
    });
    svgChart.setOption(optionRef.current);
    const svgText = (svgChart as unknown as { renderToSVGString: () => string }).renderToSVGString();
    svgChart.dispose();
    holder.remove();
    downloadBlob(
      new Blob([svgText], { type: "image/svg+xml;charset=utf-8" }),
      `${sanitizeFilename(title)}.svg`,
    );
  }

  return (
    <figure className="metric-chart">
      <figcaption className="metric-chart-caption">
        <div>
          <strong>{title}</strong>
          {subtitle ? <span className="metric-chart-subtitle">{subtitle}</span> : null}
        </div>
        <div className="metric-chart-actions">
          <button
            type="button"
            className="button button-small"
            onClick={exportPng}
            disabled={!hasPoints}
            title="把当前图表导出为 PNG（位图）"
          >
            导出 PNG
          </button>
          <button
            type="button"
            className="button button-small"
            onClick={exportSvg}
            disabled={!hasPoints}
            title="把当前图表导出为 SVG（矢量图）"
          >
            导出 SVG
          </button>
        </div>
      </figcaption>
      <div
        ref={containerRef}
        className="metric-chart-canvas"
        style={{ height }}
        role="img"
        aria-label={`${title} 训练指标曲线`}
      >
        {!hasPoints ? (
          <div className="metric-chart-placeholder" style={{ height }}>
            {emptyMessage}
          </div>
        ) : null}
      </div>
      {built.requestedLogScale && !built.logScaleApplied ? (
        <p className="chart-note">
          数据中包含 0 或负值，对数轴无法显示；本次已按线性轴绘制。
        </p>
      ) : null}
      {downsampled ? (
        <p className="chart-note">
          图表使用最小-最大分桶抽样（保留每个分桶的极值）；最佳/最终统计仍基于全部原始记录。
        </p>
      ) : null}
      <p className="chart-note">
        {axisShortLabel(axis)} 横轴
        {smoothing !== "none"
          ? `；显示为${smoothingLabel(smoothing)}（窗口 ${smoothingWindow}），仅影响显示`
          : "；显示原始采样"}
        。
      </p>
    </figure>
  );
}

function buildChartOption({
  lines,
  axis,
  smoothing,
  smoothingWindow,
  logScale,
  showRaw,
}: {
  lines: ChartLine[];
  axis: Axis;
  smoothing: SmoothingMethod;
  smoothingWindow: number;
  logScale: boolean;
  showRaw: boolean;
}): {
  option: EChartsCoreOption;
  mainSeriesCount: number;
  requestedLogScale: boolean;
  logScaleApplied: boolean;
  unitName: string;
} {
  const series: Record<string, unknown>[] = [];
  const legendNames: string[] = [];
  const rawNames = new Set<string>();
  const unitBySeries = new Map<string, string | null>();
  const units = new Set<string>();
  let hasNonPositive = false;
  let colorIndex = 0;
  let mainSeriesCount = 0;

  for (const line of lines) {
    const color = PALETTE[colorIndex % PALETTE.length];
    colorIndex += 1;
    if (line.unit) {
      units.add(line.unit);
    }
    const segments = splitBySession(
      line.points.filter((point) => point.x !== null && Number.isFinite(point.x)),
    );
    segments.forEach((segment, segmentIndex) => {
      if (segment.points.length === 0) {
        return;
      }
      const suffix = segments.length > 1 ? ` · 会话 ${segmentIndex + 1}` : "";
      const mainName = `${line.label}${suffix}`;
      legendNames.push(mainName);
      unitBySeries.set(mainName, line.unit ?? null);
      mainSeriesCount += 1;
      const smoothed = smoothPoints(segment.points, smoothing, smoothingWindow);
      for (const point of segment.points) {
        hasNonPositive = hasNonPositive || point.value <= 0;
      }
      if (showRaw && smoothing !== "none") {
        const rawName = `${mainName}（原始）`;
        rawNames.add(rawName);
        series.push({
          name: rawName,
          type: "line",
          showSymbol: false,
          silent: true,
          animation: false,
          connectNulls: false,
          data: segment.points.map((point) => ({ value: [point.x, point.value], meta: point })),
          lineStyle: { width: 1, opacity: 0.28, color },
          itemStyle: { color, opacity: 0.28 },
          z: 1,
        });
      }
      series.push({
        name: mainName,
        type: "line",
        showSymbol: false,
        animation: false,
        connectNulls: false,
        data: smoothed.map((point) => ({ value: [point.x, point.value], meta: point })),
        lineStyle: { width: 2, color },
        itemStyle: { color },
        emphasis: { focus: "series" },
        z: 3,
      });
    });
  }

  const logScaleApplied = logScale && !hasNonPositive && mainSeriesCount > 0;
  const singleUnit = units.size === 1 ? Array.from(units)[0] : null;
  const tooltipFormatter = (params: unknown) => {
    const parameters = (Array.isArray(params) ? params : [params]) as TooltipParameter[];
    const visible = parameters.filter(
      (parameter) => parameter?.data?.meta && !rawNames.has(parameter.seriesName),
    );
    if (visible.length === 0) {
      return "";
    }
    const meta = visible[0].data.meta as SeriesPoint;
    const header =
      axis === "timestamp" && meta.x !== null
        ? formatAxisTimestampLong(meta.x)
        : `横轴 ${formatNumber(meta.x ?? null)}`;
    const rows = visible.map((parameter) => {
      const point = parameter.data.meta as SeriesPoint;
      const unit = unitBySeries.get(parameter.seriesName);
      const detail =
        axis === "global_step"
          ? point.epoch !== null
            ? `（Epoch ${point.epoch}）`
            : ""
          : axis === "epoch"
            ? point.global_step !== null
              ? `（Step ${point.global_step}）`
              : ""
            : "";
      return `${parameter.marker} ${escapeHtml(parameter.seriesName)}：${escapeHtml(
        formatMetricValue(point.value, unit),
      )}${escapeHtml(detail)}`;
    });
    return `<div class="chart-tooltip"><div class="chart-tooltip-title">${escapeHtml(
      header,
    )}</div>${rows.join("<br/>")}</div>`;
  };

  const option: EChartsCoreOption = {
    animation: false,
    color: PALETTE,
    grid: {
      left: 64,
      right: 28,
      top: legendNames.length > 1 ? 52 : 28,
      bottom: 86,
      containLabel: false,
    },
    legend:
      legendNames.length > 1
        ? {
            data: legendNames,
            type: "scroll",
            top: 4,
            left: 8,
            right: 8,
            textStyle: { fontSize: 12 },
          }
        : undefined,
    tooltip: {
      trigger: "axis",
      confine: true,
      axisPointer: { type: "cross" },
      formatter: tooltipFormatter,
      textStyle: { fontSize: 12 },
    },
    xAxis: {
      type: "value",
      name: axisShortLabel(axis),
      nameLocation: "middle",
      nameGap: 36,
      scale: true,
      minInterval: axis === "timestamp" ? undefined : 1,
      axisLabel: {
        formatter:
          axis === "timestamp"
            ? (value: number) => formatAxisTime(value)
            : (value: number) => formatNumber(value, 0),
      },
      splitLine: { show: false },
    },
    yAxis: {
      type: logScaleApplied ? "log" : "value",
      name: singleUnit ? unitLabel(singleUnit) : undefined,
      nameLocation: "end",
      nameGap: 12,
      scale: true,
      axisLabel: { formatter: (value: number) => formatNumber(value) },
      splitLine: { lineStyle: { color: "#e5e7eb" } },
    },
    dataZoom: [
      { type: "inside", filterMode: "none" },
      { type: "slider", height: 16, bottom: 8, filterMode: "none" },
    ],
    series,
  };

  return {
    option,
    mainSeriesCount,
    requestedLogScale: logScale,
    logScaleApplied,
    unitName: singleUnit ?? "",
  };
}

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}
