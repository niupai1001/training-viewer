import { useMemo, useState } from "react";
import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { useLiveVersion } from "../live/LiveUpdates";
import type {
  Axis,
  MetricKey,
  MetricQueryResult,
  RunDetail,
  RunSummary,
} from "../types";
import {
  axisShortLabel,
  formatDateTime,
  formatMetricValue,
  formatRelativeTime,
  unitLabel,
} from "../utils/format";
import {
  EmptyState,
  ErrorBlock,
  LoadingBlock,
  PageHeader,
  Panel,
  StatusBadge,
} from "../components/Common";
import { MetricChart } from "../components/MetricChart";
import { RootDirectoriesPanel } from "../components/RootDirectoriesPanel";
import { LatestArtifactPreview } from "../components/LatestArtifactPreview";

export function OverviewPage() {
  const liveVersion = useLiveVersion();
  const runsState = useApi(() => api.runs({ limit: 50, sort: "-last_updated_at" }), [liveVersion]);
  const rootsState = useApi(() => api.roots(), [liveVersion]);
  const diagnostics = useApi(() => api.diagnostics(), [liveVersion]);
  const savedViews = useApi(() => api.savedViews(), [liveVersion]);
  const [showRootForm, setShowRootForm] = useState(false);

  const runs = runsState.data?.runs ?? [];
  const featured = useMemo(
    () =>
      runs.find((run) => run.activity === "updating" || run.status === "running") ??
      runs[0] ??
      null,
    [runs],
  );
  const detailState = useApi(
    () => (featured ? api.run(featured.run_id) : Promise.resolve(null)),
    [featured?.run_id, liveVersion],
  );
  const detail = detailState.data ?? null;
  const recommendations = useMemo(
    () => buildOverviewRecommendations(detail?.metric_keys ?? []),
    [detail?.metric_keys],
  );
  const lossKeys = recommendations.lossKeys;
  const metricKey = recommendations.metricKey;
  const lossAxis = chooseAxis(detail?.metric_keys ?? [], lossKeys);
  const metricAxis = metricKey ? chooseAxis(detail?.metric_keys ?? [], [metricKey.key]) : "global_step";
  const lossState = useApi<MetricQueryResult | null>(
    () =>
      featured && lossKeys.length > 0
        ? api.metrics(featured.run_id, lossKeys, lossAxis, 1500)
        : Promise.resolve(null),
    [featured?.run_id, lossKeys.join("|"), lossAxis, liveVersion],
  );
  const metricState = useApi<MetricQueryResult | null>(
    () =>
      featured && metricKey
        ? api.metrics(featured.run_id, [metricKey.key], metricAxis, 1500)
        : Promise.resolve(null),
    [featured?.run_id, metricKey?.key, metricAxis, liveVersion],
  );

  const roots = rootsState.data?.roots ?? [];
  const hasRuns = runs.length > 0;
  const lastEpoch = detail ? maxEpoch(detail.metric_keys) : 0;
  const configuredEpochs = detail ? configuredEpochCount(detail) : null;
  const keyMetric = metricKey ?? detail?.metric_keys[0] ?? null;
  const learningRate = detail?.metric_keys.find((metric) =>
    ["lr", "learning_rate"].includes(metric.metric_name.toLowerCase()),
  );

  if (runsState.loading && roots.length === 0) {
    return (
      <div className="page">
        <PageHeader title="监控" subtitle="正在读取最近的训练记录…" />
        <LoadingBlock />
      </div>
    );
  }

  return (
    <div className="page monitor-page">
      <PageHeader
        title="监控"
        subtitle="打开后先看到最近训练的真实曲线；目录、诊断与协议细节在高级设置中。"
        actions={
          <>
            <button
              type="button"
              className="button button-primary"
              onClick={() => {
                setShowRootForm(true);
                window.scrollTo({ top: 0, behavior: "smooth" });
              }}
            >
              打开训练目录
            </button>
            {featured ? (
              <a className="button" href={`#/runs/${encodeURIComponent(featured.run_id)}`}>
                打开运行详情
              </a>
            ) : null}
          </>
        }
      />

      {runsState.error ? <ErrorBlock error={runsState.error} onRetry={runsState.reload} /> : null}
      {!hasRuns ? (
        <>
          <Panel title="打开训练目录">
            <RootDirectoriesPanel />
          </Panel>
          {roots.length > 0 ? (
            <EmptyState
              title="目录已添加，但还没有识别到训练记录"
              description="支持 run.json、TensorBoard 事件文件、任意文件名的 CSV/TSV/JSONL、普通 train.log/train.txt。新增指标后会自动出现。"
            />
          ) : null}
        </>
      ) : null}

      {hasRuns && featured ? (
        <>
          <section className="monitor-hero">
            <div className="monitor-hero-main">
              <div className="monitor-eyebrow">当前/最近训练</div>
              <div className="monitor-title-row">
                <h1>
                  <a href={`#/runs/${encodeURIComponent(featured.run_id)}`}>{featured.name}</a>
                </h1>
                <StatusBadge
                  status={featured.status}
                  label={featured.status_label}
                  reason={featured.status_reason}
                />
                <span className={`activity-badge activity-${featured.activity}`} title={featured.status_reason}>
                  {featured.activity_label}
                </span>
              </div>
              <div className="monitor-meta">
                <span>
                  {featured.project}
                  {featured.experiment ? ` / ${featured.experiment}` : ""}
                </span>
                <span>最近更新 {formatRelativeTime(featured.last_metric_at ?? featured.last_updated_at)}</span>
                <span>
                  {lastEpoch > 0 ? `已训练 ${lastEpoch} 个训练轮次` : "尚无训练轮次"}
                  {configuredEpochs ? ` / 计划 ${configuredEpochs}` : ""}
                </span>
              </div>
              {featured.status_reason ? (
                <p className="monitor-status-reason">{featured.status_reason}</p>
              ) : null}
            </div>
            <div className="monitor-hero-actions">
              <a className="button button-primary" href={`#/runs/${encodeURIComponent(featured.run_id)}`}>
                指标曲线与配置
              </a>
              <a
                className="button"
                href={`#/compare?runs=${encodeURIComponent(featured.run_id)}${
                  keyMetric ? `&series=${encodeURIComponent(keyMetric.key)}` : ""
                }`}
              >
                与其它运行对比
              </a>
            </div>
          </section>

          <div className="monitor-kpis">
            <KpiCard
              label="最佳验证指标"
              value={
                keyMetric
                  ? `${formatMetricValue(keyMetric.best?.value, keyMetric.unit)}`
                  : "—"
              }
              hint={keyMetric ? `${keyMetric.key} · ${keyMetric.direction === "max" ? "越高越好" : "越低越好"}` : "尚未记录"}
            />
            <KpiCard
              label="最新验证指标"
              value={
                keyMetric
                  ? `${formatMetricValue(keyMetric.last?.value, keyMetric.unit)}`
                  : "—"
              }
              hint={keyMetric?.last?.epoch ? `Epoch ${keyMetric.last.epoch}` : "最新记录"}
            />
            <KpiCard
              label="学习率"
              value={learningRate ? formatMetricValue(learningRate.last?.value, learningRate.unit) : "—"}
              hint={learningRate ? "最近记录的优化器学习率" : "日志未记录学习率"}
            />
            <KpiCard
              label="日志活动"
              value={featured.activity_label}
              hint={`最后指标 ${formatDateTime(featured.last_metric_at)}`}
            />
          </div>

          <div className="monitor-charts">
            <Panel title="训练与验证损失">
              {lossKeys.length === 0 ? (
                <EmptyState title="日志中没有损失指标" description="有其它指标时会显示在右侧。" />
              ) : lossState.loading ? (
                <LoadingBlock label="正在读取损失曲线…" />
              ) : lossState.error ? (
                <ErrorBlock error={lossState.error} onRetry={lossState.reload} />
              ) : (
                <MetricChart
                  title="Loss"
                  subtitle={`横轴自动选择：${axisShortLabel(lossAxis)}`}
                  lines={(lossState.data?.series ?? []).map((series) => ({
                    id: series.key,
                    label: series.key,
                    points: series.points,
                    unit: series.unit,
                  }))}
                  axis={lossAxis}
                  smoothing="none"
                  smoothingWindow={5}
                  logScale={false}
                  showRaw={false}
                  height={330}
                  downsampled={(lossState.data?.series ?? []).some((series) => series.downsampled)}
                  emptyMessage="当前损失指标没有可绘制的数据点；请检查日志是否只记录了其它字段。"
                />
              )}
            </Panel>

            <Panel title={metricKey ? metricKey.key : "验证指标"}>
              {!metricKey ? (
                <EmptyState
                  title="还没有验证指标"
                  description="查看器只显示日志中真实记录的指标，不会凭空补出 mIoU 或 F1。"
                />
              ) : metricState.loading ? (
                <LoadingBlock label="正在读取验证指标…" />
              ) : metricState.error ? (
                <ErrorBlock error={metricState.error} onRetry={metricState.reload} />
              ) : (
                <MetricChart
                  title={metricKey.key}
                  subtitle={`单位：${unitLabel(metricKey.unit) || "未声明"} · 横轴自动选择：${axisShortLabel(metricAxis)}`}
                  lines={(metricState.data?.series ?? []).map((series) => ({
                    id: series.key,
                    label: series.key,
                    points: series.points,
                    unit: series.unit,
                  }))}
                  axis={metricAxis}
                  smoothing="none"
                  smoothingWindow={5}
                  logScale={false}
                  showRaw={false}
                  height={330}
                  downsampled={(metricState.data?.series ?? []).some((series) => series.downsampled)}
                  emptyMessage="该指标没有可绘制的数据点。"
                />
              )}
            </Panel>
          </div>

          <LatestArtifactPreview runId={featured.run_id} />

          <Panel
            title="最近实验"
            actions={<a href="#/runs">打开实验库</a>}
          >
            {runs.length === 0 ? (
              <EmptyState title="还没有其它实验" />
            ) : (
              <RecentRunsTable runs={runs.slice(0, 8)} />
            )}
          </Panel>
        </>
      ) : null}

      {showRootForm || !hasRuns ? null : (
        <p className="monitor-add-hint">
          需要查看新的训练目录？<button type="button" className="link-button" onClick={() => setShowRootForm(true)}>打开目录</button>
        </p>
      )}
      {showRootForm && hasRuns ? (
        <Panel title="添加训练目录" actions={<button type="button" className="button button-small" onClick={() => setShowRootForm(false)}>收起</button>}>
          <RootDirectoriesPanel />
        </Panel>
      ) : null}

      {hasRuns ? (
        <details className="advanced-section">
          <summary>高级设置：目录、诊断、保存的对比视图</summary>
          <Panel title="日志目录与来源">
            <RootDirectoriesPanel compact />
          </Panel>
          <Panel
            title="诊断摘要"
            actions={<a href="#/diagnostics">打开设置与诊断</a>}
          >
            {diagnostics.error ? (
              <ErrorBlock error={diagnostics.error} onRetry={diagnostics.reload} />
            ) : null}
            {diagnostics.data ? (
              <div className="diagnostic-summary">
                <div>
                  <strong>{diagnostics.data.scan_issues.length}</strong>
                  <span>目录级问题</span>
                </div>
                <div>
                  <strong>{diagnostics.data.conflicts.length}</strong>
                  <span>run_id 冲突</span>
                </div>
                <div>
                  <strong>{diagnostics.data.problem_runs.length}</strong>
                  <span>需要关注的运行</span>
                </div>
              </div>
            ) : null}
          </Panel>
          <Panel title="保存的对比视图">
            {savedViews.error ? <ErrorBlock error={savedViews.error} onRetry={savedViews.reload} /> : null}
            {savedViews.data && savedViews.data.saved_views.length === 0 ? (
              <p className="muted">在实验对比页保存后，可从这里的名称恢复完整显示设置。</p>
            ) : null}
            <ul className="saved-view-list">
              {savedViews.data?.saved_views.map((view) => (
                <li key={view.id}>
                  <div>
                    <a href={`#/compare?view=${view.id}`}>{view.name}</a>
                    <div className="muted small">
                      {view.payload.run_ids?.length ?? 0} 个运行 · {view.payload.series?.length ?? 0} 个指标 ·
                      保存于 {formatDateTime(view.created_at)}
                    </div>
                  </div>
                  <button
                    type="button"
                    className="button button-small button-danger"
                    onClick={async () => {
                      if (!window.confirm(`删除保存的视图“${view.name}”？`)) {
                        return;
                      }
                      await api.deleteSavedView(view.id);
                      savedViews.reload();
                    }}
                  >
                    删除
                  </button>
                </li>
              ))}
            </ul>
          </Panel>
        </details>
      ) : null}
    </div>
  );
}

function KpiCard({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="stat-card">
      <span className="stat-label">{label}</span>
      <strong className="stat-value stat-value-small">{value}</strong>
      <span className="stat-hint">{hint}</span>
    </div>
  );
}

function RecentRunsTable({ runs }: { runs: RunSummary[] }) {
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            <th scope="col">运行</th>
            <th scope="col">状态</th>
            <th scope="col">关键指标</th>
            <th scope="col">最近更新</th>
            <th scope="col">操作</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.run_id}>
              <td>
                <a href={`#/runs/${encodeURIComponent(run.run_id)}`}>{run.name}</a>
                <div className="muted small">{run.tags.join(" · ")}</div>
              </td>
              <td>
                <StatusBadge status={run.status} label={run.status_label} reason={run.status_reason} />
                <span className={`activity-badge activity-${run.activity}`}>{run.activity_label}</span>
              </td>
              <td>
                {run.primary_metric ? (
                  <span title={run.primary_metric.definition ?? ""}>
                    {run.primary_metric.key}
                    <div className="muted small">
                      最佳 {formatMetricValue(run.primary_metric.best?.value, run.primary_metric.unit)}
                    </div>
                  </span>
                ) : (
                  <span className="muted">—</span>
                )}
              </td>
              <td title={formatDateTime(run.last_updated_at)}>{formatRelativeTime(run.last_updated_at)}</td>
              <td>
                <a
                  className="button button-small"
                  href={`#/compare?runs=${encodeURIComponent(run.run_id)}`}
                >
                  对比
                </a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function buildOverviewRecommendations(keys: MetricKey[]): {
  lossKeys: string[];
  metricKey: MetricKey | null;
} {
  const lower = (key: MetricKey) => key.metric_name.toLowerCase();
  const isValidation = (key: MetricKey) =>
    ["val", "valid", "validation", "test", "eval"].includes(key.phase.toLowerCase());
  const lossKeys = keys
    .filter((key) => lower(key).includes("loss"))
    .sort((left, right) => {
      const leftWeight = isValidation(left) ? (left.phase.toLowerCase() === "train" ? 0 : 1) : 0;
      const rightWeight = isValidation(right) ? (right.phase.toLowerCase() === "train" ? 0 : 1) : 0;
      return leftWeight - rightWeight;
    })
    .slice(0, 2)
    .map((key) => key.key);
  const priority = ["miou", "accuracy", "acc", "f1", "dice", "precision", "recall", "auc"];
  const metricKey =
    keys
      .filter((key) => isValidation(key) && key.direction === "max" && !lower(key).includes("loss"))
      .sort((left, right) => {
        const leftIndex = priority.findIndex((name) => lower(left).includes(name));
        const rightIndex = priority.findIndex((name) => lower(right).includes(name));
        return (leftIndex < 0 ? 99 : leftIndex) - (rightIndex < 0 ? 99 : rightIndex);
      })[0] ??
    keys.find((key) => key.direction === "max" && !lower(key).includes("loss")) ??
    keys.find((key) => !lower(key).includes("loss")) ??
    keys[0] ??
    null;
  return { lossKeys, metricKey };
}

function chooseAxis(keys: MetricKey[], selectedKeys: string[]): Axis {
  const selected = keys.filter((key) => selectedKeys.includes(key.key));
  if (selected.length === 0) {
    return "global_step";
  }
  if (selected.every((key) => key.step_point_count > 0)) {
    return "global_step";
  }
  if (selected.every((key) => key.epoch_point_count > 0)) {
    return "epoch";
  }
  if (selected.some((key) => key.step_point_count > 0)) {
    return "global_step";
  }
  if (selected.some((key) => key.epoch_point_count > 0)) {
    return "epoch";
  }
  return "global_step";
}

function maxEpoch(keys: MetricKey[]): number {
  return keys.reduce((maximum, key) => Math.max(maximum, key.last?.epoch ?? 0), 0);
}

function configuredEpochCount(detail: RunDetail): number | null {
  const value = (detail.config as Record<string, unknown>).epochs;
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
