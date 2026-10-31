import { useState } from "react";
import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { useLiveVersion } from "../live/LiveUpdates";
import type { RunSummary } from "../types";
import {
  formatDateTime,
  formatMetricValue,
  formatNumber,
  formatRelativeTime,
  statusLabel,
} from "../utils/format";
import {
  EmptyState,
  ErrorBlock,
  LoadingBlock,
  PageHeader,
  Panel,
  StatusBadge,
  WarningList,
} from "../components/Common";

export function OverviewPage() {
  const liveVersion = useLiveVersion();
  const projects = useApi(() => api.projects(), [liveVersion]);
  const recentRuns = useApi(() => api.runs({ limit: 8, sort: "-last_updated_at" }), [liveVersion]);
  const runningRuns = useApi(() => api.runs({ status: "running", limit: 6 }), [liveVersion]);
  const diagnostics = useApi(() => api.diagnostics(), [liveVersion]);
  const savedViews = useApi(() => api.savedViews(), [liveVersion]);

  const [rootPath, setRootPath] = useState("");
  const [rootMessage, setRootMessage] = useState<string | null>(null);
  const [rootError, setRootError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const roots = projects.data?.roots ?? [];
  const projectNodes = projects.data?.projects ?? [];
  const totalRuns = recentRuns.data?.total ?? diagnostics.data?.totals.run_count ?? 0;
  const runningCount = projectNodes.reduce((sum, project) => sum + project.running_count, 0);
  const unknownCount = diagnostics.data?.totals.unknown_count ?? 0;
  const scanIssueCount = diagnostics.data?.scan_issues.length ?? 0;
  const conflictCount = diagnostics.data?.conflicts.length ?? 0;

  function refreshAll() {
    projects.reload();
    recentRuns.reload();
    runningRuns.reload();
    diagnostics.reload();
    savedViews.reload();
  }

  async function handleAddRoot(event: React.FormEvent) {
    event.preventDefault();
    setRootError(null);
    setRootMessage(null);
    if (!rootPath.trim()) {
      return;
    }
    setBusy(true);
    try {
      await api.addRoot(rootPath.trim());
      setRootMessage(`已添加目录：${rootPath.trim()}，正在扫描。`);
      setRootPath("");
      refreshAll();
    } catch (error) {
      setRootError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  async function handleRemoveRoot(rootId: number, path: string) {
    if (!window.confirm(`移除扫描目录“${path}”？只会删除索引，磁盘上的原始日志不会被删除。`)) {
      return;
    }
    setBusy(true);
    setRootError(null);
    try {
      await api.removeRoot(rootId);
      setRootMessage(`已移除目录：${path}`);
      refreshAll();
    } catch (error) {
      setRootError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  async function handleRescan() {
    setBusy(true);
    setRootError(null);
    try {
      const result = await api.rescan();
      setRootMessage(`扫描完成：当前版本 ${result.version}，发现 ${result.run_count} 个运行。`);
      refreshAll();
    } catch (error) {
      setRootError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <PageHeader
        title="总览"
        subtitle="本机训练实验的实时状态、最近运行与数据来源。查看器只读取日志文件，不会修改训练目录。"
        actions={
          <button type="button" className="button" onClick={handleRescan} disabled={busy}>
            立即重新扫描
          </button>
        }
      />

      <div className="stat-grid">
        <StatCard label="运行总数" value={formatNumber(totalRuns, 0)} hint="已导入索引的训练/评估运行数量" />
        <StatCard label="运行中" value={formatNumber(runningCount, 0)} hint="最近 120 秒内收到心跳或新指标的运行" />
        <StatCard label="项目" value={formatNumber(projectNodes.length, 0)} hint="按 run.json 的 project 字段分组" />
        <StatCard
          label="状态未知"
          value={formatNumber(unknownCount, 0)}
          hint="没有完成事件且心跳超时的运行；日志停止不能证明训练失败"
          tone="warning"
        />
      </div>

      <div className="overview-grid">
        <Panel
          title="日志来源目录"
          actions={
            <span className="muted small">
              {roots.length} 个根目录 · {scanIssueCount} 条目录级问题
            </span>
          }
        >
          <form className="root-form" onSubmit={handleAddRoot}>
            <input
              type="text"
              value={rootPath}
              placeholder="输入本机训练日志根目录，例如 D:\\experiments"
              aria-label="要添加的训练日志根目录"
              onChange={(event) => setRootPath(event.target.value)}
            />
            <button type="submit" className="button" disabled={busy || !rootPath.trim()}>
              添加目录
            </button>
          </form>
          <p className="muted small">
            只扫描你显式添加的目录。也可以在终端运行 <code>training-viewer open &lt;目录&gt;</code>，
            或用 VS Code 命令“Training Viewer: Add Folder”。目录中的原始日志始终只读。
          </p>
          {rootMessage ? <p className="notice">{rootMessage}</p> : null}
          {rootError ? <p className="notice notice-error">{rootError}</p> : null}
          {roots.length === 0 ? (
            <EmptyState
              title="还没有日志目录"
              description="添加一个包含 run.json 或 TensorBoard/CSV 日志的目录。也可以先在终端执行 training-viewer open <目录>。"
            />
          ) : (
            <ul className="root-list">
              {roots.map((root) => (
                <li key={root.id}>
                  <code title={root.path}>{root.path}</code>
                  <span className="muted small">添加于 {formatDateTime(root.added_at)}</span>
                  <button
                    type="button"
                    className="button button-small button-danger"
                    disabled={busy}
                    onClick={() => handleRemoveRoot(root.id, root.path)}
                  >
                    移除
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title="运行中的实验" actions={<a href="#/runs?status=running">查看全部</a>}>
          {runningRuns.loading ? <LoadingBlock label="正在检查运行状态…" /> : null}
          {runningRuns.error ? <ErrorBlock error={runningRuns.error} onRetry={runningRuns.reload} /> : null}
          {runningRuns.data && runningRuns.data.runs.length === 0 ? (
            <EmptyState title="当前没有运行中的实验" description="训练启动并写入新指标后，这里会自动出现。" />
          ) : null}
          <ul className="running-list">
            {runningRuns.data?.runs.map((run) => (
              <li key={run.run_id}>
                <div>
                  <a href={`#/runs/${encodeURIComponent(run.run_id)}`}>{run.name}</a>
                  <div className="muted small">
                    {run.project}
                    {run.experiment ? ` / ${run.experiment}` : ""} · 更新于 {formatRelativeTime(run.last_updated_at)}
                  </div>
                </div>
                <StatusBadge status={run.status} label={run.status_label} reason={run.status_reason} />
              </li>
            ))}
          </ul>
        </Panel>
      </div>

      <Panel
        title="最近实验"
        actions={<a href="#/runs">查看所有实验</a>}
      >
        {recentRuns.loading ? <LoadingBlock /> : null}
        {recentRuns.error ? <ErrorBlock error={recentRuns.error} onRetry={recentRuns.reload} /> : null}
        {recentRuns.data && recentRuns.data.runs.length === 0 ? (
          <EmptyState title="还没有实验记录" description="添加日志目录后，符合 TVLP 1.0 或可适配格式的运行会自动出现在这里。" />
        ) : null}
        {recentRuns.data && recentRuns.data.runs.length > 0 ? (
          <RecentRunsTable runs={recentRuns.data.runs} />
        ) : null}
      </Panel>

      <div className="overview-grid">
        <Panel
          title="诊断摘要"
          actions={<a href="#/diagnostics">打开诊断页</a>}
        >
          {diagnostics.error ? <ErrorBlock error={diagnostics.error} onRetry={diagnostics.reload} /> : null}
          {diagnostics.data ? (
            <div className="diagnostic-summary">
              <div>
                <strong>{scanIssueCount}</strong>
                <span>目录级问题</span>
              </div>
              <div>
                <strong>{conflictCount}</strong>
                <span>run_id 冲突</span>
              </div>
              <div>
                <strong>{diagnostics.data.problem_runs.length}</strong>
                <span>需要关注的运行</span>
              </div>
            </div>
          ) : null}
          <p className="muted small">
            状态未知不等于训练失败：没有完成事件且超过 120 秒没有心跳或新指标时，查看器会保持“状态未知（可能中断）”。
          </p>
        </Panel>

        <Panel title="保存的对比视图">
          {savedViews.error ? <ErrorBlock error={savedViews.error} onRetry={savedViews.reload} /> : null}
          {savedViews.data && savedViews.data.saved_views.length === 0 ? (
            <EmptyState
              title="还没有保存的对比视图"
              description="在“实验对比”页选择运行与指标后，可以保存视图，之后从总览恢复同一组比较。"
            />
          ) : null}
          <ul className="saved-view-list">
            {savedViews.data?.saved_views.map((view) => {
              const params = new URLSearchParams();
              if (view.payload.run_ids?.length) {
                params.set("runs", view.payload.run_ids.join(","));
              }
              if (view.payload.series?.length) {
                params.set("series", view.payload.series.join(","));
              }
              if (view.payload.axis) {
                params.set("axis", view.payload.axis);
              }
              return (
                <li key={view.id}>
                  <div>
                    <a href={`#/compare?${params.toString()}`}>{view.name}</a>
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
              );
            })}
          </ul>
        </Panel>
      </div>

      {projects.error ? <ErrorBlock error={projects.error} onRetry={projects.reload} /> : null}
    </div>
  );
}

function StatCard({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: string;
  hint: string;
  tone?: "warning";
}) {
  return (
    <div className={`stat-card ${tone ? `stat-${tone}` : ""}`} title={hint}>
      <span className="stat-label">{label}</span>
      <strong className="stat-value">{value}</strong>
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
            <th scope="col">项目 / 实验组</th>
            <th scope="col">主要指标</th>
            <th scope="col">最近更新</th>
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
              </td>
              <td>
                {run.project}
                {run.experiment ? <div className="muted small">{run.experiment}</div> : null}
              </td>
              <td>
                {run.primary_metric ? (
                  <span title={run.primary_metric.definition ?? ""}>
                    {run.primary_metric.key}
                    <div className="muted small">
                      最佳 {formatMetricValue(run.primary_metric.best?.value, run.primary_metric.unit)} · 最终{" "}
                      {formatMetricValue(run.primary_metric.last?.value, run.primary_metric.unit)}
                    </div>
                  </span>
                ) : (
                  <span className="muted">尚无指标</span>
                )}
              </td>
              <td title={formatDateTime(run.last_updated_at)}>{formatRelativeTime(run.last_updated_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
