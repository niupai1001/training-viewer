import { useEffect, useMemo, useState } from "react";
import type { Artifact, ArtifactGroup } from "../types";
import { formatDateTime, roleLabel } from "../utils/format";
import { EmptyState } from "./Common";
import { TablePreviewDialog } from "./TablePreviewDialog";

const ROLE_ORDER = ["input", "ground_truth", "prediction"];

function isImageArtifact(artifact: Artifact): boolean {
  return (
    ["image", "figure"].includes(artifact.artifact_type) &&
    [".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"].some((suffix) =>
      artifact.path.toLowerCase().endsWith(suffix),
    )
  );
}

function groupRoles(group: ArtifactGroup): { role: string; artifact: Artifact; extraCount: number }[] {
  return Object.entries(group.roles)
    .map(([role, artifacts]) => ({ role, artifact: artifacts[0], extraCount: artifacts.length - 1 }))
    .sort((left, right) => {
      const leftIndex = ROLE_ORDER.indexOf(left.role);
      const rightIndex = ROLE_ORDER.indexOf(right.role);
      return (leftIndex === -1 ? 99 : leftIndex) - (rightIndex === -1 ? 99 : rightIndex);
    });
}

export function PredictionComparisonViewer({
  groups,
  runName,
}: {
  groups: ArtifactGroup[];
  runName?: string;
}) {
  const samples = useMemo(() => {
    const seen = new Set<string>();
    const list: string[] = [];
    for (const group of groups) {
      const sample = group.sample_id ?? group.group_id;
      if (!seen.has(sample)) {
        seen.add(sample);
        list.push(sample);
      }
    }
    return list;
  }, [groups]);

  const [selectedSample, setSelectedSample] = useState<string | null>(samples[0] ?? null);
  const [selectedEpoch, setSelectedEpoch] = useState<number | null | "__none__">(null);
  const [mode, setMode] = useState<"side-by-side" | "overlay">("side-by-side");
  const [baseArtifactId, setBaseArtifactId] = useState<number | null>(null);
  const [overlayArtifactId, setOverlayArtifactId] = useState<number | null>(null);
  const [opacity, setOpacity] = useState(65);
  const [naturalSizes, setNaturalSizes] = useState<Record<number, { width: number; height: number }>>({});
  const [tableArtifact, setTableArtifact] = useState<Artifact | null>(null);

  useEffect(() => {
    if (samples.length > 0 && (selectedSample === null || !samples.includes(selectedSample))) {
      setSelectedSample(samples[0]);
    }
  }, [samples, selectedSample]);

  const sampleGroups = useMemo(
    () =>
      groups
        .filter((group) => (group.sample_id ?? group.group_id) === selectedSample)
        .sort((left, right) => (left.epoch ?? 0) - (right.epoch ?? 0)),
    [groups, selectedSample],
  );

  const epochs = sampleGroups.map((group) => group.epoch);

  useEffect(() => {
    if (sampleGroups.length === 0) {
      setSelectedEpoch("__none__");
      return;
    }
    const stillExists = sampleGroups.some((group) => group.epoch === selectedEpoch);
    if (!stillExists) {
      setSelectedEpoch(sampleGroups[sampleGroups.length - 1].epoch);
    }
  }, [sampleGroups, selectedEpoch]);

  const selectedGroup =
    sampleGroups.find((group) => group.epoch === selectedEpoch) ?? sampleGroups[sampleGroups.length - 1];

  const roleItems = selectedGroup ? groupRoles(selectedGroup) : [];
  const imageRoles = roleItems.filter((item) => isImageArtifact(item.artifact));

  useEffect(() => {
    if (mode !== "overlay" || imageRoles.length === 0) {
      setBaseArtifactId(null);
      setOverlayArtifactId(null);
      return;
    }
    const base = imageRoles.find((item) => item.role === "ground_truth") ?? imageRoles[0];
    const overlay =
      imageRoles.find((item) => item.role === "prediction" && item.artifact.id !== base.artifact.id) ??
      imageRoles.find((item) => item.artifact.id !== base.artifact.id) ??
      base;
    setBaseArtifactId(base.artifact.id);
    setOverlayArtifactId(overlay.artifact.id);
    // 只依赖当前分组的角色身份，避免每次渲染重置用户选择。
  }, [selectedGroup?.group_id, mode]);

  if (groups.length === 0) {
    return (
      <EmptyState
        title="没有可对照的产物"
        description="该标签下没有带样本与训练轮次的图像产物。请确认 events.jsonl 的 artifact 事件提供了 sample_id、group_id、epoch 和 role。"
      />
    );
  }

  const baseArtifact = imageRoles.find((item) => item.artifact.id === baseArtifactId)?.artifact ?? null;
  const overlayArtifact =
    imageRoles.find((item) => item.artifact.id === overlayArtifactId)?.artifact ?? null;
  const baseSize = baseArtifact ? naturalSizes[baseArtifact.id] : undefined;
  const overlaySize = overlayArtifact ? naturalSizes[overlayArtifact.id] : undefined;
  const sizeMismatch =
    baseSize && overlaySize && (baseSize.width !== overlaySize.width || baseSize.height !== overlaySize.height);

  function rememberSize(artifact: Artifact, element: HTMLImageElement) {
    setNaturalSizes((current) => ({
      ...current,
      [artifact.id]: { width: element.naturalWidth, height: element.naturalHeight },
    }));
  }

  return (
    <div className="prediction-viewer">
      <div className="prediction-sidebar">
        <h3>样本</h3>
        <div className="sample-list">
          {samples.map((sample) => (
            <button
              key={sample}
              type="button"
              className={`sample-button ${selectedSample === sample ? "sample-active" : ""}`}
              onClick={() => setSelectedSample(sample)}
            >
              {sample}
            </button>
          ))}
        </div>
        <p className="muted small">
          共 {samples.length} 个样本。图像按 sample_id 与 group_id 关联；不同运行之间不做自动对齐。
        </p>
      </div>
      <div className="prediction-main">
        <div className="prediction-toolbar">
          <div className="toolbar-group">
            <span className="control-label">训练轮次</span>
            <div className="segmented">
              {sampleGroups.map((group, index) => (
                <button
                  key={`${group.group_id}-${index}`}
                  type="button"
                  className={`segment ${selectedGroup?.group_id === group.group_id ? "segment-active" : ""}`}
                  onClick={() => setSelectedEpoch(group.epoch)}
                >
                  {group.epoch === null ? "未标注" : `Epoch ${group.epoch}`}
                </button>
              ))}
            </div>
          </div>
          <div className="toolbar-group">
            <span className="control-label">显示方式</span>
            <div className="segmented">
              <button
                type="button"
                className={`segment ${mode === "side-by-side" ? "segment-active" : ""}`}
                onClick={() => setMode("side-by-side")}
              >
                并排
              </button>
              <button
                type="button"
                className={`segment ${mode === "overlay" ? "segment-active" : ""}`}
                onClick={() => setMode("overlay")}
                disabled={imageRoles.length < 2}
                title={imageRoles.length < 2 ? "叠加至少需要两张图像" : "把预测结果叠加在真实标签上"}
              >
                叠加
              </button>
            </div>
          </div>
          {runName ? <span className="muted small">运行：{runName}</span> : null}
        </div>

        {mode === "side-by-side" ? (
          <div className={`role-grid role-grid-${Math.min(roleItems.length, 3)}`}>
            {roleItems.map(({ role, artifact, extraCount }) => (
              <figure className="role-card" key={`${role}-${artifact.id}`}>
                <figcaption>
                  {roleLabel(role)}
                  {extraCount > 0 ? <span className="muted small">（另有 {extraCount} 个）</span> : null}
                </figcaption>
                {isImageArtifact(artifact) && artifact.exists_on_disk ? (
                  <img
                    src={artifact.content_url}
                    alt={`${roleLabel(role)}：${artifact.sample_id ?? artifact.path}`}
                    loading="lazy"
                    onLoad={(event) => rememberSize(artifact, event.currentTarget)}
                  />
                ) : (
                  <div className="artifact-missing">
                    <span>{artifact.exists_on_disk ? "该产物不是图像" : "文件缺失"}</span>
                    <a href={artifact.download_url} download>
                      下载文件
                    </a>
                  </div>
                )}
                <div className="role-meta">
                  <span title={artifact.path}>{artifact.path.split("/").pop()}</span>
                  <span className="muted small">
                    {artifact.epoch !== null ? `Epoch ${artifact.epoch}` : ""}
                    {artifact.timestamp ? ` · ${formatDateTime(artifact.timestamp)}` : ""}
                  </span>
                </div>
              </figure>
            ))}
          </div>
        ) : (
          <div className="overlay-viewer">
            <div className="overlay-controls">
              <label>
                底层
                <select
                  value={baseArtifactId ?? ""}
                  onChange={(event) => setBaseArtifactId(Number(event.target.value))}
                >
                  {imageRoles.map(({ role, artifact }) => (
                    <option key={artifact.id} value={artifact.id}>
                      {roleLabel(role)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                叠加层
                <select
                  value={overlayArtifactId ?? ""}
                  onChange={(event) => setOverlayArtifactId(Number(event.target.value))}
                >
                  {imageRoles.map(({ role, artifact }) => (
                    <option key={artifact.id} value={artifact.id}>
                      {roleLabel(role)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="overlay-opacity">
                叠加透明度
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={opacity}
                  onChange={(event) => setOpacity(Number(event.target.value))}
                />
                <span>{opacity}%</span>
              </label>
            </div>
            {sizeMismatch ? (
              <p className="notice notice-warning">
                两张图像尺寸不同（{baseSize?.width}×{baseSize?.height} 与 {overlaySize?.width}×
                {overlaySize?.height}），直接叠加会产生位移；当前按等比例拉伸显示。
              </p>
            ) : null}
            {baseArtifact ? (
              <div className="overlay-canvas">
                <img
                  src={baseArtifact.content_url}
                  alt="叠加底层"
                  onLoad={(event) => rememberSize(baseArtifact, event.currentTarget)}
                />
                {overlayArtifact ? (
                  <img
                    className="overlay-image"
                    src={overlayArtifact.content_url}
                    alt="叠加预测结果"
                    style={{ opacity: opacity / 100 }}
                    onLoad={(event) => rememberSize(overlayArtifact, event.currentTarget)}
                  />
                ) : null}
              </div>
            ) : (
              <EmptyState title="没有可叠加的图像" />
            )}
          </div>
        )}

        {selectedGroup ? (
          <div className="prediction-summary">
            <span>
              分组：{selectedGroup.group_id} · 阶段：{selectedGroup.phase ?? "未标注"} · 标签：
              {selectedGroup.tag}
            </span>
            {roleItems.some(({ artifact }) => !isImageArtifact(artifact)) ? (
              <div className="role-file-actions">
                {roleItems
                  .filter(({ artifact }) => !isImageArtifact(artifact))
                  .map(({ role, artifact }) => (
                    <div key={artifact.id}>
                      <span>{roleLabel(role)}：{artifact.path.split("/").pop()}</span>
                      {[".csv", ".tsv", ".json"].some((suffix) =>
                        artifact.path.toLowerCase().endsWith(suffix),
                      ) ? (
                        <button
                          type="button"
                          className="button button-small"
                          onClick={() => setTableArtifact(artifact)}
                        >
                          预览
                        </button>
                      ) : null}
                      <a className="button button-small" href={artifact.download_url} download>
                        下载
                      </a>
                    </div>
                  ))}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
      {tableArtifact ? (
        <TablePreviewDialog artifact={tableArtifact} onClose={() => setTableArtifact(null)} />
      ) : null}
    </div>
  );
}
