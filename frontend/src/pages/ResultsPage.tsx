import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { useLiveVersion } from "../live/LiveUpdates";
import { useRoute } from "../navigation/route";
import {
  EmptyState,
  ErrorBlock,
  LoadingBlock,
  PageHeader,
  Panel,
} from "../components/Common";
import { PredictionComparisonViewer } from "../components/PredictionComparisonViewer";
import { ArtifactGallery } from "../components/ArtifactGallery";

export function ResultsPage() {
  const route = useRoute();
  const routeKey = route.params.toString();
  const liveVersion = useLiveVersion();
  const [selectedRunId, setSelectedRunId] = useState<string>(route.params.get("run") ?? "");
  const [selectedTag, setSelectedTag] = useState<string>(route.params.get("tag") ?? "");
  const [showGallery, setShowGallery] = useState(false);

  const runsState = useApi(() => api.runs({ limit: 1000, sort: "-last_updated_at" }), [liveVersion]);

  useEffect(() => {
    const runFromUrl = route.params.get("run") ?? "";
    if (runFromUrl && runFromUrl !== selectedRunId) {
      setSelectedRunId(runFromUrl);
    }
    const tagFromUrl = route.params.get("tag") ?? "";
    if (tagFromUrl !== selectedTag) {
      setSelectedTag(tagFromUrl);
    }
    // 仅响应外部导航。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeKey]);

  useEffect(() => {
    if (!selectedRunId && runsState.data?.runs.length) {
      setSelectedRunId(runsState.data.runs[0].run_id);
    }
  }, [selectedRunId, runsState.data]);

  const runState = useApi(
    () => (selectedRunId ? api.run(selectedRunId) : Promise.resolve(null)),
    [selectedRunId, liveVersion],
  );
  const groupsState = useApi(
    () =>
      selectedRunId
        ? api.artifactGroups(selectedRunId, selectedTag || undefined)
        : Promise.resolve(null),
    [selectedRunId, selectedTag, liveVersion],
  );
  const artifactsState = useApi(
    () => (selectedRunId ? api.artifacts(selectedRunId) : Promise.resolve(null)),
    [selectedRunId, liveVersion],
  );

  const tags = useMemo(() => {
    const map = new Map<string, number>();
    for (const item of runState.data?.artifact_tags ?? []) {
      map.set(item.tag, (map.get(item.tag) ?? 0) + item.count);
    }
    return Array.from(map.entries());
  }, [runState.data]);

  useEffect(() => {
    if (tags.length === 0) {
      return;
    }
    if (!selectedTag || !tags.some(([tag]) => tag === selectedTag)) {
      setSelectedTag(tags[0][0]);
    }
    // 运行切换后选择第一个有产物的标签。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedRunId, tags.map(([tag]) => tag).join("|")]);

  useEffect(() => {
    if (!selectedRunId) {
      return;
    }
    const params = new URLSearchParams();
    params.set("run", selectedRunId);
    if (selectedTag) {
      params.set("tag", selectedTag);
    }
    window.history.replaceState(null, "", `#/results?${params.toString()}`);
  }, [selectedRunId, selectedTag]);

  if (runsState.loading) {
    return (
      <div className="page">
        <LoadingBlock label="正在加载运行列表…" />
      </div>
    );
  }
  if (runsState.error) {
    return (
      <div className="page">
        <ErrorBlock error={runsState.error} onRetry={runsState.reload} />
      </div>
    );
  }

  const runs = runsState.data?.runs ?? [];

  return (
    <div className="page results-page">
      <PageHeader
        title="预测结果浏览"
        subtitle="按样本和训练轮次对照原图、真实标签与预测结果；图像只在浏览器中显示，不会执行 HTML 产物中的脚本。"
        actions={
          selectedRunId ? (
            <a className="button" href={`#/runs/${encodeURIComponent(selectedRunId)}`}>
              打开运行详情
            </a>
          ) : null
        }
      />

      {runs.length === 0 ? (
        <EmptyState
          title="还没有可浏览的运行"
          description="先在总览页添加训练日志目录。实验结果图像来自 events.jsonl 的 artifact 事件。"
        />
      ) : (
        <>
          <div className="filter-bar results-toolbar">
            <label>
              运行
              <select value={selectedRunId} onChange={(event) => setSelectedRunId(event.target.value)}>
                {runs.map((run) => (
                  <option key={run.run_id} value={run.run_id}>
                    {run.name}（{run.project}）
                  </option>
                ))}
              </select>
            </label>
            <div className="tag-filter">
              {tags.length > 1 ? (
                <button
                  type="button"
                  className={`chip ${selectedTag === "" ? "chip-active" : ""}`}
                  onClick={() => setSelectedTag("")}
                >
                  全部标签
                </button>
              ) : null}
              {tags.map(([tag, count]) => (
                <button
                  key={tag}
                  type="button"
                  className={`chip ${selectedTag === tag ? "chip-active" : ""}`}
                  onClick={() => setSelectedTag(tag)}
                >
                  {tag}（{count}）
                </button>
              ))}
            </div>
            <button
              type="button"
              className="button button-small"
              onClick={() => setShowGallery((value) => !value)}
            >
              {showGallery ? "收起全部产物" : "显示全部产物"}
            </button>
          </div>

          {runState.loading ? <LoadingBlock label="正在读取运行信息…" /> : null}
          {runState.error ? <ErrorBlock error={runState.error} onRetry={runState.reload} /> : null}
          {runState.data ? (
            <p className="muted small">
              运行“{runState.data.name}”共有 {runState.data.counts.artifact_count} 个产物引用
              {runState.data.counts.missing_artifact_count > 0
                ? `，其中 ${runState.data.counts.missing_artifact_count} 个文件当前缺失`
                : ""}
              。同一 group_id 的原图、标签和预测会并排显示。
            </p>
          ) : null}

          {groupsState.loading ? <LoadingBlock label="正在读取预测结果…" /> : null}
          {groupsState.error ? (
            <ErrorBlock error={groupsState.error} onRetry={groupsState.reload} />
          ) : null}
          {groupsState.data ? (
            <Panel title="样本对照">
              <PredictionComparisonViewer
                groups={groupsState.data.groups}
                runName={runState.data?.name}
              />
            </Panel>
          ) : null}

          {showGallery ? (
            <Panel title="全部实验产物">
              {artifactsState.loading ? <LoadingBlock /> : null}
              {artifactsState.error ? (
                <ErrorBlock error={artifactsState.error} onRetry={artifactsState.reload} />
              ) : null}
              {artifactsState.data ? (
                <ArtifactGallery artifacts={artifactsState.data.artifacts} />
              ) : null}
            </Panel>
          ) : null}
        </>
      )}
    </div>
  );
}
