import { useMemo, useState } from "react";
import type { Artifact } from "../types";
import { formatFileSize, formatDateTime, roleLabel } from "../utils/format";
import { getArtifactViewPlugin } from "../view_plugins/artifactViews";
import { EmptyState } from "./Common";
import { Modal } from "./Modal";
import { TablePreviewDialog } from "./TablePreviewDialog";

export function ArtifactGallery({
  artifacts,
  emptyMessage = "该运行还没有记录实验产物。",
}: {
  artifacts: Artifact[];
  emptyMessage?: string;
}) {
  const [activeTag, setActiveTag] = useState<string>("__all__");
  const [lightboxArtifact, setLightboxArtifact] = useState<Artifact | null>(null);
  const [tableArtifact, setTableArtifact] = useState<Artifact | null>(null);

  const tags = useMemo(() => {
    const counts = new Map<string, number>();
    for (const artifact of artifacts) {
      counts.set(artifact.tag, (counts.get(artifact.tag) ?? 0) + 1);
    }
    return Array.from(counts.entries());
  }, [artifacts]);

  const visible = useMemo(
    () => (activeTag === "__all__" ? artifacts : artifacts.filter((item) => item.tag === activeTag)),
    [artifacts, activeTag],
  );

  const grouped = useMemo(() => {
    const groups = new Map<string, Artifact[]>();
    for (const artifact of visible) {
      const list = groups.get(artifact.tag) ?? [];
      list.push(artifact);
      groups.set(artifact.tag, list);
    }
    return Array.from(groups.entries());
  }, [visible]);

  if (artifacts.length === 0) {
    return <EmptyState title="没有实验产物" description={emptyMessage} />;
  }

  return (
    <div className="artifact-gallery">
      {tags.length > 1 ? (
        <div className="tag-filter" role="group" aria-label="按产物标签筛选">
          <button
            type="button"
            className={`chip ${activeTag === "__all__" ? "chip-active" : ""}`}
            onClick={() => setActiveTag("__all__")}
          >
            全部（{artifacts.length}）
          </button>
          {tags.map(([tag, count]) => (
            <button
              key={tag}
              type="button"
              className={`chip ${activeTag === tag ? "chip-active" : ""}`}
              onClick={() => setActiveTag(tag)}
            >
              {tag}（{count}）
            </button>
          ))}
        </div>
      ) : null}
      {grouped.map(([tag, items]) => (
        <section key={tag} className="artifact-group">
          <h3 className="artifact-group-title">{tag}</h3>
          <div className="artifact-grid">
            {items.map((artifact) => {
              const plugin = getArtifactViewPlugin(artifact);
              return (
                <div key={artifact.id} data-view-plugin={plugin.id}>
                  {plugin.render({
                    artifact,
                    onOpenImage: setLightboxArtifact,
                    onPreviewTable: setTableArtifact,
                  })}
                </div>
              );
            })}
          </div>
        </section>
      ))}
      {lightboxArtifact ? (
        <Modal
          title={`${roleLabel(lightboxArtifact.role)} · ${lightboxArtifact.path.split("/").pop()}`}
          subtitle={`标签 ${lightboxArtifact.tag}${
            lightboxArtifact.epoch !== null ? ` · Epoch ${lightboxArtifact.epoch}` : ""
          }${lightboxArtifact.sample_id ? ` · 样本 ${lightboxArtifact.sample_id}` : ""}`}
          onClose={() => setLightboxArtifact(null)}
          wide
        >
          <div className="lightbox">
            <img
              src={lightboxArtifact.content_url}
              alt={`${roleLabel(lightboxArtifact.role)} ${lightboxArtifact.path}`}
            />
          </div>
          <dl className="detail-list">
            <dt>文件路径</dt>
            <dd>{lightboxArtifact.path}</dd>
            <dt>文件大小</dt>
            <dd>{formatFileSize(lightboxArtifact.size)}</dd>
            <dt>记录时间</dt>
            <dd>{formatDateTime(lightboxArtifact.timestamp)}</dd>
          </dl>
          <div className="dialog-actions">
            <a className="button" href={lightboxArtifact.download_url} download>
              下载原始文件
            </a>
          </div>
        </Modal>
      ) : null}
      {tableArtifact ? (
        <TablePreviewDialog artifact={tableArtifact} onClose={() => setTableArtifact(null)} />
      ) : null}
    </div>
  );
}
