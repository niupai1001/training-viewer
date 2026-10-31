import { useState } from "react";
import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { useLiveVersion } from "../live/LiveUpdates";
import type { RunDetail } from "../types";
import { eventLabel, formatDateTime, roleLabel } from "../utils/format";
import { EmptyState, ErrorBlock, LoadingBlock, Panel } from "./Common";

export function RunTimelineTab({ run }: { run: RunDetail }) {
  const liveVersion = useLiveVersion();
  const state = useApi(
    () => api.timeline(run.run_id),
    [run.run_id, run.status === "running" ? liveVersion : 0],
  );
  const [showHeartbeats, setShowHeartbeats] = useState(false);

  if (state.loading) {
    return <LoadingBlock label="正在读取时间线…" />;
  }
  if (state.error) {
    return <ErrorBlock error={state.error} onRetry={state.reload} />;
  }

  const events = state.data?.events ?? [];
  const heartbeats = events.filter((event) => event.kind === "heartbeat");
  const visible = (showHeartbeats ? events : events.filter((event) => event.kind !== "heartbeat")).slice(
    0,
    1000,
  );

  return (
    <div className="timeline-tab">
      <Panel
        title="执行会话"
        actions={<span className="muted small">断点续训会增加新的会话，不会合并 Step 回退</span>}
      >
        {run.sessions.length === 0 ? (
          <p className="muted">还没有可识别的会话（需要指标或事件中包含 session_id）。</p>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">会话</th>
                  <th scope="col">首次记录</th>
                  <th scope="col">最后记录</th>
                  <th scope="col">指标点</th>
                  <th scope="col">事件</th>
                </tr>
              </thead>
              <tbody>
                {run.sessions.map((session, index) => (
                  <tr key={`${session.session_id}-${index}`}>
                    <th scope="row" className="mono">
                      {session.session_id ?? "未标注"}
                    </th>
                    <td>{formatDateTime(session.first_seen)}</td>
                    <td>{formatDateTime(session.last_seen)}</td>
                    <td>{session.point_count}</td>
                    <td>{session.event_count ?? 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel
        title="事件时间线"
        actions={
          <label className="inline-check">
            <input
              type="checkbox"
              checked={showHeartbeats}
              onChange={(event) => setShowHeartbeats(event.target.checked)}
            />
            显示心跳（{heartbeats.length}）
          </label>
        }
      >
        {events.length === 0 ? (
          <EmptyState
            title="没有生命周期或心跳事件"
            description="训练程序可以在 events.jsonl 中记录 lifecycle、heartbeat 与 artifact 事件。没有完成事件时，状态会显示为未知，而不是失败。"
          />
        ) : (
          <ol className="timeline">
            {visible.map((event, index) => (
              <li
                key={`${event.kind}-${event.timestamp}-${index}`}
                className={`timeline-item timeline-${event.kind} ${
                  event.status ? `timeline-status-${event.status}` : ""
                }`}
              >
                <span className="timeline-dot" aria-hidden="true" />
                <div className="timeline-content">
                  <div className="timeline-heading">
                    <strong>{eventLabel(event.kind, event.status)}</strong>
                    <span className="muted small">{formatDateTime(event.timestamp)}</span>
                    {event.session_id ? (
                      <span className="tag" title="执行会话">
                        会话 {event.session_id}
                      </span>
                    ) : null}
                  </div>
                  <div className="timeline-detail muted small">
                    {event.global_step !== null ? `Step ${event.global_step}` : ""}
                    {event.epoch !== null ? ` · Epoch ${event.epoch}` : ""}
                    {event.kind === "artifact" ? (
                      <>
                        {" "}
                        · 标签 {event.tag} · 角色 {roleLabel(event.role)}
                        {event.sample_id ? ` · 样本 ${event.sample_id}` : ""}
                        <div className="mono wrap-anywhere">{event.path}</div>
                      </>
                    ) : null}
                    {event.message ? <div>{event.message}</div> : null}
                  </div>
                </div>
              </li>
            ))}
          </ol>
        )}
        {!showHeartbeats && heartbeats.length > 0 ? (
          <p className="muted small">心跳事件默认隐藏，避免淹没训练生命周期；勾选上方选项可查看。</p>
        ) : null}
        {visible.length >= 1000 ? (
          <p className="notice">时间线较长，当前只显示前 1000 条事件。</p>
        ) : null}
      </Panel>
    </div>
  );
}
