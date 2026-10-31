import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { useLiveVersion } from "../live/LiveUpdates";
import { ErrorBlock, LoadingBlock, Panel } from "./Common";

/** 来源清单：原始文件 → 逻辑实验，供审计与高级分析使用。 */
export function SourceInventoryPanel() {
  const liveVersion = useLiveVersion();
  const state = useApi(() => api.sourceInventory(), [liveVersion]);
  if (state.loading && !state.data) {
    return <LoadingBlock label="正在读取来源清单…" />;
  }
  if (state.error) {
    return <ErrorBlock error={state.error} onRetry={state.reload} />;
  }
  const rows = state.data?.sources ?? [];
  const logical = new Set(rows.map((row) => row.logical_run_id));
  return (
    <Panel title="来源清单与逻辑实验">
      <p className="muted small">
        {rows.length} 个原始来源文件 · {logical.size} 个逻辑实验。归并只来自用户确认的侧车规则，
        不会修改原始日志；推断标签在未确认前不能作为结论。
      </p>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>来源文件</th>
              <th>解析器</th>
              <th>逻辑实验</th>
              <th>归并</th>
              <th>置信度</th>
              <th>点数</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`${row.logical_run_id}-${row.source_path ?? index}`}>
                <td className="mono small" title={row.source_path ?? ""}>
                  {row.source_path ?? "（尚无游标）"}
                </td>
                <td>{row.parser}</td>
                <td>
                  <div>{row.name}</div>
                  <div className="muted small mono">{row.logical_run_id}</div>
                </td>
                <td>{row.merged ? "是" : "否"}</td>
                <td>{row.confidence}</td>
                <td>{row.point_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length === 0 ? <p className="muted">尚无来源记录；添加日志目录后出现。</p> : null}
    </Panel>
  );
}
