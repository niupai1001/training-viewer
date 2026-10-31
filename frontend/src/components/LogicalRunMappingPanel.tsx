import { useState } from "react";
import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { useLiveVersion } from "../live/LiveUpdates";
import { ErrorBlock, LoadingBlock, Panel } from "./Common";

/** 用户确认的文件 → 逻辑实验归并；规则保存在 Viewer 数据目录，不碰原始日志。 */
export function LogicalRunMappingPanel() {
  const liveVersion = useLiveVersion();
  const sources = useApi(() => api.sourceInventory(), [liveVersion]);
  const overrides = useApi(() => api.logicalOverrides(), [liveVersion]);
  const [selectedFiles, setSelectedFiles] = useState<string[]>([]);
  const [logicalRunId, setLogicalRunId] = useState("");
  const [name, setName] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function toggle(path: string) {
    setSelectedFiles((current) =>
      current.includes(path) ? current.filter((item) => item !== path) : [...current, path],
    );
  }

  async function save() {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const id = logicalRunId.trim() || `logical-${Date.now()}`;
      await api.saveLogicalOverride({
        logical_run_id: id,
        name: name.trim() || id,
        files: selectedFiles,
        reason: "用户在来源清单中确认",
      });
      setMessage(`已建立逻辑实验 ${id}；原始文件未修改。`);
      setSelectedFiles([]);
      setLogicalRunId("");
      setName("");
      sources.reload();
      overrides.reload();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  const candidates = (sources.data?.sources ?? []).filter(
    (row) => row.source_path && !row.merged && row.confidence !== "canonical",
  );
  return (
    <Panel title="来源映射与逻辑实验">
      <p className="muted small">
        默认每个来源文件独立；只有你在这里确认后，同一目录的文件才会归并成一个逻辑实验。
        规则保存在 Viewer 数据目录，删除索引不会删除它。
      </p>
      {sources.loading ? <LoadingBlock label="正在读取来源…" /> : null}
      {sources.error ? <ErrorBlock error={sources.error} onRetry={sources.reload} /> : null}
      <div className="mapping-list">
        {candidates.map((row) => (
          <label key={row.source_path ?? row.run_id} className="mapping-row">
            <input
              type="checkbox"
              checked={selectedFiles.includes(row.source_path ?? "")}
              disabled={!row.source_path}
              onChange={() => row.source_path && toggle(row.source_path)}
            />
            <span className="mono small">{row.source_path}</span>
            <span className="muted small">
              {row.parser} · {row.point_count} 点
            </span>
          </label>
        ))}
        {candidates.length === 0 && !sources.loading ? (
          <p className="muted">没有可归并的独立来源文件。</p>
        ) : null}
      </div>
      <div className="mapping-form">
        <label>
          逻辑实验 ID
          <input
            value={logicalRunId}
            placeholder="例如 logical-segformer-20261031"
            onChange={(event) => setLogicalRunId(event.target.value)}
          />
        </label>
        <label>
          显示名
          <input value={name} onChange={(event) => setName(event.target.value)} />
        </label>
        <button
          type="button"
          className="button button-primary"
          disabled={busy || selectedFiles.length === 0}
          onClick={save}
        >
          {busy ? "保存中…" : "确认归并选中文件"}
        </button>
      </div>
      {message ? <p className="notice">{message}</p> : null}
      {error ? <p className="notice notice-error">{error}</p> : null}
      <h3 className="mapping-heading">已保存的归并规则</h3>
      {overrides.data?.overrides.length === 0 ? (
        <p className="muted small">还没有归并规则。</p>
      ) : null}
      <ul className="saved-view-list">
        {overrides.data?.overrides.map((override) => (
          <li key={override.logical_run_id}>
            <div>
              <strong>{override.name}</strong>
              <div className="muted small">
                {override.logical_run_id} · {override.files.length} 个文件
              </div>
            </div>
            <button
              type="button"
              className="button button-small button-danger"
              onClick={async () => {
                if (!window.confirm(`撤销逻辑实验“${override.name}”的归并？`)) {
                  return;
                }
                await api.deleteLogicalOverride(override.logical_run_id);
                sources.reload();
                overrides.reload();
              }}
            >
              撤销
            </button>
          </li>
        ))}
      </ul>
    </Panel>
  );
}
