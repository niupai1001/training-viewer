import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { useLiveVersion } from "../live/LiveUpdates";
import type { RunDetail } from "../types";
import { formatNumber } from "../utils/format";
import { ArtifactGallery } from "./ArtifactGallery";
import { EmptyState, ErrorBlock, LoadingBlock, Panel, WarningList } from "./Common";

export function RunArtifactsTab({ run }: { run: RunDetail }) {
  const liveVersion = useLiveVersion();
  const state = useApi(
    () => api.artifacts(run.run_id),
    [run.run_id, run.status === "running" ? liveVersion : 0],
  );

  if (state.loading) {
    return <LoadingBlock label="正在读取实验产物清单…" />;
  }
  if (state.error) {
    return <ErrorBlock error={state.error} onRetry={state.reload} />;
  }

  const artifacts = state.data?.artifacts ?? [];
  const missing = artifacts.filter((artifact) => !artifact.exists_on_disk).length;

  return (
    <div className="artifacts-tab">
      <Panel
        title="实验产物"
        actions={
          <span className="muted small">
            共 {formatNumber(artifacts.length, 0)} 个引用
            {missing > 0 ? `，其中 ${missing} 个文件缺失` : ""}
          </span>
        }
      >
        {missing > 0 ? (
          <WarningList
            warnings={[
              {
                code: "missing_artifacts",
                severity: "warning",
                message: `有 ${missing} 个产物事件引用的文件当前不存在。查看器保留引用记录，不会伪造内容；请检查训练程序是否已写入文件或目录是否被移动。`,
              },
            ]}
          />
        ) : null}
        <ArtifactGallery artifacts={artifacts} />
        <p className="muted small">
          图像按角色（原图 / 真实标签 / 预测结果）展示。HTML、SVG 产物不作为可执行页面加载；模型文件只显示元数据并允许下载，
          查看器不会反序列化任意模型文件。
        </p>
      </Panel>
      {run.artifact_tags.length === 0 ? (
        <EmptyState
          title="还没有产物标签"
          description="训练程序可以在 events.jsonl 中写入 artifact 事件，引用图像、表格、HTML 或模型文件。"
        />
      ) : null}
    </div>
  );
}
