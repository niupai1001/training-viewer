import { useEffect, useMemo, useState } from "react";
import { api, runExportUrl } from "../api/client";
import { useApi } from "../hooks/useApi";
import { useLiveVersion } from "../live/LiveUpdates";
import type { MetricQueryResult, RunDetail } from "../types";
import {
  axisShortLabel,
  directionLabel,
  formatMetricValue,
  formatNumber,
  formatDateTime,
  unitLabel,
} from "../utils/format";
import { downloadBlob, downloadFromUrl } from "../utils/download";
import { EmptyState, ErrorBlock, LoadingBlock, WarningList } from "../components/Common";
import { ChartControls, DEFAULT_CHART_PREFERENCES } from "../components/ChartControls";
import type { ChartPreferences } from "../components/ChartControls";
import { MetricChart } from "../components/MetricChart";

const MAX_SELECTED_METRICS = 6;

export function RunMetricsTab({ run, chartLimit }: { run: RunDetail; chartLimit?: number }) {
  const liveVersion = useLiveVersion();
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
  const [phaseFilter, setPhaseFilter] = useState<string>("all");
  const [preferences, setPreferences] = useState<ChartPreferences>(DEFAULT_CHART_PREFERENCES);
  const [limitMessage, setLimitMessage] = useState<string | null>(null);

  const metricSignature = run.metric_keys.map((metric) => metric.key).join("|");
  const phases = useMemo(
    () => Array.from(new Set(run.metric_keys.map((metric) => metric.phase))),
    [run.metric_keys],
  );

  useEffect(() => {
    setPhaseFilter("all");
    setSelectedKeys((current) => {
      const valid = current.filter((key) => run.metric_keys.some((metric) => metric.key === key));
      if (valid.length > 0) {
        return valid;
      }
      return recommendedMetricKeys(run.metric_keys);
    });
    // metricSignature 覆盖指标集合变化；run_id 覆盖切换运行。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run.run_id, metricSignature]);

  const metricsState = useApi<MetricQueryResult | null>(
    () =>
      selectedKeys.length === 0
        ? Promise.resolve(null)
        : api.metrics(run.run_id, selectedKeys, preferences.axis, 3000),
    [
      run.run_id,
      selectedKeys.join("|"),
      preferences.axis,
      run.status === "running" ? liveVersion : 0,
    ],
  );

  const visibleKeys = run.metric_keys.filter(
    (metric) => phaseFilter === "all" || metric.phase === phaseFilter,
  );

  function toggleMetric(key: string) {
    setLimitMessage(null);
    setSelectedKeys((current) => {
      if (current.includes(key)) {
        return current.filter((item) => item !== key);
      }
      if (current.length >= MAX_SELECTED_METRICS) {
        setLimitMessage(`一次最多显示 ${MAX_SELECTED_METRICS} 条指标曲线，请先取消其它指标。`);
        return current;
      }
      return [...current, key];
    });
  }

  function exportMetrics(format: "csv" | "json") {
    if (selectedKeys.length === 0) {
      return;
    }
    downloadFromUrl(
      runExportUrl(run.run_id, {
        series: selectedKeys,
        axis: preferences.axis,
        format,
        maxPoints: 1500,
        smoothingMethod: preferences.smoothing,
        smoothingWindow: preferences.smoothingWindow,
        scale: preferences.logScale ? "log" : "linear",
      }),
    );
  }

  function exportVisibleChartData() {
    const series = metricsState.data?.series ?? [];
    if (series.length === 0) {
      return;
    }
    const lines: string[] = ["run_id,metric_key,axis,x,value,global_step,epoch,timestamp,session_id"];
    for (const metric of series) {
      for (const point of metric.points) {
        lines.push(
          [
            JSON.stringify(run.run_id),
            JSON.stringify(metric.key),
            JSON.stringify(preferences.axis),
            point.x ?? "",
            point.value,
            point.global_step ?? "",
            point.epoch ?? "",
            JSON.stringify(point.timestamp ?? ""),
            JSON.stringify(point.session_id ?? ""),
          ].join(","),
        );
      }
    }
    downloadBlob(
      new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" }),
      `${run.name.replace(/[^\w-]+/g, "_")}_chart_data.csv`,
    );
  }

  if (run.metric_keys.length === 0) {
    return (
      <EmptyState
        title="该运行还没有数值指标"
        description="查看器只显示 metrics.jsonl / metrics.csv / TensorBoard 中真实记录的指标。请确认训练程序已按 TVLP 1.0 追加 metrics.jsonl，或该来源的指标文件可被读取。"
      />
    );
  }

  return (
    <div className="metrics-tab">
      <div className="metric-picker">
        <div className="metric-picker-header">
          <h3>指标</h3>
          <div className="phase-filter">
            <button
              type="button"
              className={`chip ${phaseFilter === "all" ? "chip-active" : ""}`}
              onClick={() => setPhaseFilter("all")}
            >
              全部阶段
            </button>
            {phases.map((phase) => (
              <button
                key={phase}
                type="button"
                className={`chip ${phaseFilter === phase ? "chip-active" : ""}`}
                onClick={() => setPhaseFilter(phase)}
              >
                {phase === "unlabeled" ? "未标注阶段" : phase}
              </button>
            ))}
          </div>
          <span className="muted small">
            已选 {selectedKeys.length} / {MAX_SELECTED_METRICS}
          </span>
        </div>
        <div className="metric-chips">
          {visibleKeys.map((metric) => {
            const active = selectedKeys.includes(metric.key);
            return (
              <button
                key={metric.key}
                type="button"
                className={`metric-chip ${active ? "metric-chip-active" : ""}`}
                onClick={() => toggleMetric(metric.key)}
                title={`单位：${metric.unit ?? "未声明"}；方向：${directionLabel(metric.direction)}；${
                  metric.definition ?? "未提供计算定义"
                }`}
              >
                <span>{metric.key}</span>
                <span className="muted small">
                  {formatNumber(metric.point_count, 0)} 点 · {metric.unit ?? "未声明单位"}
                </span>
              </button>
            );
          })}
        </div>
        {limitMessage ? <p className="notice notice-warning">{limitMessage}</p> : null}
      </div>

      <ChartControls value={preferences} onChange={setPreferences} />

      {metricsState.loading ? <LoadingBlock label="正在读取指标…" /> : null}
      {metricsState.error ? (
        <ErrorBlock error={metricsState.error} onRetry={metricsState.reload} />
      ) : null}
      {metricsState.data?.warnings.length ? <WarningList warnings={metricsState.data.warnings} /> : null}

      {run.metric_keys.length === 0 ? (
        <EmptyState
          title="这个运行还没有可绘制的指标"
          description={
            run.data_sources.length === 0
              ? "查看器还没有读到日志文件；确认目录已添加，且日志正在写入。"
              : "日志文件已读取，但没有解析到“Step/Epoch + 数值指标”。请确认日志格式，或展开下方“数据来源与协议细节”查看读取位置与问题。"
          }
        />
      ) : null}
      {run.metric_keys.length > 0 && selectedKeys.length === 0 ? (
        <EmptyState title="请选择至少一个指标" description="点击上方的指标名称即可绘制对应曲线。" />
      ) : null}

      <div className="chart-stack">
        {metricsState.data?.series.slice(0, chartLimit ?? metricsState.data.series.length).map((series) => (
          <MetricChart
            key={series.key}
            title={series.key}
            subtitle={`${series.display_name} · 单位：${unitLabel(series.unit) || "未声明"} · ${directionLabel(
              series.direction,
            )}${series.definition ? ` · 定义：${series.definition}` : ""}`}
            lines={[
              {
                id: series.key,
                label: series.key,
                points: series.points,
                unit: series.unit,
              },
            ]}
            axis={series.axis}
            smoothing={preferences.smoothing}
            smoothingWindow={preferences.smoothingWindow}
            logScale={preferences.logScale}
            showRaw={preferences.showRaw}
            group="run-detail"
            downsampled={series.downsampled}
            emptyMessage={`指标 ${series.key} 在${axisShortLabel(series.axis)}横轴上没有可用记录。`}
          />
        ))}
      </div>

      {metricsState.data && metricsState.data.series.length > 0 ? (
        <>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">指标</th>
                  <th scope="col">单位 / 方向</th>
                  <th scope="col">最佳值</th>
                  <th scope="col">最终值</th>
                  <th scope="col">点数</th>
                  <th scope="col">计算定义</th>
                </tr>
              </thead>
              <tbody>
                {metricsState.data.series.map((series) => (
                  <tr key={series.key}>
                    <th scope="row">{series.key}</th>
                    <td>
                      {series.unit ?? "未声明"}
                      <div className="muted small">{directionLabel(series.direction)}</div>
                    </td>
                    <td>
                      {series.best ? (
                        <>
                          <strong>{formatMetricValue(series.best.value, series.unit)}</strong>
                          <div className="muted small">
                            {series.best.global_step !== null ? `Step ${series.best.global_step}` : ""}
                            {series.best.epoch !== null ? ` · Epoch ${series.best.epoch}` : ""}
                          </div>
                        </>
                      ) : (
                        <span className="muted">无方向定义</span>
                      )}
                    </td>
                    <td>
                      {series.last ? (
                        <>
                          <strong>{formatMetricValue(series.last.value, series.unit)}</strong>
                          <div className="muted small">
                            {series.last.global_step !== null ? `Step ${series.last.global_step}` : ""}
                            {series.last.epoch !== null ? ` · Epoch ${series.last.epoch}` : ""}
                            {series.last.timestamp ? ` · ${formatDateTime(series.last.timestamp)}` : ""}
                          </div>
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td title={`原始 ${series.total_points} 点，图表返回 ${series.returned_points} 点`}>
                      {formatNumber(series.total_points, 0)}
                      {series.downsampled ? <div className="muted small">图表已抽样</div> : null}
                    </td>
                    <td>{series.definition ?? <span className="muted">未提供</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="export-bar">
            <span className="muted small">导出数据包含横轴与平滑设置，便于复现图表：</span>
            <button type="button" className="button button-small" onClick={() => exportMetrics("csv")}>
              导出 CSV
            </button>
            <button type="button" className="button button-small" onClick={() => exportMetrics("json")}>
              导出 JSON
            </button>
            <button type="button" className="button button-small" onClick={exportVisibleChartData}>
              导出当前图表数据点
            </button>
          </div>
        </>
      ) : null}

      <div className="advanced-inline">
        <details>
          <summary>数据来源与协议细节</summary>
          <ul>
            {run.data_sources.map((source) => (
              <li key={source.file_path}>
                <code>{source.relative_path}</code>
                <span className="muted small">
                  （{source.file_kind}；已读取位置 {formatNumber(source.offset, 0)}，文件{" "}
                  {formatNumber(source.size, 0)} 字节）
                </span>
              </li>
            ))}
            {run.data_sources.length === 0 ? <li className="muted">尚未读取到日志文件。</li> : null}
          </ul>
          <p className="muted small">
            指标点来自原始日志；SQLite 只是可重建的索引。不同定义的指标不会自动换算或插值。
          </p>
        </details>
      </div>
    </div>
  );
}

function recommendedMetricKeys(metrics: RunDetail["metric_keys"]): string[] {
  const phaseOf = (metric: (typeof metrics)[number]) => metric.phase.toLowerCase();
  const isValidation = (metric: (typeof metrics)[number]) =>
    ["val", "valid", "validation", "test", "eval"].includes(phaseOf(metric));
  const findLoss = (validation: boolean) =>
    metrics.find((metric) => {
      const name = metric.metric_name.toLowerCase();
      return name.includes("loss") && (validation ? isValidation(metric) : phaseOf(metric) === "train");
    }) ??
    metrics.find((metric) => {
      const name = metric.metric_name.toLowerCase();
      return name.includes("loss") && (validation ? !isValidation(metric) : true);
    });
  const priority = ["miou", "accuracy", "acc", "f1", "dice", "precision", "recall", "auc"];
  const keyMetric = metrics
    .filter((metric) => isValidation(metric) && metric.direction === "max")
    .sort((left, right) => {
      const leftIndex = priority.findIndex((name) => left.metric_name.toLowerCase().includes(name));
      const rightIndex = priority.findIndex((name) => right.metric_name.toLowerCase().includes(name));
      return (leftIndex < 0 ? 99 : leftIndex) - (rightIndex < 0 ? 99 : rightIndex);
    })[0] ??
    metrics.find((metric) => metric.direction === "max") ??
    metrics.find((metric) => metric.direction === "min");
  const learningRate = metrics.find((metric) =>
    ["lr", "learning_rate"].includes(metric.metric_name.toLowerCase()),
  );
  const recommended = [findLoss(false), findLoss(true), keyMetric, learningRate]
    .filter((metric): metric is (typeof metrics)[number] => metric !== undefined)
    .map((metric) => metric.key);
  const unique = [...new Set(recommended)].slice(0, MAX_SELECTED_METRICS);
  return unique.length > 0 ? unique : metrics.slice(0, 1).map((metric) => metric.key);
}
