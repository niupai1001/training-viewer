import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { useLiveVersion } from "../live/LiveUpdates";
import type {
  Axis,
  MetricCatalogItem,
  MetricQueryResult,
  RunDetail,
  RunMonitoringSummary,
  SeriesPayload,
} from "../types";
import { formatDuration, formatMetricValue, formatNumber, unitLabel } from "../utils/format";
import { EmptyState, ErrorBlock, LoadingBlock } from "./Common";
import { MetricBrowserDrawer } from "./MetricBrowserDrawer";
import { MetricChart, type ChartLine } from "./MetricChart";
import { MetricEvaluationTable } from "./MetricEvaluationTable";

type ChartKind = "line" | "evaluation";
interface ChartView {
  id: string;
  title: string;
  keys: string[];
  axis: Axis;
  unit: string | null;
  kind: ChartKind;
  items: MetricCatalogItem[];
}

const VIEW_STORAGE_PREFIX = "training-viewer.chart-views.v1.";

export function TrainingOverview({ run }: { run: RunDetail }) {
  const liveVersion = useLiveVersion();
  const [browserOpen, setBrowserOpen] = useState(false);
  const [views, setViews] = useState<ChartView[]>([]);
  const [viewsLoaded, setViewsLoaded] = useState(false);
  const [range, setRange] = useState<{ min: number; max: number } | null>(null);
  const [lossMode, setLossMode] = useState<"full" | "late" | "log">("full");

  useEffect(() => {
    setRange(null);
    setLossMode("full");
  }, [run.run_id]);

  function updateRange(next: { min: number; max: number } | null) {
    setRange((current) => {
      if (!next) return null;
      if (current && Math.abs(current.min - next.min) < 1e-9 && Math.abs(current.max - next.max) < 1e-9) {
        return current;
      }
      return next;
    });
  }

  useEffect(() => {
    setViewsLoaded(false);
    try {
      const raw = window.localStorage.getItem(`${VIEW_STORAGE_PREFIX}${run.run_id}`);
      const parsed = raw ? (JSON.parse(raw) as ChartView[]) : [];
      setViews(
        Array.isArray(parsed)
          ? parsed.map((view) => ({ ...view, items: view.items ?? [] }))
          : [],
      );
    } catch {
      setViews([]);
    }
    setViewsLoaded(true);
  }, [run.run_id]);

  useEffect(() => {
    if (viewsLoaded) {
      window.localStorage.setItem(`${VIEW_STORAGE_PREFIX}${run.run_id}`, JSON.stringify(views));
    }
  }, [run.run_id, views, viewsLoaded]);

  const catalogState = useApi(
    () => api.metricCatalog(run.run_id, { limit: 100 }),
    [run.run_id, liveVersion],
  );
  const summaryState = useApi(() => api.runSummary(run.run_id), [run.run_id, liveVersion]);
  const catalog = catalogState.data?.items ?? [];
  const core = useMemo(() => {
    const trainLoss = catalog.find((item) => item.role === "train_loss");
    const valLoss = catalog.find((item) => item.role === "val_loss");
    const primary =
      catalog.find((item) => item.is_primary) ??
      catalog.find((item) => item.role === "validation_score" && item.direction === "max") ??
      catalog.find((item) => item.role === "validation_score");
    const learningRate = catalog.find((item) => item.role === "learning_rate");
    return { trainLoss, valLoss, primary, learningRate };
  }, [catalog]);
  const coreKeys = [core.trainLoss?.raw_key, core.valLoss?.raw_key, core.primary?.raw_key, core.learningRate?.raw_key]
    .filter((key): key is string => Boolean(key));
  const coreState = useApi<MetricQueryResult | null>(
    () => (coreKeys.length ? api.metrics(run.run_id, coreKeys, "auto", 2000, range?.min, range?.max) : Promise.resolve(null)),
    [run.run_id, coreKeys.join("|"), range?.min, range?.max, liveVersion],
  );
  const coreSeries = useMemo(
    () => new Map((coreState.data?.series ?? []).map((series) => [series.key, series])),
    [coreState.data],
  );

  const customKeys = useMemo(
    () => Array.from(new Set(views.flatMap((view) => view.keys))),
    [views],
  );
  const customState = useApi<MetricQueryResult | null>(
    () => (customKeys.length ? api.metrics(run.run_id, customKeys, "auto", 5000, range?.min, range?.max) : Promise.resolve(null)),
    [run.run_id, customKeys.join("|"), range?.min, range?.max, liveVersion],
  );
  const customSeries = useMemo(
    () => new Map((customState.data?.series ?? []).map((series) => [series.key, series])),
    [customState.data],
  );

  const knownKeys = new Set(run.metric_keys.map((metric) => metric.key));
  const missingKeys = customKeys.filter((key) => !knownKeys.has(key));

  function addToViews(items: MetricCatalogItem[], targetId: string | null): string | null {
    if (targetId) {
      const target = views.find((view) => view.id === targetId);
      if (!target) return "目标图表已不存在。";
      const incompatible = items.find(
        (item) =>
          (target.kind === "line" && item.value_kind !== "continuous") ||
          (target.kind === "evaluation" && item.value_kind !== "single_point") ||
          (item.unit ?? null) !== target.unit,
      );
      if (incompatible) return "单位/数据类型与目标图不兼容，已拒绝合并。";
      setViews((current) =>
        current.map((view) =>
          view.id === targetId
            ? {
                ...view,
                keys: Array.from(new Set([...view.keys, ...items.map((item) => item.raw_key)])),
                items: [...view.items, ...items.filter((item) => !view.items.some((known) => known.raw_key === item.raw_key))],
              }
            : view,
        ),
      );
      return null;
    }
    const groups = new Map<string, { kind: ChartKind; items: MetricCatalogItem[]; axis: Axis; unit: string | null }>();
    for (const item of items) {
      const axis = (item.available_axes[0] ?? "global_step") as Axis;
      const kind: ChartKind = item.value_kind === "continuous" ? "line" : "evaluation";
      const key = `${kind}|${item.unit ?? ""}|${axis}`;
      const group = groups.get(key) ?? { kind, items: [], axis, unit: item.unit ?? null };
      group.items.push(item);
      groups.set(key, group);
    }
    const created = Array.from(groups.values()).map((group, index) => ({
      id: `view-${Date.now()}-${index}`,
      title: group.items.length === 1 ? group.items[0].display_name_zh : `${group.items[0].display_name_zh} 等 ${group.items.length} 项`,
      keys: group.items.map((item) => item.raw_key),
      axis: group.axis,
      unit: group.unit,
      kind: group.kind,
      items: group.items,
    }));
    setViews((current) => [...current, ...created]);
    return null;
  }

  function renameView(id: string) {
    const target = views.find((view) => view.id === id);
    if (!target) return;
    const title = window.prompt("图表标题", target.title);
    if (title?.trim()) {
      setViews((current) => current.map((view) => (view.id === id ? { ...view, title: title.trim() } : view)));
    }
  }

  function moveView(id: string, direction: -1 | 1) {
    setViews((current) => {
      const index = current.findIndex((view) => view.id === id);
      const next = index + direction;
      if (index < 0 || next < 0 || next >= current.length) return current;
      const copy = [...current];
      [copy[index], copy[next]] = [copy[next], copy[index]];
      return copy;
    });
  }

  return (
    <section className="training-overview">
      <div className="overview-toolbar">
        <div>
          <div className="monitor-eyebrow">指标与图表</div>
        </div>
        <button type="button" className="button button-primary" onClick={() => setBrowserOpen(true)}>
          ＋ 添加图表 / 指标
        </button>
      </div>

      {run.metadata?.experiment_description ? (
        <details className="experiment-description">
          <summary>实验说明：数据、架构、改动、目标</summary>
          <dl>
            <dt>数据</dt><dd>{run.metadata.experiment_description.data_description}</dd>
            <dt>模型架构</dt><dd>{run.metadata.experiment_description.model_architecture}</dd>
            <dt>改动方案</dt><dd>{run.metadata.experiment_description.modification_plan}</dd>
            <dt>研究目标</dt><dd>{run.metadata.experiment_description.research_objective}</dd>
          </dl>
        </details>
      ) : null}

      <SummaryGrid run={run} core={core} series={coreSeries} summary={summaryState.data} />
      {catalogState.loading && !catalogState.data ? <LoadingBlock label="正在读取指标目录…" /> : null}
      {catalogState.error ? <ErrorBlock error={catalogState.error} onRetry={catalogState.reload} /> : null}
      {coreState.error ? <ErrorBlock error={coreState.error} onRetry={coreState.reload} /> : null}

      {range ? (
        <p className="chart-note">
          当前只查询 {formatNumber(range.min, 2)} – {formatNumber(range.max, 2)} 区间。
          <button type="button" className="link-button" onClick={() => setRange(null)}>重置区间</button>
        </p>
      ) : null}
      <div className="overview-charts">
        <CoreLossPanel train={core.trainLoss} val={core.valLoss} series={coreSeries} onRangeChange={updateRange} mode={lossMode} onModeChange={setLossMode} />
        <CoreValidationPanel metric={core.primary} series={coreSeries} onRangeChange={updateRange} />
      </div>

      {missingKeys.length > 0 ? (
        <p className="notice notice-warning">
          自定义视图引用了 {missingKeys.length} 个已不存在的指标：{missingKeys.join("、")}。请删除或重新添加。
        </p>
      ) : null}
      {views.length > 0 ? (
        <section className="custom-charts">
          <div className="section-heading">
            <h3>自定义图表</h3>
            <span className="muted small">按 Run 保存在浏览器用户状态中</span>
          </div>
          {views.map((view, index) => {
            const series = view.keys.map((key) => customSeries.get(key)).filter(Boolean) as SeriesPayload[];
            const missing = view.keys.filter((key) => !customSeries.has(key));
            if (missing.length > 0) {
              return (
                <div key={view.id} className="notice notice-warning">
                  「{view.title}」缺少指标：{missing.join("、")}
                  <button type="button" className="link-button" onClick={() => setViews((current) => current.filter((item) => item.id !== view.id))}>
                    删除视图
                  </button>
                </div>
              );
            }
            return (
              <article key={view.id} className="custom-chart-card">
                <div className="custom-chart-header">
                  <h3>{view.title}</h3>
                  <div className="custom-chart-actions">
                    <button type="button" className="link-button" onClick={() => moveView(view.id, -1)} disabled={index === 0}>上移</button>
                    <button type="button" className="link-button" onClick={() => moveView(view.id, 1)} disabled={index === views.length - 1}>下移</button>
                    <button type="button" className="link-button" onClick={() => renameView(view.id)}>重命名</button>
                    <button type="button" className="link-button" onClick={() => setViews((current) => current.filter((item) => item.id !== view.id))}>删除</button>
                  </div>
                </div>
                {view.kind === "evaluation" ? (
                  <MetricEvaluationTable items={view.items} series={series} />
                ) : (
                  <MetricChart
                    title={view.title}
                    lines={view.keys.map((key, lineIndex) => toLine(series.find((entry) => entry.key === key), key, lineIndex))}
                    axis={view.axis}
                    smoothing="none"
                    smoothingWindow={5}
                    logScale={false}
                    showRaw={false}
                    height={360}
                    group={`run-custom-${run.run_id}`}
                    onRangeChange={updateRange}
                    emptyMessage="该指标没有可用数据点。"
                  />
                )}
              </article>
            );
          })}
        </section>
      ) : null}

      <details className="advanced-metrics">
        <summary>高级分析 · 全部指标表</summary>
        <p className="muted small">这里只做只读清单；添加曲线请使用右上角“添加图表 / 指标”。</p>
        <div className="metric-raw-list">
          {catalog.slice(0, 100).map((item) => (
            <div key={item.raw_key}>
              <code>{item.raw_key}</code> · {item.point_count} 点 · {unitLabel(item.unit) || "单位未声明"}
            </div>
          ))}
        </div>
      </details>

      <MetricBrowserDrawer
        runId={run.run_id}
        open={browserOpen}
        charts={views.map((view) => ({ id: view.id, title: view.title, unit: view.unit }))}
        onClose={() => setBrowserOpen(false)}
        onAdd={(items, targetId) => {
          const error = addToViews(items, targetId);
          return error;
        }}
      />
    </section>
  );
}

function SummaryGrid({
  run,
  core,
  series,
  summary,
}: {
  run: RunDetail;
  core: { trainLoss?: MetricCatalogItem; valLoss?: MetricCatalogItem; primary?: MetricCatalogItem; learningRate?: MetricCatalogItem };
  series: Map<string, SeriesPayload>;
  summary?: RunMonitoringSummary | null;
}) {
  const train = core.trainLoss ? series.get(core.trainLoss.raw_key) : undefined;
  const val = core.valLoss ? series.get(core.valLoss.raw_key) : undefined;
  const primary = core.primary ? series.get(core.primary.raw_key) : undefined;
  const lr = core.learningRate ? series.get(core.learningRate.raw_key) : undefined;
  const fallbackLast = [train?.last, val?.last, primary?.last, lr?.last]
    .filter((point): point is NonNullable<SeriesPayload["last"]> => Boolean(point))
    .sort((a, b) => (Date.parse(b.timestamp ?? "") || 0) - (Date.parse(a.timestamp ?? "") || 0))[0];
  const currentEpoch = summary?.current_epoch ?? fallbackLast?.epoch ?? null;
  const currentStep = summary?.current_global_step ?? fallbackLast?.global_step ?? null;
  const timing = summary?.timing;
  const activeSeconds = timing?.active_training_seconds ?? null;
  const wallSeconds = timing?.wall_span_seconds ?? run.duration_seconds;
  const timeValue =
    activeSeconds != null
      ? formatDuration(activeSeconds)
      : wallSeconds != null
        ? formatDuration(wallSeconds)
        : "未记录";
  const timeLabel = activeSeconds != null ? "累计运行时长" : "日志跨度";
  const timeNote =
    activeSeconds != null
      ? `日志跨度 ${wallSeconds != null ? formatDuration(wallSeconds) : "未记录"}；${timing?.quality ?? ""}`
      : "指标首末；不是有效训练时长";
  const trainValue = summary?.train_loss?.latest ?? train?.last;
  const valValue = summary?.val_loss?.latest ?? val?.last;
  const primaryMetric = summary?.primary_validation_metric;
  const primaryBest = primaryMetric?.best ?? primary?.best;
  const lrValue = summary?.learning_rate?.latest ?? lr?.last;
  return (
    <div className="summary-grid">
      <div className="summary-card">
        <span className="summary-label">{timeLabel}</span>
        <strong>{timeValue}</strong>
        <span className="muted small">{timeNote}</span>
      </div>
      <div className="summary-card">
        <span className="summary-label">Epoch / Step</span>
        <strong>{currentEpoch != null ? `E${currentEpoch}` : "—"} / {currentStep != null ? `S${currentStep}` : "—"}</strong>
        <span className="muted small">计划 {summary?.planned_epochs ?? "未记录"}</span>
      </div>
      <div className="summary-card">
        <span className="summary-label">Train Loss</span>
        <strong>{trainValue ? formatMetricValue(trainValue.value, summary?.train_loss?.unit ?? train?.unit) : "未记录"}</strong>
        <span className="muted small">最新训练损失</span>
      </div>
      <div className="summary-card">
        <span className="summary-label">Validation Loss</span>
        <strong>{valValue ? formatMetricValue(valValue.value, summary?.val_loss?.unit ?? val?.unit) : "未记录"}</strong>
        <span className="muted small">{valValue?.global_step != null ? `最近验证：S${valValue.global_step}` : "尚无验证记录"}</span>
      </div>
      <div className="summary-card">
        <span className="summary-label">最佳验证指标</span>
        <strong>{primaryBest ? formatMetricValue(primaryBest.value, primaryMetric?.unit ?? primary?.unit) : "未记录"}</strong>
        <span className="muted small">{primaryMetric?.display_name ?? core.primary?.display_name_zh ?? (core.valLoss ? "最佳验证损失（越低越好）" : "未定义/未记录")}</span>
      </div>
      <div className="summary-card">
        <span className="summary-label">Learning Rate</span>
        <strong>{lrValue ? formatMetricValue(lrValue.value) : "未记录"}</strong>
        <span className="muted small">最近记录；多参数组未合并</span>
      </div>
    </div>
  );
}

function CoreLossPanel({
  train,
  val,
  series,
  onRangeChange,
  mode,
  onModeChange,
}: {
  train?: MetricCatalogItem;
  val?: MetricCatalogItem;
  series: Map<string, SeriesPayload>;
  onRangeChange: (range: { min: number; max: number } | null) => void;
  mode: "full" | "late" | "log";
  onModeChange: (mode: "full" | "late" | "log") => void;
}) {
  const lines: ChartLine[] = [];
  const trainPayload = train ? series.get(train.raw_key) : undefined;
  const valPayload = val ? series.get(val.raw_key) : undefined;
  const rawLines: ChartLine[] = [];
  if (trainPayload) rawLines.push(toLine(trainPayload, train!.display_name_zh, 0));
  if (valPayload) rawLines.push(toLine(valPayload, val!.display_name_zh, 1));
  const allX = rawLines.flatMap((line) => line.points.map((point) => point.x)).filter((x): x is number => typeof x === "number");
  const threshold = allX.length ? Math.max(...allX) - (Math.max(...allX) - Math.min(...allX)) * 0.2 : null;
  for (const line of rawLines) {
    lines.push(
      mode === "late" && threshold != null
        ? { ...line, points: line.points.filter((point) => typeof point.x === "number" && point.x >= threshold) }
        : line,
    );
  }
  if (rawLines.length === 0) {
    return <EmptyState title="未记录 Loss" description="日志没有可识别的 Train/Val Loss；不会补造曲线。" />;
  }
  if (rawLines.every((line) => line.points.length <= 1)) {
    return (
      <section className="core-chart-card">
        <div className="section-heading"><h3>Loss</h3><span className="muted small">仅单点，按评估结果展示</span></div>
        <MetricEvaluationTable
          items={[train, val].filter((item): item is MetricCatalogItem => Boolean(item))}
          series={[trainPayload, valPayload].filter((item): item is SeriesPayload => Boolean(item))}
        />
      </section>
    );
  }
  const compatible =
    !trainPayload ||
    !valPayload ||
    (trainPayload.axis === valPayload.axis && (trainPayload.unit ?? null) === (valPayload.unit ?? null));
  if (!compatible) {
    return (
      <section className="core-chart-card">
        <div className="section-heading"><h3>Loss</h3></div>
        <p className="notice notice-warning">Train/Val Loss 的横轴或单位不一致，已分图，不能宣称可直接叠加。</p>
        {trainPayload ? (
          <MetricChart title="Train Loss" lines={[toLine(trainPayload, train!.display_name_zh, 0)]} axis={trainPayload.axis} smoothing="none" smoothingWindow={5} logScale={false} showRaw={false} height={260} group={`run-core-${train!.raw_key}`} onRangeChange={onRangeChange} emptyMessage="Loss 没有数据点。" />
        ) : null}
        {valPayload ? (
          <MetricChart title="Validation Loss" lines={[toLine(valPayload, val!.display_name_zh, 0)]} axis={valPayload.axis} smoothing="none" smoothingWindow={5} logScale={false} showRaw={false} height={260} group={`run-core-${val!.raw_key}`} onRangeChange={onRangeChange} emptyMessage="Loss 没有数据点。" />
        ) : null}
      </section>
    );
  }
  return (
    <section className="core-chart-card">
      <div className="section-heading">
        <h3>{valPayload ? "Train / Validation Loss" : "Train Loss"}</h3>
        <LossModeSwitch mode={mode} onChange={onModeChange} />
      </div>
      <MetricChart
        title="Loss"
        lines={lines}
        axis={trainPayload?.axis ?? valPayload?.axis ?? "global_step"}
        smoothing="none"
        smoothingWindow={5}
        logScale={mode === "log"}
        showRaw={false}
        height={330}
        group={`run-core-${train?.raw_key ?? val?.raw_key ?? "loss"}`}
        onRangeChange={onRangeChange}
        emptyMessage="Loss 没有数据点。"
      />
      {mode === "late" ? <p className="chart-note">后期聚焦：只显示最后 20% 横轴范围；原始数据未修改。</p> : null}
      {mode === "log" ? <p className="chart-note">对数轴：零/负值存在时会自动退回线性并提示。</p> : null}
      {!valPayload ? <p className="muted small">未记录验证损失（Validation Loss）。</p> : null}
    </section>
  );
}

function CoreValidationPanel({
  metric,
  series,
  onRangeChange,
}: {
  metric?: MetricCatalogItem;
  series: Map<string, SeriesPayload>;
  onRangeChange: (range: { min: number; max: number } | null) => void;
}) {
  const payload = metric ? series.get(metric.raw_key) : undefined;
  if (!metric || !payload) {
    return <EmptyState title="未记录主验证指标" description="没有可识别的验证分数；未知字段不会猜测为 mIoU。" />;
  }
  if (metric.value_kind === "single_point") {
    return (
      <section className="core-chart-card">
        <div className="section-heading">
          <h3>{metric.display_name_zh}</h3>
          <span className="muted small">仅 1 个数据点，按评估结果展示</span>
        </div>
        <MetricEvaluationTable items={[metric]} series={[payload]} />
      </section>
    );
  }
  return (
    <section className="core-chart-card">
      <div className="section-heading">
        <h3>{metric.display_name_zh}</h3>
        <span className="muted small">原始键 {metric.raw_key}</span>
      </div>
      <MetricChart
        title={metric.display_name_zh}
        lines={[toLine(payload, metric.display_name_zh, 0)]}
        axis={payload.axis}
        smoothing="none"
        smoothingWindow={5}
        logScale={false}
        showRaw={false}
        height={300}
        group={`run-core-${metric.raw_key}`}
        onRangeChange={onRangeChange}
        emptyMessage="该指标没有数据点。"
      />
    </section>
  );
}

function LossModeSwitch({
  mode,
  onChange,
}: {
  mode: "full" | "late" | "log";
  onChange: (mode: "full" | "late" | "log") => void;
}) {
  return (
    <div className="chart-mode-switch" role="group" aria-label="Loss 显示模式">
      {([
        ["full", "全程"],
        ["late", "后期"],
        ["log", "对数"],
      ] as const).map(([value, label]) => (
        <button
          key={value}
          type="button"
          className={mode === value ? "active" : ""}
          aria-pressed={mode === value}
          onClick={() => onChange(value)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function toLine(series: SeriesPayload | undefined, label: string, index: number): ChartLine {
  return {
    id: series?.key ?? `missing-${index}`,
    label,
    points: series?.points ?? [],
    unit: series?.unit ?? null,
  };
}
