import { useState } from "react";
import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { useLiveVersion } from "../live/LiveUpdates";
import { formatDateTime } from "../utils/format";
import { EmptyState, ErrorBlock, LoadingBlock } from "./Common";

/** 日志根目录管理：文本输入、本机系统目录选择、移除与重新扫描。 */
export function RootDirectoriesPanel({ compact = false }: { compact?: boolean }) {
  const liveVersion = useLiveVersion();
  const rootsState = useApi(() => api.roots(), [liveVersion]);
  const [path, setPath] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function addRoot(target: string) {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const root = await api.addRoot(target);
      setMessage(`已添加目录：${root.path}`);
      setPath("");
      rootsState.reload();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  async function chooseDirectory() {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const selected = await api.selectRootDirectory();
      await addRoot(selected.path);
    } catch (cause) {
      setError(
        `${cause instanceof Error ? cause.message : String(cause)} ` +
          "也可以直接在输入框粘贴目录，或使用 training-viewer open <目录>。",
      );
    } finally {
      setBusy(false);
    }
  }

  async function removeRoot(rootId: number, target: string) {
    if (!window.confirm(`移除扫描目录“${target}”？只会删除索引，原始日志不会被删除。`)) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.removeRoot(rootId);
      setMessage(`已移除目录：${target}`);
      rootsState.reload();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  async function rescan() {
    setBusy(true);
    setError(null);
    try {
      const result = await api.rescan();
      setMessage(`扫描完成：发现 ${result.run_count} 个运行。`);
      rootsState.reload();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={compact ? "root-panel root-panel-compact" : "root-panel"}>
      <form
        className="root-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (path.trim()) {
            void addRoot(path.trim());
          }
        }}
      >
        <input
          type="text"
          value={path}
          placeholder="输入训练日志根目录，例如 D:\experiments"
          aria-label="训练日志根目录"
          onChange={(event) => setPath(event.target.value)}
        />
        <button type="submit" className="button" disabled={busy || !path.trim()}>
          添加目录
        </button>
        <button type="button" className="button" onClick={chooseDirectory} disabled={busy}>
          选择本机目录
        </button>
        {!compact ? (
          <button type="button" className="button" onClick={rescan} disabled={busy}>
            重新扫描
          </button>
        ) : null}
      </form>
      <p className="muted small">
        “选择本机目录”会打开本机系统目录选择框；无桌面环境时请粘贴路径、使用 CLI 或 VS Code。
        目录中的原始日志始终只读。
      </p>
      {message ? <p className="notice">{message}</p> : null}
      {error ? <p className="notice notice-error">{error}</p> : null}
      {rootsState.loading ? <LoadingBlock label="正在读取目录…" /> : null}
      {rootsState.error ? <ErrorBlock error={rootsState.error} onRetry={rootsState.reload} /> : null}
      {rootsState.data && rootsState.data.roots.length === 0 ? (
        <EmptyState
          title="还没有日志目录"
          description="添加一个包含 run.json、TensorBoard 事件文件、CSV/JSONL 或普通训练日志的目录。"
        />
      ) : null}
      <ul className="root-list">
        {rootsState.data?.roots.map((root) => (
          <li key={root.id}>
            <code title={root.path}>{root.path}</code>
            <span className="muted small">添加于 {formatDateTime(root.added_at)}</span>
            <button
              type="button"
              className="button button-small button-danger"
              disabled={busy}
              onClick={() => removeRoot(root.id, root.path)}
            >
              移除
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
