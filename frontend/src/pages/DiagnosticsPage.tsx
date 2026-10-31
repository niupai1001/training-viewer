import { useState } from "react";
import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { useLiveVersion } from "../live/LiveUpdates";
import type { Severity } from "../types";
import { formatNumber, statusLabel } from "../utils/format";
import { RootDirectoriesPanel } from "../components/RootDirectoriesPanel";
import {
  EmptyState,
  ErrorBlock,
  LoadingBlock,
  PageHeader,
  Panel,
  StatusBadge,
} from "../components/Common";

const SEVERITY_LABELS: Record<Severity, string> = {
  info: "提示",
  warning: "警告",
  error: "错误",
};

export function DiagnosticsPage() {
  const liveVersion = useLiveVersion();
  const diagnostics = useApi(() => api.diagnostics(), [liveVersion]);
  const meta = useApi(() => api.meta(), [liveVersion]);
  const health = useApi(() => api.health(), [liveVersion]);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleRescan() {
    setBusy(true);
    setMessage(null);
    try {
      const result = await api.rescan();
      setMessage(`扫描完成：版本 ${result.version}，发现 ${result.run_count} 个运行。`);
      diagnostics.reload();
      health.reload();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  const totals = diagnostics.data?.totals;
  const scanIssues = diagnostics.data?.scan_issues ?? [];
  const conflicts = diagnostics.data?.conflicts ?? [];
  const problemRuns = diagnostics.data?.problem_runs ?? [];
  const hasProblems = scanIssues.length > 0 || conflicts.length > 0 || problemRuns.length > 0;

  return (
    <div className="page diagnostics-page">
      <PageHeader
        title="设置与诊断"
        subtitle="管理日志目录与来源，检查日志解析、run_id 冲突与运行状态。这里不会修改原始实验数据。"
        actions={
          <button type="button" className="button" onClick={handleRescan} disabled={busy}>
            {busy ? "扫描中…" : "立即重新扫描"}
          </button>
        }
      />

      <Panel title="日志目录与来源">
        <RootDirectoriesPanel />
      </Panel>

      {message ? <p className="notice">{message}</p> : null}
      {diagnostics.error ? (
        <ErrorBlock error={diagnostics.error} onRetry={diagnostics.reload} />
      ) : null}
      {diagnostics.loading ? <LoadingBlock label="正在收集诊断信息…" /> : null}

      <div className="stat-grid">
        <div className="stat-card">
          <span className="stat-label">运行总数</span>
          <strong className="stat-value">{formatNumber(totals?.run_count ?? 0, 0)}</strong>
          <span className="stat-hint">已建立索引的运行</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">运行中</span>
          <strong className="stat-value">{formatNumber(totals?.running_count ?? 0, 0)}</strong>
          <span className="stat-hint">最近 120 秒内有心跳或新指标</span>
        </div>
        <div className="stat-card stat-warning">
          <span className="stat-label">状态未知</span>
          <strong className="stat-value">{formatNumber(totals?.unknown_count ?? 0, 0)}</strong>
          <span className="stat-hint">日志停止不能证明训练失败</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">目录级问题</span>
          <strong className="stat-value">{formatNumber(scanIssues.length, 0)}</strong>
          <span className="stat-hint">坏 run.json、缺少可选依赖等</span>
        </div>
      </div>

      <Panel title="目录扫描问题">
        {scanIssues.length === 0 ? (
          <p className="notice">没有发现目录级问题。</p>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">路径</th>
                  <th scope="col">级别</th>
                  <th scope="col">问题</th>
                  <th scope="col">发现时间</th>
                </tr>
              </thead>
              <tbody>
                {scanIssues.map((issue, index) => (
                  <tr key={`${issue.file_path}-${index}`}>
                    <td className="mono wrap-anywhere" title={issue.file_path}>
                      {issue.file_path}
                    </td>
                    <td>
                      <span className={`severity severity-${issue.severity}`}>
                        {SEVERITY_LABELS[issue.severity] ?? issue.severity}
                      </span>
                    </td>
                    <td>{issue.message}</td>
                    <td>{issue.created_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel title="run_id 冲突">
        {conflicts.length === 0 ? (
          <p className="notice">没有发现重复 run_id。</p>
        ) : (
          <>
            <p className="notice notice-warning">
              同一 run_id 出现在多个目录时，查看器保留一个目录并报警，不会静默覆盖。请修正训练程序的 run_id 生成方式，
              或手动区分这些实验。
            </p>
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th scope="col">run_id</th>
                    <th scope="col">当前显示目录</th>
                    <th scope="col">冲突目录</th>
                    <th scope="col">发现时间</th>
                  </tr>
                </thead>
                <tbody>
                  {conflicts.map((conflict) => (
                    <tr key={conflict.run_id}>
                      <td className="mono">
                        <a href={`#/runs/${encodeURIComponent(conflict.run_id)}`}>{conflict.run_id}</a>
                      </td>
                      <td className="mono wrap-anywhere">{conflict.kept_run_dir}</td>
                      <td className="mono wrap-anywhere">{conflict.conflicting_run_dir}</td>
                      <td>{conflict.detected_at}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Panel>

      <Panel title="需要关注的运行">
        {problemRuns.length === 0 ? (
          <EmptyState title="没有需要关注的运行" description="所有运行的状态和日志解析都正常。" />
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">运行</th>
                  <th scope="col">状态</th>
                  <th scope="col">状态说明</th>
                  <th scope="col">解析问题</th>
                  <th scope="col">缺失产物</th>
                </tr>
              </thead>
              <tbody>
                {problemRuns.map((run) => (
                  <tr key={run.run_id}>
                    <td>
                      <a href={`#/runs/${encodeURIComponent(run.run_id)}`}>{run.name}</a>
                    </td>
                    <td>
                      <StatusBadge status={run.status} label={statusLabel(run.status)} reason={run.status_reason} />
                    </td>
                    <td>{run.status_reason}</td>
                    <td>{run.issue_count}</td>
                    <td>{run.missing_artifact_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel title="日志来源适配器">
        <ul className="adapter-list">
          {meta.data?.adapters.map((adapter) => (
            <li key={adapter.adapter_id}>
              <div>
                <strong>{adapter.display_name}</strong>
                <div className="muted small mono">{adapter.adapter_id}</div>
              </div>
              <span className={`badge ${adapter.available ? "badge-success" : "badge-warning"}`}>
                {adapter.available ? "可用" : "未安装可选依赖"}
              </span>
            </li>
          ))}
        </ul>
        <p className="muted small">
          读取 TensorBoard 事件文件需要可选依赖 tensorboard（pip install "training-viewer[tensorboard]"）。
          CSV 与标准 TVLP 日志不需要额外依赖。
        </p>
      </Panel>

      <Panel title="同步状态">
        <dl className="detail-list">
          <dt>最后同步时间</dt>
          <dd>{health.data?.last_sync_at ?? "—"}</dd>
          <dt>当前索引版本</dt>
          <dd>{health.data?.version ?? "—"}</dd>
          <dt>应用版本</dt>
          <dd>{meta.data?.version ?? "—"}</dd>
          <dt>日志协议</dt>
          <dd>TVLP {meta.data?.tvlp_schema_version ?? "1.0"}</dd>
        </dl>
        <p className="muted small">
          后台每 2 秒轮询一次，并在 watchdog 可用时用文件事件提前唤醒。SSE 只发送轻量更新通知，前端按需重新查询。
        </p>
      </Panel>

      {!hasProblems && diagnostics.data ? (
        <p className="notice">当前没有需要处理的诊断问题。</p>
      ) : null}
    </div>
  );
}
