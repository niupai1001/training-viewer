import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { useLiveVersion } from "../live/LiveUpdates";
import { navigate, navigateWithParams, useRoute } from "../navigation/route";
import type { RunSummary } from "../types";
import {
  formatDateTime,
  formatDuration,
  formatMetricValue,
  formatNumber,
  formatRelativeTime,
  statusLabel,
} from "../utils/format";
import {
  EmptyState,
  ErrorBlock,
  LoadingBlock,
  PageHeader,
  StatusBadge,
  WarnBadge,
} from "../components/Common";

interface Filters {
  project: string;
  experiment: string;
  status: string;
  q: string;
  tag: string;
  task: string;
  model: string;
  dataset: string;
  favorite: boolean;
}

const EMPTY_FILTERS: Filters = {
  project: "",
  experiment: "",
  status: "",
  q: "",
  tag: "",
  task: "",
  model: "",
  dataset: "",
  favorite: false,
};

const COLUMN_DEFINITIONS = [
  { id: "status", label: "状态" },
  { id: "group", label: "项目 / 实验组" },
  { id: "model", label: "模型" },
  { id: "dataset", label: "数据集" },
  { id: "seed", label: "随机种子" },
  { id: "updated", label: "最近更新" },
  { id: "duration", label: "数据时长" },
  { id: "primary", label: "关键指标" },
  { id: "note", label: "备注" },
  { id: "artifacts", label: "产物" },
  { id: "issues", label: "日志问题" },
];

const PAGE_SIZE = 50;
const MAX_COMPARE_RUNS = 12;
const COLUMN_STORAGE_KEY = "training-viewer.experiment-columns.v2";
const DEFAULT_VISIBLE_COLUMNS = ["status", "primary", "updated"];

function loadVisibleColumns(): string[] {
  try {
    const stored = window.localStorage.getItem(COLUMN_STORAGE_KEY);
    if (stored) {
      const parsed = JSON.parse(stored) as unknown;
      if (Array.isArray(parsed) && parsed.every((item) => typeof item === "string")) {
        return parsed;
      }
    }
  } catch {
    // 存储不可用时使用默认列。
  }
  return DEFAULT_VISIBLE_COLUMNS;
}

export function ExperimentsPage() {
  const route = useRoute();
  const liveVersion = useLiveVersion();
  const routeKey = route.params.toString();
  const [filters, setFilters] = useState<Filters>(() => ({
    ...EMPTY_FILTERS,
    project: route.params.get("project") ?? "",
    experiment: route.params.get("experiment") ?? "",
    status: route.params.get("status") ?? "",
  }));
  const [searchInput, setSearchInput] = useState("");
  const [sort, setSort] = useState("-last_updated_at");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<string[]>([]);
  const [visibleColumns, setVisibleColumns] = useState<string[]>(loadVisibleColumns);
  const [showColumns, setShowColumns] = useState(false);

  useEffect(() => {
    setFilters((current) => ({
      ...current,
      project: route.params.get("project") ?? "",
      experiment: route.params.get("experiment") ?? "",
      status: route.params.get("status") ?? "",
    }));
    setOffset(0);
    // 只在地址栏参数变化时同步，避免覆盖用户当前筛选。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeKey]);

  useEffect(() => {
    window.localStorage.setItem(COLUMN_STORAGE_KEY, JSON.stringify(visibleColumns));
  }, [visibleColumns]);

  const [debouncedSearch, setDebouncedSearch] = useState("");
  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(searchInput), 300);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  const projects = useApi(() => api.projects(), [liveVersion]);
  const facets = useApi(() => api.facets(), [liveVersion]);
  const runsState = useApi(
    () =>
      api.runs({
        project: filters.project || undefined,
        experiment: filters.experiment || undefined,
        status: filters.status || undefined,
        q: debouncedSearch || undefined,
        tag: filters.tag || undefined,
        task: filters.task || undefined,
        model: filters.model || undefined,
        dataset: filters.dataset || undefined,
        favorite: filters.favorite || undefined,
        sort,
        limit: PAGE_SIZE,
        offset,
      }),
    [
      filters.project,
      filters.experiment,
      filters.status,
      filters.tag,
      filters.task,
      filters.model,
      filters.dataset,
      filters.favorite,
      debouncedSearch,
      sort,
      offset,
      liveVersion,
    ],
  );

  useEffect(() => {
    setOffset(0);
  }, [
    filters.project,
    filters.experiment,
    filters.status,
    filters.tag,
    filters.task,
    filters.model,
    filters.dataset,
    filters.favorite,
    debouncedSearch,
    sort,
  ]);

  const experimentOptions = useMemo(() => {
    const project = projects.data?.projects.find((item) => item.name === filters.project);
    return project?.experiments ?? [];
  }, [projects.data, filters.project]);

  const runs = runsState.data?.runs ?? [];
  const total = runsState.data?.total ?? 0;
  const hasActiveFilters = Object.entries(filters).some(([, value]) =>
    typeof value === "boolean" ? value : value !== "",
  ) || searchInput !== "";

  function updateFilter<K extends keyof Filters>(key: K, value: Filters[K]) {
    setFilters((current) => ({
      ...current,
      [key]: value,
      ...(key === "project" ? { experiment: "" } : {}),
    }));
  }

  function toggleSort(field: string) {
    setSort((current) => (current === field ? `-${field}` : current === `-${field}` ? field : `-${field}`));
  }

  function sortIndicator(field: string) {
    if (sort === field) {
      return " ▲";
    }
    if (sort === `-${field}`) {
      return " ▼";
    }
    return "";
  }

  function toggleSelection(runId: string) {
    setSelected((current) =>
      current.includes(runId)
        ? current.filter((id) => id !== runId)
        : current.length >= MAX_COMPARE_RUNS
          ? current
          : [...current, runId],
    );
  }

  async function toggleFavorite(run: RunSummary) {
    await api.updateAnnotation(run.run_id, { favorite: !run.favorite });
    runsState.reload();
  }

  function openComparison() {
    navigateWithParams("/compare", { runs: selected.join(",") });
  }

  return (
    <div className="page">
      <PageHeader
        title="实验库"
        subtitle="按最近更新查看、筛选和对比训练运行；默认只显示最常用的几列，更多列在“列设置”中。"
        actions={
          <div className="header-actions">
            <div className="column-picker-wrapper">
              <button
                type="button"
                className="button"
                onClick={() => setShowColumns((value) => !value)}
                aria-expanded={showColumns}
              >
                列设置
              </button>
              {showColumns ? (
                <div className="column-picker" role="group" aria-label="显示或隐藏表格列">
                  {COLUMN_DEFINITIONS.map((column) => (
                    <label key={column.id}>
                      <input
                        type="checkbox"
                        checked={visibleColumns.includes(column.id)}
                        onChange={(event) =>
                          setVisibleColumns((current) =>
                            event.target.checked
                              ? [...current, column.id]
                              : current.filter((id) => id !== column.id),
                          )
                        }
                      />
                      {column.label}
                    </label>
                  ))}
                </div>
              ) : null}
            </div>
            <button
              type="button"
              className="button button-primary"
              disabled={selected.length === 0}
              onClick={openComparison}
            >
              对比选中（{selected.length}）
            </button>
          </div>
        }
      />

      <div className="filter-bar">
        <label className="filter-search">
          搜索
          <input
            type="search"
            value={searchInput}
            placeholder="名称、run_id、项目、模型…"
            onChange={(event) => setSearchInput(event.target.value)}
          />
        </label>
        <label>
          项目
          <select value={filters.project} onChange={(event) => updateFilter("project", event.target.value)}>
            <option value="">全部项目</option>
            {projects.data?.projects.map((project) => (
              <option key={project.name} value={project.name}>
                {project.name}（{project.run_count}）
              </option>
            ))}
          </select>
        </label>
        <label>
          状态
          <select value={filters.status} onChange={(event) => updateFilter("status", event.target.value)}>
            <option value="">全部状态</option>
            {["running", "completed", "failed", "cancelled", "unknown", "imported"].map((status) => (
              <option key={status} value={status}>
                {statusLabel(status)}
              </option>
            ))}
          </select>
        </label>
        {hasActiveFilters ? (
          <button
            type="button"
            className="button button-small"
            onClick={() => {
              setFilters(EMPTY_FILTERS);
              setSearchInput("");
            }}
          >
            清除筛选
          </button>
        ) : null}
        <details className="advanced-filters">
          <summary>高级筛选（实验组、标签、模型、数据集、任务、收藏）</summary>
          <div className="advanced-filter-fields">
            <label>
              实验组
              <select
                value={filters.experiment}
                onChange={(event) => updateFilter("experiment", event.target.value)}
                disabled={!filters.project}
              >
                <option value="">全部实验组</option>
                {experimentOptions.map((experiment) => (
                  <option key={experiment.name ?? "ungrouped"} value={experiment.name ?? ""}>
                    {experiment.name ?? "未分组"}（{experiment.run_count}）
                  </option>
                ))}
              </select>
            </label>
            <label>
              标签
              <select value={filters.tag} onChange={(event) => updateFilter("tag", event.target.value)}>
                <option value="">全部标签</option>
                {facets.data?.tags.map((tag) => (
                  <option key={tag} value={tag}>
                    {tag}
                  </option>
                ))}
              </select>
            </label>
            <label>
              模型
              <select value={filters.model} onChange={(event) => updateFilter("model", event.target.value)}>
                <option value="">全部模型</option>
                {facets.data?.models.map((model) => (
                  <option key={model} value={model}>
                    {model}
                  </option>
                ))}
              </select>
            </label>
            <label>
              数据集
              <select value={filters.dataset} onChange={(event) => updateFilter("dataset", event.target.value)}>
                <option value="">全部数据集</option>
                {facets.data?.datasets.map((dataset) => (
                  <option key={dataset} value={dataset}>
                    {dataset}
                  </option>
                ))}
              </select>
            </label>
            <label>
              任务
              <select value={filters.task} onChange={(event) => updateFilter("task", event.target.value)}>
                <option value="">全部任务</option>
                {facets.data?.tasks.map((task) => (
                  <option key={task} value={task}>
                    {task}
                  </option>
                ))}
              </select>
            </label>
            <label className="filter-check">
              <input
                type="checkbox"
                checked={filters.favorite}
                onChange={(event) => updateFilter("favorite", event.target.checked)}
              />
              只看收藏
            </label>
          </div>
        </details>
      </div>

      {selected.length > 0 ? (
        <div className="batch-bar">
          <span>已选择 {selected.length} 个运行（最多 {MAX_COMPARE_RUNS} 个）。</span>
          <button type="button" className="button button-small" onClick={openComparison}>
            实验对比
          </button>
          <button type="button" className="button button-small" onClick={() => setSelected([])}>
            清除选择
          </button>
        </div>
      ) : null}

      {runsState.loading ? <LoadingBlock /> : null}
      {runsState.error ? <ErrorBlock error={runsState.error} onRetry={runsState.reload} /> : null}

      {runsState.data && runs.length === 0 ? (
        <EmptyState
          title={hasActiveFilters ? "没有符合筛选条件的运行" : "还没有实验运行"}
          description={
            hasActiveFilters
              ? "尝试清除部分筛选条件，或确认日志目录中是否存在符合 TVLP 1.0 的 run.json。"
              : "在总览页添加日志目录，或运行 training-viewer open <目录>。"
          }
        />
      ) : null}

      {runs.length > 0 ? (
        <>
          <div className="table-scroll">
            <table className="data-table experiment-table">
              <thead>
                <tr>
                  <th scope="col" className="checkbox-cell">
                    <input
                      type="checkbox"
                      aria-label="选择本页全部运行"
                      checked={runs.every((run) => selected.includes(run.run_id))}
                      onChange={(event) => {
                        if (event.target.checked) {
                          setSelected(
                            Array.from(
                              new Set([...selected, ...runs.map((run) => run.run_id)]),
                            ).slice(0, MAX_COMPARE_RUNS),
                          );
                        } else {
                          const pageIds = new Set(runs.map((run) => run.run_id));
                          setSelected(selected.filter((id) => !pageIds.has(id)));
                        }
                      }}
                    />
                  </th>
                  <th scope="col" className="sortable" onClick={() => toggleSort("name")}>
                    运行名称{sortIndicator("name")}
                  </th>
                  {visibleColumns.includes("status") ? (
                    <th scope="col">状态</th>
                  ) : null}
                  {visibleColumns.includes("group") ? (
                    <th scope="col">项目 / 实验组</th>
                  ) : null}
                  {visibleColumns.includes("model") ? <th scope="col">模型</th> : null}
                  {visibleColumns.includes("dataset") ? <th scope="col">数据集</th> : null}
                  {visibleColumns.includes("seed") ? <th scope="col">随机种子</th> : null}
                  {visibleColumns.includes("primary") ? <th scope="col">关键指标</th> : null}
                  {visibleColumns.includes("updated") ? (
                    <th scope="col" className="sortable" onClick={() => toggleSort("last_updated_at")}>
                      最近更新{sortIndicator("last_updated_at")}
                    </th>
                  ) : null}
                  {visibleColumns.includes("duration") ? <th scope="col">数据时长</th> : null}
                  {visibleColumns.includes("note") ? <th scope="col">备注</th> : null}
                  {visibleColumns.includes("artifacts") ? <th scope="col">产物</th> : null}
                  {visibleColumns.includes("issues") ? <th scope="col">日志问题</th> : null}
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr
                    key={run.run_id}
                    className="clickable-row"
                    onClick={() => navigate(`/runs/${encodeURIComponent(run.run_id)}`)}
                  >
                    <td className="checkbox-cell" onClick={(event) => event.stopPropagation()}>
                      <input
                        type="checkbox"
                        aria-label={`选择运行 ${run.name}`}
                        checked={selected.includes(run.run_id)}
                        onChange={() => toggleSelection(run.run_id)}
                      />
                    </td>
                    <td>
                      <div className="run-name-cell">
                        <button
                          type="button"
                          className={`star-button ${run.favorite ? "starred" : ""}`}
                          title={run.favorite ? "取消收藏" : "收藏"}
                          aria-label={run.favorite ? "取消收藏" : "收藏"}
                          onClick={(event) => {
                            event.stopPropagation();
                            void toggleFavorite(run);
                          }}
                        >
                          {run.favorite ? "★" : "☆"}
                        </button>
                        <a
                          href={`#/runs/${encodeURIComponent(run.run_id)}`}
                          onClick={(event) => event.stopPropagation()}
                        >
                          {run.name}
                        </a>
                        <button
                          type="button"
                          className="button button-small quick-compare-button"
                          onClick={(event) => {
                            event.stopPropagation();
                            toggleSelection(run.run_id);
                          }}
                        >
                          {selected.includes(run.run_id) ? "已选对比" : "+ 对比"}
                        </button>
                      </div>
                      {run.tags.length > 0 ? (
                        <div className="tag-row">
                          {run.tags.map((tag) => (
                            <span key={tag} className="tag">
                              {tag}
                            </span>
                          ))}
                        </div>
                      ) : null}
                      <div className="muted small mono" title={run.run_id}>
                        {run.run_id}
                      </div>
                    </td>
                    {visibleColumns.includes("status") ? (
                      <td>
                        <StatusBadge status={run.status} label={run.status_label} reason={run.status_reason} />
                        <span className={`activity-badge activity-${run.activity}`} title={run.status_reason}>
                          {run.activity_label}
                        </span>
                        {!run.directory_available ? <WarnBadge label="目录不可访问" /> : null}
                        {run.conflict ? <WarnBadge label="run_id 冲突" /> : null}
                      </td>
                    ) : null}
                    {visibleColumns.includes("group") ? (
                      <td>
                        {run.project}
                        <div className="muted small">{run.experiment ?? "未分组"}</div>
                      </td>
                    ) : null}
                    {visibleColumns.includes("model") ? (
                      <td>
                        {run.model?.name ?? "—"}
                        <div className="muted small">{run.model?.architecture ?? ""}</div>
                      </td>
                    ) : null}
                    {visibleColumns.includes("dataset") ? (
                      <td>
                        {run.dataset?.name ?? "—"}
                        <div className="muted small">
                          {run.dataset?.version ? `版本 ${run.dataset.version}` : ""}
                        </div>
                      </td>
                    ) : null}
                    {visibleColumns.includes("seed") ? <td>{run.seed ?? "—"}</td> : null}
                    {visibleColumns.includes("primary") ? (
                      <td>
                        {run.primary_metric ? (
                          <span title={run.primary_metric.definition ?? ""}>
                            <div>{run.primary_metric.key}</div>
                            <div className="muted small">
                              最佳{" "}
                              {formatMetricValue(run.primary_metric.best?.value, run.primary_metric.unit)} · 最终{" "}
                              {formatMetricValue(run.primary_metric.last?.value, run.primary_metric.unit)}
                            </div>
                          </span>
                        ) : (
                          <span className="muted">—</span>
                        )}
                      </td>
                    ) : null}
                    {visibleColumns.includes("updated") ? (
                      <td title={formatDateTime(run.last_updated_at)}>
                        {formatRelativeTime(run.last_updated_at)}
                      </td>
                    ) : null}
                    {visibleColumns.includes("duration") ? (
                      <td>{formatDuration(run.duration_seconds)}</td>
                    ) : null}
                    {visibleColumns.includes("note") ? (
                      <td className="note-cell" title={run.note}>
                        {run.note || <span className="muted">—</span>}
                      </td>
                    ) : null}
                    {visibleColumns.includes("artifacts") ? (
                      <td>{formatNumber(run.artifact_count, 0)}</td>
                    ) : null}
                    {visibleColumns.includes("issues") ? (
                      <td>
                        {run.issue_count > 0 ? (
                          <span className="badge badge-warning">{run.issue_count}</span>
                        ) : (
                          <span className="muted">0</span>
                        )}
                      </td>
                    ) : null}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="pagination">
            <span className="muted small">
              共 {total} 个运行，当前显示 {offset + 1}–{Math.min(offset + PAGE_SIZE, total)}
            </span>
            <div>
              <button
                type="button"
                className="button button-small"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              >
                上一页
              </button>
              <button
                type="button"
                className="button button-small"
                disabled={offset + PAGE_SIZE >= total}
                onClick={() => setOffset(offset + PAGE_SIZE)}
              >
                下一页
              </button>
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
