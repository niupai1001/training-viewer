import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { useLiveVersion } from "../live/LiveUpdates";
import type { Artifact, ArtifactGroup } from "../types";
import { roleLabel } from "../utils/format";

function imageArtifacts(group: ArtifactGroup): { role: string; artifact: Artifact }[] {
  return Object.entries(group.roles)
    .map(([role, artifacts]) => ({ role, artifact: artifacts[0] }))
    .filter(({ artifact }) =>
      ["image", "figure"].includes(artifact.artifact_type) &&
      [".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"].some((suffix) =>
        artifact.path.toLowerCase().endsWith(suffix),
      ),
    )
    .sort((left, right) => {
      const order = ["input", "ground_truth", "prediction"];
      return order.indexOf(left.role) - order.indexOf(right.role);
    });
}

/** 运行页内嵌的“最新预测样本”预览；完整图库仍在产物标签页。 */
export function LatestArtifactPreview({ runId }: { runId: string }) {
  const liveVersion = useLiveVersion();
  const state = useApi(() => api.artifactGroups(runId), [runId, liveVersion]);
  if (!state.data) {
    return null;
  }
  const group = [...state.data.groups]
    .filter((item) => imageArtifacts(item).length > 0)
    .sort((left, right) => (right.epoch ?? 0) - (left.epoch ?? 0))[0];
  if (!group) {
    return null;
  }
  const images = imageArtifacts(group).slice(0, 3);
  return (
    <section className="latest-artifact-preview">
      <header>
        <div>
          <h2>最新预测样本</h2>
          <p className="muted small">
            {group.sample_id ?? group.group_id}
            {group.epoch !== null ? ` · Epoch ${group.epoch}` : ""} · 标签 {group.tag}
          </p>
        </div>
        <a href={`#/results?run=${encodeURIComponent(runId)}&tag=${encodeURIComponent(group.tag)}`}>
          查看完整结果
        </a>
      </header>
      <div className="latest-artifact-grid">
        {images.map(({ role, artifact }) => (
          <figure key={`${role}-${artifact.id}`}>
            <img src={artifact.content_url} alt={`${roleLabel(role)} ${artifact.path}`} loading="lazy" />
            <figcaption>{roleLabel(role)}</figcaption>
          </figure>
        ))}
      </div>
    </section>
  );
}
