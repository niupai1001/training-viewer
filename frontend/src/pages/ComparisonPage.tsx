import { useEffect, useMemo, useRef, useState } from "react";
import { api, downloadCompareExport } from "../api/client";
import { useApi } from "../hooks/useApi";
import { useLiveVersion } from "../live/LiveUpdates";
import type { CompareResult, MetricKey } from "../types";
import { useRoute } from "../navigation/route";
import { formatNumber, unitLabel, directionLabel } from "../utils/format";
import {
  EmptyState,
  ErrorBlock,
  LoadingBlock,
  PageHeader,
  Panel,
  WarningList,
} from "../components/Common";
import { ChartControls, DEFAULT_CHART_PREFERENCES } from "../components/ChartControls";
import type { ChartPreferences } from "../components/ChartControls";
import { MetricChart } from "../components/MetricChart";
import { BestLastTable } from "../components/BestLastTable";
import { HyperparameterDiffTable, RunFieldsTable } from "../components/ComparisonTables";
import { RunSelector } from "../components/RunSelector";

const MAX_COMPARE_RUNS = 12;

export function ComparisonPage() {
  const route = useRoute();
  const liveVersion = useLiveVersion();
  const routeKey = route.params.toString();
  const [selectedIds, setSelectedIds] = useState<string[]>(() =>
    (route.params.get("runs") ?? "").split(",").filter(Boolean).slice(0, MAX_COMPARE_RUNS),
  );
  const [selectedSeries, setSelectedSeries] = useState<string[]>(() =>
    (route.params.get("series") ?? "").split(",").filter(Boolean),
  );
  const [preferences, setPreferences] = useState<ChartPreferences>(() => ({
    ...DEFAULT_CHART_PREFERENCES,
    axis: (route.params.get("axis") as ChartPreferences["axis"]) || DEFAULT_CHART_PREFERENCES.axis,
  }));
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const explicitSeriesRef = useRef(route.params.has("series"));

  useEffect(() => {
    explicitSeriesRef.current = route.params.has("series");
    setSelectedIds(
      (route.params.get("runs") ?? "").split(",").filter(Boolean).slice(0, MAX_COMPARE_RUNS),
    );
    setSelectedSeries((route.params.get("series") ?? "").split(",").filter(Boolean));
    const axis = route.params.get("axis");
    if (axis === "global_step" || axis === "epoch" || axis === "timestamp") {
      setPreferences((current) => ({ ...current, axis }));
    }
    // 仅在外部导航改变地址栏参数时同步。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeKey]);

  const runsState = useApi(() => api.runs({ limit: 1000, sort: "-last_updated_at" }), [liveVersion]);
  const metricKeysState = useApi(
    () => Promise.all(selectedIds.map((runId) => api.metricKeys(runId))),
    [selectedIds.join(","), liveVersion],
  );

  const availableKeys = useMemo(() => {
    const union = new Map<
      string,
      { key: string; phase: string; metricName: string; unit: string | null; direction: MetricKey["direction"]; definition: string | null; presentIn: string[] }
    >();
    for (const result of metricKeysState.data ?? []) {
      for (const metric of result.metric_keys) {
        const existing = union.get(metric.key);
        if (existing) {
          existing.presentIn.push(result.run_id);
          existing.unit = existing.unit ?? metric.unit;
          existing.direction = existing.direction ?? metric.direction;
          existing.definition = existing.definition ?? metric.definition;
        } else {
          union.set(metric.key, {
            key: metric.key,
            phase: metric.phase,
            metricName: metric.metric_name,
            unit: metric.unit,
            direction: metric.direction,
            definition: metric.definition,
            presentIn: [result.run_id],
          });
        }
      }
    }
    return Array.from(union.values());
  }, [metricKeysState.data]);

  const availableSignature = availableKeys.map((item) => item.key).join("|");

  useEffect(() => {
    if (selectedIds.length === 0) {
      setSelectedSeries([]);
      return;
    }
    if (availableKeys.length === 0) {
      // 指标列表尚未加载完成时保留地址栏或用户已选择的指标。
      return;
    }
    if (explicitSeriesRef.current) {
      // 地址栏（例如保存的对比视图）指定了指标时，不自动替换用户选择。
      return;
    }
    setSelectedSeries((current) => {
      const valid = current.filter((key) => availableKeys.some((item) => item.key === key));
      if (valid.length > 0) {
        return valid;
      }
      const complete = availableKeys.filter(
        (item) => item.presentIn.length === selectedIds.length,
      );
      const preferred =
        complete.find(
          (item) =>
            item.phase === "val" && (item.direction === "min" || item.direction === "max"),
        ) ??
        complete.find((item) => item.direction === "min" || item.direction === "max") ??
        availableKeys[0];
      return preferred ? [preferred.key] : [];
    });
    // 只在运行集合或可用指标变化时修正选择。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedIds.join(","), availableSignature]);

  const compareState = useApi<CompareResult | null>(
    () =>
      selectedIds.length === 0 || selectedSeries.length === 0
        ? Promise.resolve(null)
        : api.compare({
            run_ids: selectedIds,
            series: selectedSeries,
            axis: preferences.axis,
            max_points: 1500,
          }),
    [selectedIds.join(","), selectedSeries.join(","), preferences.axis, liveVersion],
  );

  useEffect(() => {
    const params = new URLSearchParams();
    if (selectedIds.length > 0) {
      params.set("runs", selectedIds.join(","));
    }
    if (selectedSeries.length > 0) {
      params.set("series", selectedSeries.join(","));
    }
    params.set("axis", preferences.axis);
    window.history.replaceState(null, "", `#/compare?${params.toString()}`);
    // 使用 replaceState 避免每次切换指标都增加浏览器历史记录。
  }, [selectedIds, selectedSeries, preferences.axis]);

  const selectedRuns = (runsState.data?.runs ?? []).filter((run) => selectedIds.includes(run.run_id));

  async function handleExport(format: "csv" | "json") {
    if (selectedIds.length === 0 || selectedSeries.length === 0) {
      return;
    }
    setError(null);
    try {
      await downloadCompareExport(
        {
          run_ids: selectedIds,
          series: selectedSeries,
          axis: preferences.axis,
          max_points: 1500,
        },
        format,
        {
          method: preferences.smoothing,
          window: preferences.smoothingWindow,
          scale: preferences.logScale ? "log" : "linear",
        },
      );
      setNotice(`已导出对比数据（${format.toUpperCase()}）。`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  }

  async function handleSaveView() {
    if (selectedIds.length === 0) {
      return;
    }
    const name = window.prompt("为这组对比视图命名：", "未命名对比");
    if (!name) {
      return;
    }
    setError(null);
    try {
      await api.createSavedView({
        name,
        view_kind: "comparison",
        payload: {
          run_ids: selectedIds,
          series: selectedSeries,
          axis: preferences.axis,
          smoothing: preferences.smoothing,
          smoothing_window: preferences.smoothingWindow,
          scale: preferences.logScale ? "log" : "linear",
        },
      });
      setNotice(`已保存对比视图“${name}”，可在总览页重新打开。`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  }

  return (
    <div className="page comparison-page">
      <PageHeader
        title="实验对比"
        subtitle="叠加同一指标定义下的多个运行。不同运行各自保持原始采样，不插值、不截断。"
        actions={
          <div className="header-actions">
            <button
              type="button"
              className="button"
              disabled={selectedIds.length === 0}
              onClick={handleSaveView}
            >
              保存对比视图
            </button>
            <button
              type="button"
              className="button"
              disabled={selectedIds.length === 0 || selectedSeries.length === 0}
              onClick={() => handleExport("csv")}
            >
              导出 CSV
            </button>
            <button
              type="button"
              className="button"
              disabled={selectedIds.length === 0 || selectedSeries.length === 0}
              onClick={() => handleExport("json")}
            >
              导出 JSON
            </button>
          </div>
        }
      />

      {notice ? <p className="notice">{notice}</p> : null}
      {error ? <p className="notice notice-error">{error}</p> : null}

      <div className="comparison-layout">
        <aside className="comparison-sidebar">
          <Panel title="选择运行">
            {runsState.loading ? <LoadingBlock label="正在加载运行列表…" /> : null}
            {runsState.error ? <ErrorBlock error={runsState.error} onRetry={runsState.reload} /> : null}
            <RunSelector
              runs={runsState.data?.runs ?? []}
              selectedIds={selectedIds}
              maxSelected={MAX_COMPARE_RUNS}
              onChange={setSelectedIds}
            />
          </Panel>
        </aside>

        <div className="comparison-main">
          {selectedIds.length === 0 ? (
            <EmptyState
              title="请选择要对比的运行"
              description="从左侧勾选两个或更多运行。也可以从实验管理页批量选中后点击“实验对比”。"
            />
          ) : (
            <>
              <Panel title="对比指标">
                {metricKeysState.loading ? <LoadingBlock label="正在读取指标定义…" /> : null}
                {metricKeysState.error ? (
                  <ErrorBlock error={metricKeysState.error} onRetry={metricKeysState.reload} />
                ) : null}
                {availableKeys.length === 0 ? (
                  <p className="muted">所选运行没有可用指标。</p>
                ) : (
                  <div className="metric-chips">
                    {availableKeys.map((metric) => {
                      const active = selectedSeries.includes(metric.key);
                      return (
                        <button
                          key={metric.key}
                          type="button"
                          className={`metric-chip ${active ? "metric-chip-active" : ""}`}
                          onClick={() =>
                            setSelectedSeries((current) =>
                              current.includes(metric.key)
                                ? current.filter((key) => key !== metric.key)
                                : [...current, metric.key],
                            )
                          }
                          title={`单位：${metric.unit ?? "未声明"}；方向：${directionLabel(
                            metric.direction,
                          )}；${metric.definition ?? "未提供定义"}`}
                        >
                          <span>{metric.key}</span>
                          <span className="muted small">
                            出现于 {metric.presentIn.length}/{selectedIds.length} 个运行 ·{" "}
                            {metric.presentIn.length < selectedIds.length ? "部分运行缺失" : "全部运行"}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                )}
              </Panel>

              <ChartControls
                value={preferences}
                onChange={setPreferences}
              />

              {compareState.loading ? <LoadingBlock label="正在读取对比数据…" /> : null}
              {compareState.error ? (
                <ErrorBlock error={compareState.error} onRetry={compareState.reload} />
              ) : null}
              {compareState.data?.warnings.length ? (
                <WarningList warnings={compareState.data.warnings} />
              ) : null}

              {compareState.data?.series.map((series) => {
                const runLines = series.runs.map((run) => ({
                  id: run.run_id,
                  label: run.name,
                  points: run.points,
                  unit: series.unit,
                }));
                const downsampled = series.runs.some((run) => run.downsampled);
                return (
                  <section key={series.key} className="comparison-series">
                    <MetricChart
                      title={series.key}
                      subtitle={`单位：${unitLabel(series.unit) || "未声明"} · ${directionLabel(
                        series.direction,
                      )}${series.definition ? ` · 定义：${series.definition}` : ""}`}
                      lines={runLines}
                      axis={preferences.axis}
                      smoothing={preferences.smoothing}
                      smoothingWindow={preferences.smoothingWindow}
                      logScale={preferences.logScale}
                      showRaw={preferences.showRaw}
                      group="comparison"
                      downsampled={downsampled}
                      emptyMessage={`没有运行在${preferences.axis}横轴上记录该指标。`}
                    />
                    {series.warnings.length > 0 ? <WarningList warnings={series.warnings} /> : null}
                    <p className="muted small">
                      返回点数：{series.runs.map((run) => `${run.name}: ${formatNumber(run.returned_points, 0)}`).join("；")}
                    </p>
                  </section>
                );
              })}

              {compareState.data && compareState.data.series.length > 0 ? (
                <>
                  <Panel title="最佳值与最终值">
                    <BestLastTable series={compareState.data.series} runs={compareState.data.runs} />
                    <p className="muted small">
                      最佳值使用未平滑的原始采样；最终值是该运行最新的有效记录。只有单位、数据集和定义一致且指标声明了方向时，才会标记最优。
                    </p>
                  </Panel>

                  <Panel title="运行关键字段">
                    <RunFieldsTable
                      fields={compareState.data.run_fields}
                      runs={compareState.data.runs.map((run) => ({ run_id: run.run_id, name: run.name }))}
                    />
                  </Panel>

                  <Panel title="超参数差异">
                    <HyperparameterDiffTable
                      rows={compareState.data.hyperparameters.rows}
                      runs={compareState.data.runs.map((run) => ({ run_id: run.run_id, name: run.name }))}
                    />
                  </Panel>
                </>
              ) : null}

              {selectedRuns.length > 0 ? (
                <p className="muted small">
                  当前对比的运行：{selectedRuns.map((run) => run.name).join("、")}。图表之间已同步鼠标悬停与缩放。
                </p>
              ) : null}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
