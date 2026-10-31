import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { useLiveVersion } from "../live/LiveUpdates";
import { roleLabel } from "../utils/format";

/** 结果文件候选：事件未引用时，明确展示“推断、未确认”的图片。 */
export function ResultCandidatePanel({ runId }: { runId: string }) {
  const liveVersion = useLiveVersion();
  const state = useApi(() => api.resultCandidates(runId), [runId, liveVersion]);
  if (!state.data || state.data.candidates.length === 0) {
    return null;
  }
  const candidates = state.data.candidates
    .filter((candidate) => candidate.role_guess === "prediction")
    .slice(0, 6);
  const shown = candidates.length > 0 ? candidates : state.data.candidates.slice(0, 6);
  return (
    <section className="result-candidates">
      <header>
        <h2>结果文件候选</h2>
        <p className="muted small">{state.data.note}</p>
      </header>
      <div className="latest-artifact-grid">
        {shown.map((candidate) => (
          <figure key={candidate.path}>
            <img src={candidate.content_url} alt={candidate.path} loading="lazy" />
            <figcaption>
              {roleLabel(candidate.role_guess ?? "未分类")} · 置信度 {candidate.confidence}
              <span className="muted small"> · 未确认</span>
            </figcaption>
          </figure>
        ))}
      </div>
    </section>
  );
}
