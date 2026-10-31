import { useState } from "react";
import type { ReactNode } from "react";
import type { Artifact } from "../types";
import { formatFileSize, roleLabel } from "../utils/format";

/**
 * 实验产物视图插件注册表。
 * 每种 artifact_type 由独立插件渲染；第三方可通过 registerArtifactViewPlugin
 * 注册新类型，而无需修改实验产物列表页。
 */
export interface ArtifactViewProps {
  artifact: Artifact;
  onOpenImage: (artifact: Artifact) => void;
  onPreviewTable: (artifact: Artifact) => void;
}

export interface ArtifactViewPlugin {
  id: string;
  label: string;
  supports: (artifact: Artifact) => boolean;
  render: (props: ArtifactViewProps) => ReactNode;
}

const IMAGE_SUFFIXES = [".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"];

function isImageArtifact(artifact: Artifact): boolean {
  if (!["image", "figure"].includes(artifact.artifact_type)) {
    return false;
  }
  const lower = artifact.path.toLowerCase();
  return IMAGE_SUFFIXES.some((suffix) => lower.endsWith(suffix));
}

function ImageArtifactView({ artifact, onOpenImage }: ArtifactViewProps) {
  const [broken, setBroken] = useState(false);
  const missing = !artifact.exists_on_disk || broken;
  return (
    <article className="artifact-card artifact-image-card">
      <button
        type="button"
        className="artifact-thumb-button"
        onClick={() => onOpenImage(artifact)}
        disabled={missing}
        title={missing ? "产物文件不存在" : "打开大图"}
      >
        {missing ? (
          <div className="artifact-missing">
            <span>文件缺失</span>
            <span className="small">训练日志记录了引用，但当前目录中找不到文件</span>
          </div>
        ) : (
          <img
            src={artifact.content_url}
            alt={`${roleLabel(artifact.role)}：${artifact.sample_id ?? artifact.path}`}
            loading="lazy"
            onError={() => setBroken(true)}
          />
        )}
      </button>
      <div className="artifact-meta">
        <span className="artifact-role">{roleLabel(artifact.role)}</span>
        <span className="artifact-path" title={artifact.path}>
          {artifact.sample_id ?? artifact.path.split("/").pop()}
        </span>
        <span className="muted small">
          {artifact.epoch !== null ? `Epoch ${artifact.epoch}` : ""}
          {artifact.global_step !== null ? ` · Step ${artifact.global_step}` : ""}
          {artifact.phase ? ` · ${artifact.phase}` : ""}
        </span>
      </div>
    </article>
  );
}

function TableArtifactView({ artifact, onPreviewTable }: ArtifactViewProps) {
  return (
    <article className="artifact-card artifact-file-card">
      <div className="file-icon" aria-hidden="true">
        ⊞
      </div>
      <div className="artifact-meta">
        <span className="artifact-role">{roleLabel(artifact.role)}</span>
        <span className="artifact-path" title={artifact.path}>
          {artifact.path.split("/").pop()}
        </span>
        <span className="muted small">
          {formatFileSize(artifact.size)}
          {artifact.epoch !== null ? ` · Epoch ${artifact.epoch}` : ""}
        </span>
        <div className="artifact-actions">
          <button
            type="button"
            className="button button-small"
            onClick={() => onPreviewTable(artifact)}
            disabled={!artifact.exists_on_disk}
          >
            预览表格
          </button>
          <a className="button button-small" href={artifact.download_url} download>
            下载
          </a>
        </div>
      </div>
    </article>
  );
}

function HtmlArtifactView({ artifact }: ArtifactViewProps) {
  return (
    <article className="artifact-card artifact-file-card">
      <div className="file-icon" aria-hidden="true">
        ▤
      </div>
      <div className="artifact-meta">
        <span className="artifact-role">{roleLabel(artifact.role)}</span>
        <span className="artifact-path" title={artifact.path}>
          {artifact.path.split("/").pop()}
        </span>
        <span className="muted small">
          HTML 产物按不可信内容处理，不在查看器内执行其脚本。
        </span>
        <div className="artifact-actions">
          <a className="button button-small" href={artifact.download_url} download>
            下载查看
          </a>
        </div>
      </div>
    </article>
  );
}

function ModelArtifactView({ artifact }: ArtifactViewProps) {
  return (
    <article className="artifact-card artifact-file-card">
      <div className="file-icon" aria-hidden="true">
        ◈
      </div>
      <div className="artifact-meta">
        <span className="artifact-role">{roleLabel(artifact.role)}</span>
        <span className="artifact-path" title={artifact.path}>
          {artifact.path.split("/").pop()}
        </span>
        <span className="muted small">
          模型文件（{formatFileSize(artifact.size)}）；查看器只显示元数据，不反序列化加载。
        </span>
        <div className="artifact-actions">
          <a className="button button-small" href={artifact.download_url} download>
            下载文件
          </a>
        </div>
      </div>
    </article>
  );
}

function GenericFileArtifactView({ artifact, onPreviewTable }: ArtifactViewProps) {
  const suffix = artifact.path.toLowerCase();
  const previewable = suffix.endsWith(".csv") || suffix.endsWith(".tsv") || suffix.endsWith(".json");
  return (
    <article className="artifact-card artifact-file-card">
      <div className="file-icon" aria-hidden="true">
        ▣
      </div>
      <div className="artifact-meta">
        <span className="artifact-role">{roleLabel(artifact.role)}</span>
        <span className="artifact-path" title={artifact.path}>
          {artifact.path.split("/").pop()}
        </span>
        <span className="muted small">
          {artifact.artifact_type} · {formatFileSize(artifact.size)}
        </span>
        <div className="artifact-actions">
          {previewable ? (
            <button
              type="button"
              className="button button-small"
              onClick={() => onPreviewTable(artifact)}
              disabled={!artifact.exists_on_disk}
            >
              预览表格
            </button>
          ) : null}
          <a className="button button-small" href={artifact.download_url} download>
            下载
          </a>
        </div>
      </div>
    </article>
  );
}

const plugins: ArtifactViewPlugin[] = [
  {
    id: "artifact.image",
    label: "图像预览",
    supports: isImageArtifact,
    render: (props) => <ImageArtifactView {...props} />,
  },
  {
    id: "artifact.table",
    label: "表格预览",
    supports: (artifact) => artifact.artifact_type === "table",
    render: (props) => <TableArtifactView {...props} />,
  },
  {
    id: "artifact.html",
    label: "HTML 下载",
    supports: (artifact) => artifact.artifact_type === "html",
    render: (props) => <HtmlArtifactView {...props} />,
  },
  {
    id: "artifact.model",
    label: "模型文件信息",
    supports: (artifact) => artifact.artifact_type === "model",
    render: (props) => <ModelArtifactView {...props} />,
  },
  {
    id: "artifact.generic-file",
    label: "通用文件",
    supports: () => true,
    render: (props) => <GenericFileArtifactView {...props} />,
  },
];

export function registerArtifactViewPlugin(plugin: ArtifactViewPlugin): void {
  const index = plugins.findIndex((existing) => existing.id === plugin.id);
  if (index >= 0) {
    plugins[index] = plugin;
  } else {
    plugins.splice(plugins.length - 1, 0, plugin);
  }
}

export function getArtifactViewPlugin(artifact: Artifact): ArtifactViewPlugin {
  return plugins.find((plugin) => plugin.supports(artifact)) ?? plugins[plugins.length - 1];
}

export function listArtifactViewPlugins(): ArtifactViewPlugin[] {
  return [...plugins];
}
