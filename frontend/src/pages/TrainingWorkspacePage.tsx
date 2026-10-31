import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { useLiveVersion } from "../live/LiveUpdates";
import { useRoute } from "../navigation/route";
import type { CompareResult, MetricKey, RunDetail, RunSummary } from "../types";
import { formatDateTime, formatRelativeTime, unitLabel } from "../utils/format";
import {
  EmptyState,
  ErrorBlock,
  LoadingBlock,
  Panel,
  StatusBadge,
} from "../components/Common";
import { RunSelector } from "../components/RunSelector";
import { RunMetricsTab } from "../components/RunMetricsTab";
import { RunConfigTab } from "../components/RunConfigTab";
import { RunDiagnosticsTab } from "../components/RunDiagnosticsTab";
import { MetricChart } from "../components/MetricChart";
import { BestLastTable } from "../components/BestLastTable";
import { HyperparameterDiffTable, RunFieldsTable } from "../components/ComparisonTables";
import { LatestArtifactPreview } from "../components/LatestArtifactPreview";
import { ResultCandidatePanel } from "../components/ResultCandidatePanel";
import { SourceInventoryPanel } from "../components/SourceInventoryPanel";
import { RootDirectoriesPanel } from "../components/RootDirectoriesPanel";

const LAST_RUN_KEY = "training-viewer.last-selected-run";
const MAX_SELECTED = 8;

export function TrainingWorkspacePage() {
  const route = useRoute();
  const liveVersion = useLiveVersion();
  const runsState = useApi(() => api.runs({ limit: 200, sort: "-last_updated_at" }), [liveVersion]);
  const runs = runsState.data?.runs ?? [];
  const routeRun = /^\/runs\/([^/]+)$/.exec(route.path);
  const routeRuns = (route.params.get("runs") ?? "").split(",").filter(Boolean);
  const [selectedIds, setSelectedIds] = useState<string[]>(() =>
    routeRun ? [decodeURIComponent(routeRun[1])] : routeRuns.slice(0, MAX_SELECTED),
  );
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const initialized = useRef(selectedIds.length > 0);
  const projectFilter = route.params.get("project");
  const visibleRuns = projectFilter
    ? runs.filter((run) => run.project === projectFilter)
    : runs;

  useEffect(() => {
    if (initialized.current || runs.length === 0) {
      return;
    }
    initialized.current = true;
    const stored = window.localStorage.getItem(LAST_RUN_KEY);
    const realRuns = runs.filter((run) => !run.metadata_synthetic);
    const pool = realRuns.length > 0 ? realRuns : runs;
    const active = pool.find((run) => run.activity === "updating" || run.status === "running");
    const preferred =
      (stored ? runs.find((run) => run.run_id === stored) : undefined) ??
      active ??
      pool[0];
    if (preferred) {
      setSelectedIds([preferred.run_id]);
      window.localStorage.setItem(LAST_RUN_KEY, preferred.run_id);
    }
  }, [runs]);

  function select(ids: string[]) {
    setSelectedIds(ids);
    if (ids[0]) {
      window.localStorage.setItem(LAST_RUN_KEY, ids[0]);
    }
  }

  const primaryId = selectedIds[0];
  const primaryState = useApi(
    () => (primaryId ? api.run(primaryId) : Promise.resolve(null)),
    [primaryId, liveVersion],
  );
  const primary = primaryState.data ?? null;
  const selectedRuns = runs.filter((run) => selectedIds.includes(run.run_id));

  return (
    <div className="workspace-page">
      <div className="workspace-toolbar">
        <div>
          <h1>训练工作区</h1>
          <p className="muted">
            左侧选择运行；选中两个以上时自动叠加共同指标。曲线优先，诊断在高级抽屉。
          </p>
        </div>
        <div className="workspace-toolbar-actions">
          <a className="button button-small" href="#/diagnostics">
            目录与设置
          </a>
          <button
            type="button"
            className="button button-small"
            onClick={() => setAdvancedOpen(true)}
            disabled={!primary}
          >
            高级分析
          </button>
        </div>
      </div>

      {runsState.error ? <ErrorBlock error={runsState.error} onRetry={runsState.reload} /> : null}
      {runsState.loading && runs.length === 0 ? <LoadingBlock label="正在读取训练记录…" /> : null}
      {!runsState.loading && runs.length === 0 ? (
        <Panel title="添加训练目录">
          <RootDirectoriesPanel />
        </Panel>
      ) : null}

      <div className="workspace-layout">
        <aside className="workspace-tree">
          <RunSelector
            runs={visibleRuns}
            selectedIds={selectedIds}
            onChange={select}
            maxSelected={MAX_SELECTED}
          />
        </aside>
        <main className="workspace-main">
          {selectedIds.length === 0 ? (
            <EmptyState
              title="从左侧选择一个训练"
              description="首次打开会恢复你上次主动选择的运行；没有记录时才选择活跃/最近运行。"
            />
          ) : null}
          {selectedIds.length === 1 && primaryId ? (
            <WorkspaceRunPanel
              runId={primaryId}
              run={primary}
              loading={primaryState.loading}
              error={primaryState.error}
              onRetry={primaryState.reload}
              onAddComparison={(ids) => select([...new Set([...selectedIds, ...ids])])}
            />
          ) : null}
          {selectedIds.length > 1 ? (
            <WorkspaceComparison selectedRuns={selectedRuns} selectedIds={selectedIds} />
          ) : null}
        </main>
      </div>

      {advancedOpen ? (
        <div className="drawer-backdrop" onClick={() => setAdvancedOpen(false)}>
          <aside className="advanced-drawer" onClick={(event) => event.stopPropagation()}>
            <header>
              <h2>高级分析</h2>
              <button type="button" className="button button-small" onClick={() => setAdvancedOpen(false)}>
                关闭
              </button>
            </header>
            {primary ? (
              <>
                <RunConfigTab run={primary} />
                <RunDiagnosticsTab run={primary} />
              </>
            ) : (
              <p className="muted">选择运行后显示配置与诊断。</p>
            )}
            <SourceInventoryPanel />
            <div className="drawer-footer">
              <a href="#/diagnostics">目录、来源映射与完整诊断</a>
            </div>
          </aside>
        </div>
      ) : null}
    </div>
  );
}

function WorkspaceRunPanel({
  runId,
  run,
  loading,
  error,
  onRetry,
  onAddComparison,
}: {
  runId: string;
  run: RunDetail | null;
  loading: boolean;
  error: Error | null;
  onRetry: () => void;
  onAddComparison: (ids: string[]) => void;
}) {
  const [adding, setAdding] = useState(false);
  if (loading && !run) {
    return <LoadingBlock label="正在读取运行…" />;
  }
  if (error) {
    return <ErrorBlock error={error} onRetry={onRetry} />;
  }
  if (!run) {
    return <EmptyState title="运行不存在" description={`找不到 ${runId}；索引可能已重建。`} />;
  }
  const currentRun = run;
  const epoch = maxEpoch(currentRun.metric_keys);
  const planned = typeof (currentRun.config as Record<string, unknown>).epochs === "number"
    ? Number((currentRun.config as Record<string, unknown>).epochs)
    : null;
  async function addSimilar() {
    setAdding(true);
    try {
      const candidate = await api.runs({
        project: currentRun.project,
        dataset: currentRun.dataset?.name ?? undefined,
        limit: 20,
        sort: "-last_updated_at",
      });
      const ids = candidate.runs
        .filter((item) => item.run_id !== currentRun.run_id && item.dataset?.name === currentRun.dataset?.name)
        .slice(0, 2)
        .map((item) => item.run_id);
      if (ids.length > 0) {
        onAddComparison(ids);
      }
    } finally {
      setAdding(false);
    }
  }
  return (
    <>
      <section className="workspace-run-header">
        <div>
          <div className="monitor-eyebrow">当前运行</div>
          <div className="workspace-run-title">
            <h2>{run.name}</h2>
            <StatusBadge status={run.status} label={run.status_label} reason={run.status_reason} />
            <span className={`activity-badge activity-${run.activity}`} title={run.status_reason}>
              {run.activity_label}
            </span>
          </div>
          <p className="muted">
            {run.project}
            {run.experiment ? ` / ${run.experiment}` : ""} · 最近更新{" "}
            {formatRelativeTime(run.last_metric_at ?? run.last_updated_at)} ·{" "}
            {epoch > 0 ? `${epoch} 个训练轮次` : "尚无轮次"}
            {planned ? ` / 计划 ${planned}` : ""}
          </p>
        </div>
        <div className="workspace-run-actions">
          <button type="button" className="button button-small" onClick={addSimilar} disabled={adding}>
            {adding ? "查找中…" : "加入同数据集对比"}
          </button>
        </div>
      </section>
      <RunMetricsTab run={currentRun} chartLimit={2} />
      <LatestArtifactPreview runId={currentRun.run_id} />
      <ResultCandidatePanel runId={currentRun.run_id} />
    </>
  );
}

function WorkspaceComparison({
  selectedRuns,
  selectedIds,
}: {
  selectedRuns: RunSummary[];
  selectedIds: string[];
}) {
  const liveVersion = useLiveVersion();
  const firstId = selectedIds[0];
  const keysState = useApi(() => api.metricKeys(firstId), [firstId, liveVersion]);
  const seriesKeys = useMemo(
    () =>
      recommendedCompareKeys(
        keysState.data?.metric_keys ?? [],
        window.localStorage.getItem("training-viewer.last-primary-metric"),
      ),
    [keysState.data],
  );
  const compareState = useApi<CompareResult | null>(
    () =>
      seriesKeys.length > 0
        ? api.compare({
            run_ids: selectedIds,
            series: seriesKeys,
            axis: "auto",
            max_points: 1500,
          })
        : Promise.resolve(null),
    [selectedIds.join(","), seriesKeys.join("|"), liveVersion],
  );
  return (
    <>
      <section className="workspace-run-header">
        <div>
          <div className="monitor-eyebrow">对比</div>
          <div className="workspace-run-title">
            <h2>{selectedIds.length} 个训练叠加</h2>
          </div>
          <p className="muted">
            {selectedRuns.map((run) => run.name).join(" · ")} · 自动选择共同指标，不做缺失插值。
          </p>
        </div>
      </section>
      {keysState.loading ? <LoadingBlock label="正在读取指标…" /> : null}
      {keysState.error ? <ErrorBlock error={keysState.error} onRetry={keysState.reload} /> : null}
      {keysState.data && seriesKeys.length === 0 ? (
        <EmptyState title="这些运行没有可比较的指标" description="请选择另一个包含 Loss/验证指标的运行。" />
      ) : null}
      {compareState.error ? <ErrorBlock error={compareState.error} onRetry={compareState.reload} /> : null}
      {compareState.data ? (
        <>
          {compareState.data.warnings.length > 0 ? (
            <div className="notice notice-warning">
              {compareState.data.warnings.map((warning) => <div key={warning.code}>{warning.message}</div>)}
            </div>
          ) : null}
          <div className="chart-stack">
            {compareState.data.series.map((series) => (
              <MetricChart
                key={series.key}
                title={series.key}
                subtitle={`单位：${unitLabel(series.unit) || "未声明"}`}
                lines={series.runs.map((run) => ({
                  id: `${series.key}-${run.run_id}`,
                  label: run.name,
                  points: run.points,
                  unit: series.unit,
                }))}
                axis={series.axis}
                smoothing="none"
                smoothingWindow={5}
                logScale={false}
                showRaw={false}
                group="workspace-comparison"
                downsampled={series.runs.some((run) => run.downsampled)}
                emptyMessage="所选运行在该横轴上没有共同记录。"
              />
            ))}
          </div>
          <Panel title="最佳与最终值">
            <BestLastTable series={compareState.data.series} runs={compareState.data.runs} />
          </Panel>
          <Panel title="超参数与运行字段差异">
            <HyperparameterDiffTable
              rows={compareState.data.hyperparameters.rows}
              runs={compareState.data.runs}
            />
            <RunFieldsTable fields={compareState.data.run_fields} runs={compareState.data.runs} />
          </Panel>
        </>
      ) : null}
    </>
  );
}

function recommendedCompareKeys(keys: MetricKey[], preferredKey?: string | null): string[] {
  const preferred = preferredKey ? keys.find((key) => key.key === preferredKey) : undefined;
  const lossKeys = keys
    .filter((key) => key.metric_name.toLowerCase().includes("loss") && key.phase === "train")
    .slice(0, 1)
    .map((key) => key.key);
  const validation = preferred &&
    ["val", "valid", "validation", "test", "eval"].includes(preferred.phase.toLowerCase()) &&
    preferred.direction === "max" &&
    !preferred.metric_name.toLowerCase().includes("loss")
    ? preferred
    : keys
        .filter(
          (key) =>
            ["val", "valid", "validation", "test", "eval"].includes(key.phase.toLowerCase()) &&
            key.direction === "max" &&
            !key.metric_name.toLowerCase().includes("loss"),
        )
        .sort((left, right) => {
          const order = ["miou", "accuracy", "acc", "f1", "dice", "precision", "recall", "auc"];
          const index = (key: MetricKey) =>
            order.findIndex((token) => key.metric_name.toLowerCase().includes(token));
          const leftIndex = index(left);
          const rightIndex = index(right);
          return (leftIndex < 0 ? 99 : leftIndex) - (rightIndex < 0 ? 99 : rightIndex);
        })[0];
  return [...new Set([...lossKeys, ...(validation ? [validation.key] : [])])].slice(0, 2);
}

function maxEpoch(keys: MetricKey[]): number {
  return keys.reduce((maximum, key) => Math.max(maximum, key.last?.epoch ?? 0), 0);
}
