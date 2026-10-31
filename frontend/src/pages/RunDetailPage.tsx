import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { useLiveVersion } from "../live/LiveUpdates";
import type { RunDetail } from "../types";
import {
  formatDateTime,
  formatDuration,
  formatRelativeTime,
  shortRunId,
} from "../utils/format";
import {
  ErrorBlock,
  LoadingBlock,
  StatusBadge,
  Tabs,
  Tag,
  WarningList,
} from "../components/Common";
import { RunMetricsTab } from "../components/RunMetricsTab";
import { RunConfigTab } from "../components/RunConfigTab";
import { RunArtifactsTab } from "../components/RunArtifactsTab";
import { RunTimelineTab } from "../components/RunTimelineTab";
import { RunDiagnosticsTab } from "../components/RunDiagnosticsTab";

export function RunDetailPage({ runId }: { runId: string }) {
  const liveVersion = useLiveVersion();
  const state = useApi(() => api.run(runId), [runId, liveVersion]);
  const [activeTab, setActiveTab] = useState("metrics");

  useEffect(() => {
    setActiveTab("metrics");
  }, [runId]);

  if (state.loading && !state.data) {
    return (
      <div className="page">
        <LoadingBlock label="正在读取运行详情…" />
      </div>
    );
  }
  if (state.error) {
    return (
      <div className="page">
        <p>
          <a href="#/runs">← 返回实验列表</a>
        </p>
        <ErrorBlock error={state.error} onRetry={state.reload} />
      </div>
    );
  }
  if (!state.data) {
    return null;
  }

  const run = state.data;
  const tabs = [
    { id: "metrics", label: "指标曲线", count: run.metric_keys.length },
    { id: "config", label: "配置与来源" },
    { id: "artifacts", label: "实验产物", count: run.counts.artifact_count },
    { id: "timeline", label: "时间线", count: run.counts.event_count },
    { id: "diagnostics", label: "诊断", count: run.counts.issue_count },
  ];

  return (
    <div className="page run-detail-page">
      <div className="breadcrumbs">
        <a href="#/runs">实验管理</a>
        <span>/</span>
        <span>{run.project}</span>
        {run.experiment ? (
          <>
            <span>/</span>
            <span>{run.experiment}</span>
          </>
        ) : null}
        <span>/</span>
        <span>{run.name}</span>
      </div>

      <header className="run-header">
        <div className="run-header-main">
          <div className="run-title-row">
            <h1>{run.name}</h1>
            <StatusBadge status={run.status} label={run.status_label} reason={run.status_reason} />
            <button
              type="button"
              className={`star-button star-large ${run.favorite ? "starred" : ""}`}
              title={run.favorite ? "取消收藏" : "收藏"}
              aria-label={run.favorite ? "取消收藏" : "收藏"}
              onClick={async () => {
                await api.updateAnnotation(run.run_id, { favorite: !run.favorite });
                state.reload();
              }}
            >
              {run.favorite ? "★" : "☆"}
            </button>
          </div>
          <div className="run-subtitle">
            <span>
              {run.project}
              {run.experiment ? ` / ${run.experiment}` : ""}
            </span>
            <span>·</span>
            <span className="mono" title={run.run_id}>
              {shortRunId(run.run_id)}
            </span>
            <button
              type="button"
              className="button button-small"
              onClick={() => {
                void navigator.clipboard?.writeText(run.run_id);
              }}
            >
              复制运行 ID
            </button>
          </div>
          <div className="run-meta-row">
            <span title={run.status_reason}>状态说明：{run.status_reason}</span>
          </div>
          <div className="run-chips">
            {run.model?.name ? <Tag title="模型">{run.model.name}</Tag> : null}
            {run.model?.architecture ? <Tag title="模型架构">{run.model.architecture}</Tag> : null}
            {run.dataset?.name ? <Tag title="数据集">{run.dataset.name}</Tag> : null}
            {run.dataset?.version ? <Tag title="数据集版本">{run.dataset.version}</Tag> : null}
            {run.tags.map((tag) => (
              <Tag key={tag}>{tag}</Tag>
            ))}
            <Tag title="训练开始时间">开始 {formatDateTime(run.created_at)}</Tag>
            <Tag title="指标数据覆盖的时长">数据时长 {formatDuration(run.duration_seconds)}</Tag>
            <Tag title="日志最后更新时间">更新 {formatRelativeTime(run.last_updated_at)}</Tag>
            <Tag title="日志协议版本">TVLP {run.schema_version ?? "1.0"}</Tag>
          </div>
          {run.warnings.length > 0 ? <WarningList warnings={run.warnings} /> : null}
        </div>
        <div className="run-header-actions">
          <a className="button" href={`#/results?run=${encodeURIComponent(run.run_id)}`}>
            查看预测结果
          </a>
          <a className="button" href={`#/compare?runs=${encodeURIComponent(run.run_id)}`}>
            与其他运行对比
          </a>
          <button type="button" className="button" onClick={state.reload}>
            刷新
          </button>
        </div>
      </header>

      <NoteEditor run={run} onSaved={state.reload} />

      <Tabs tabs={tabs} active={activeTab} onChange={setActiveTab} />

      <div className="tab-content">
        {activeTab === "metrics" ? <RunMetricsTab run={run} /> : null}
        {activeTab === "config" ? <RunConfigTab run={run} /> : null}
        {activeTab === "artifacts" ? <RunArtifactsTab run={run} /> : null}
        {activeTab === "timeline" ? <RunTimelineTab run={run} /> : null}
        {activeTab === "diagnostics" ? <RunDiagnosticsTab run={run} /> : null}
      </div>
    </div>
  );
}

function NoteEditor({ run, onSaved }: { run: RunDetail; onSaved: () => void }) {
  const [note, setNote] = useState(run.note);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    setNote(run.note);
  }, [run.run_id, run.note]);

  async function saveNote() {
    setSaving(true);
    setMessage(null);
    try {
      await api.updateAnnotation(run.run_id, { note });
      setMessage("备注已保存到本地索引，不会写入训练目录。");
      onSaved();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="note-editor">
      <label htmlFor="run-note">个人备注</label>
      <textarea
        id="run-note"
        value={note}
        rows={2}
        placeholder="记录实验结论、问题或下一步计划。备注只保存在本机 SQLite 中。"
        onChange={(event) => setNote(event.target.value)}
      />
      <div className="note-actions">
        <button
          type="button"
          className="button button-small"
          disabled={saving || note === run.note}
          onClick={saveNote}
        >
          {saving ? "保存中…" : "保存备注"}
        </button>
        {message ? <span className="muted small">{message}</span> : null}
      </div>
    </section>
  );
}
