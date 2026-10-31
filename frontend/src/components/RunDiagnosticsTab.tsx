import type { RunDetail } from "../types";
import { directionLabel, formatNumber } from "../utils/format";
import { EmptyState, Panel, WarningList } from "./Common";

export function RunDiagnosticsTab({ run }: { run: RunDetail }) {
  const metricGaps = run.metric_keys.filter(
    (metric) => !metric.direction || metric.direction === "none",
  );
  const hasProblems =
    run.issues.length > 0 ||
    run.step_warnings.length > 0 ||
    run.counts.missing_artifact_count > 0 ||
    !run.directory_available ||
    run.conflict !== null;

  return (
    <div className="diagnostics-tab">
      <Panel title="运行状态">
        <p>
          <strong>{run.status_label}</strong>：{run.status_reason}
        </p>
        <p className="muted small">
          状态由 events.jsonl 的生命周期事件和心跳推导。没有完成事件且长时间没有心跳时，查看器只显示“状态未知（可能中断）”，
          不会把日志停止误判为训练失败。
        </p>
        <div className="diagnostic-counts">
          <span>已索引指标点：{formatNumber(run.counts.metric_point_count, 0)}</span>
          <span>产物引用：{formatNumber(run.counts.artifact_count, 0)}</span>
          <span>缺失产物：{formatNumber(run.counts.missing_artifact_count, 0)}</span>
          <span>事件：{formatNumber(run.counts.event_count, 0)}</span>
          <span>解析问题：{formatNumber(run.counts.issue_count, 0)}</span>
        </div>
      </Panel>

      <Panel title="查看器警告">
        {run.warnings.length === 0 ? (
          <p className="notice">没有发现结构性问题。</p>
        ) : (
          <WarningList warnings={run.warnings} />
        )}
        {run.step_warnings.length > 0 ? (
          <div>
            <h3>Step 回退</h3>
            <ul>
              {run.step_warnings.map((warning, index) => (
                <li key={index}>{warning.message}</li>
              ))}
            </ul>
            <p className="muted small">
              同一会话内的 Step 回退会中断曲线连接；恢复训练产生新会话时，Step 从 0 开始属于正常情况。
            </p>
          </div>
        ) : null}
      </Panel>

      <Panel title="日志解析问题">
        {run.issues.length === 0 ? (
          <p className="notice">没有解析错误或校验问题。</p>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">文件</th>
                  <th scope="col">行号</th>
                  <th scope="col">级别</th>
                  <th scope="col">问题</th>
                  <th scope="col">发现时间</th>
                </tr>
              </thead>
              <tbody>
                {run.issues.map((issue, index) => (
                  <tr key={`${issue.file_path}-${issue.line_number}-${index}`}>
                    <td className="mono" title={issue.file_path}>
                      {issue.file_path.split(/[\\/]/).pop()}
                    </td>
                    <td>{issue.line_number || "—"}</td>
                    <td>{issue.severity === "error" ? "错误" : "警告"}</td>
                    <td>{issue.message}</td>
                    <td>{issue.created_at ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="muted small">
          无效行会被隔离并记录行号；文件末尾只写了一半的行会等待补齐，不会提前丢弃。
        </p>
      </Panel>

      <Panel title="指标定义完整性">
        {metricGaps.length === 0 ? (
          <p className="notice">所有已记录指标都有明确方向。</p>
        ) : (
          <>
            <p>
              以下指标缺少 min/max 方向或单位定义，可以绘制，但不能用于自动评优或直接比较：
            </p>
            <ul>
              {metricGaps.map((metric) => (
                <li key={metric.key}>
                  <code>{metric.key}</code>：方向 {directionLabel(metric.direction)}，单位{" "}
                  {metric.unit ?? "未声明"}
                </li>
              ))}
            </ul>
          </>
        )}
      </Panel>

      <Panel title="日志文件游标">
        {run.data_sources.length === 0 ? (
          <EmptyState title="没有已索引的日志文件" />
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">文件</th>
                  <th scope="col">类型</th>
                  <th scope="col">已读取位置</th>
                  <th scope="col">文件大小</th>
                  <th scope="col">最后读取</th>
                  <th scope="col">健康状态</th>
                </tr>
              </thead>
              <tbody>
                {run.data_sources.map((source) => (
                  <tr key={source.file_path}>
                    <td className="mono" title={source.file_path}>
                      {source.relative_path}
                    </td>
                    <td>{source.file_kind}</td>
                    <td>{formatNumber(source.offset, 0)}</td>
                    <td>{formatNumber(source.size, 0)}</td>
                    <td>{source.updated_at}</td>
                    <td>{source.health}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="muted small">
          游标按文件身份、大小和修改时间维护。文件被截断或替换时，查看器会删除该文件的索引并重新导入，原始文件保持不变。
        </p>
      </Panel>

      {!hasProblems ? (
        <p className="notice">该运行当前没有需要处理的诊断问题。</p>
      ) : null}
    </div>
  );
}
