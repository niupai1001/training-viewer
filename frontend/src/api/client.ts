import type {
  Artifact,
  ArtifactGroup,
  AxisRequest,
  CompareRequest,
  CompareResult,
  Diagnostics,
  Facets,
  Meta,
  MetricQueryResult,
  MetricKey,
  ProjectTree,
  ResultCandidate,
  RootDirectory,
  RunDetail,
  RunListQuery,
  RunListResponse,
  SavedView,
  SmoothingMethod,
  SourceInventoryRow,
  TablePreview,
  TimelineResult,
} from "../types";
import { downloadBlob } from "../utils/download";

const API_BASE = "/api/v1";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    let detail = response.statusText || `HTTP ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) {
        detail = body.detail;
      }
    } catch {
      // 响应不是 JSON 时保留状态文本。
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

function queryString(params: Record<string, string | number | boolean | undefined | string[]>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === "") {
      continue;
    }
    if (Array.isArray(value)) {
      for (const item of value) {
        search.append(key, item);
      }
    } else {
      search.set(key, String(value));
    }
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export interface ExportOptions {
  series: string[];
  axis: AxisRequest;
  format: "csv" | "json";
  maxPoints?: number;
  smoothingMethod?: SmoothingMethod;
  smoothingWindow?: number;
  scale?: string;
}

export const api = {
  meta: () => request<Meta>("/meta"),
  health: () => request<{ application: string; version: number; last_sync_at: string | null }>("/health"),
  projects: () => request<ProjectTree>("/projects"),
  facets: () => request<Facets>("/facets"),
  runs: (query: RunListQuery = {}) => {
    const params: Record<string, string | number | boolean | undefined> = {
      project: query.project,
      experiment: query.experiment,
      status: query.status,
      q: query.q,
      tag: query.tag,
      task: query.task,
      model: query.model,
      dataset: query.dataset,
      favorite: query.favorite,
      sort: query.sort,
      limit: query.limit,
      offset: query.offset,
    };
    return request<RunListResponse>(`/runs${queryString(params)}`);
  },
  run: (runId: string) => request<RunDetail>(`/runs/${encodeURIComponent(runId)}`),
  timeline: (runId: string) => request<TimelineResult>(`/runs/${encodeURIComponent(runId)}/timeline`),
  metricKeys: (runId: string) =>
    request<{ run_id: string; metric_keys: MetricKey[] }>(
      `/runs/${encodeURIComponent(runId)}/metric-keys`,
    ),
  metrics: (
    runId: string,
    series: string[],
    axis: AxisRequest,
    maxPoints = 2000,
    xMin?: number,
    xMax?: number,
  ) =>
    request<MetricQueryResult>(
      `/runs/${encodeURIComponent(runId)}/metrics${queryString({
        series,
        axis,
        max_points: maxPoints,
        x_min: xMin,
        x_max: xMax,
      })}`,
    ),
  compare: (payload: CompareRequest) =>
    request<CompareResult>("/compare/query", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  artifacts: (
    runId: string,
    filters: { tag?: string; sampleId?: string; epoch?: number; groupId?: string } = {},
  ) =>
    request<{ run_id: string; artifacts: Artifact[] }>(
      `/runs/${encodeURIComponent(runId)}/artifacts${queryString({
        tag: filters.tag,
        sample_id: filters.sampleId,
        epoch: filters.epoch,
        group_id: filters.groupId,
      })}`,
    ),
  artifactGroups: (runId: string, tag?: string) =>
    request<{ run_id: string; groups: ArtifactGroup[] }>(
      `/runs/${encodeURIComponent(runId)}/artifact-groups${queryString({ tag })}`,
    ),
  tablePreview: (artifactId: number) =>
    request<TablePreview>(`/artifacts/${artifactId}/table-preview`),
  diagnostics: () => request<Diagnostics>("/diagnostics"),
  sourceInventory: () =>
    request<{ sources: SourceInventoryRow[] }>("/audit/sources"),
  logicalOverrides: () =>
    request<{
      overrides: {
        logical_run_id: string;
        name: string;
        files: string[];
        reason: string;
        created_at: string;
      }[];
    }>("/logical-runs/overrides"),
  saveLogicalOverride: (payload: {
    logical_run_id: string;
    name: string;
    files: string[];
    reason: string;
  }) =>
    request("/logical-runs/overrides", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  deleteLogicalOverride: (logicalRunId: string) =>
    request(`/logical-runs/overrides/${encodeURIComponent(logicalRunId)}`, {
      method: "DELETE",
    }),
  resultCandidates: (runId: string) =>
    request<{ run_id: string; candidates: ResultCandidate[]; note: string }>(
      `/runs/${encodeURIComponent(runId)}/result-candidates`,
    ),
  roots: () => request<{ roots: RootDirectory[] }>("/roots"),
  selectRootDirectory: () => request<{ path: string }>("/roots/select", { method: "POST" }),
  addRoot: (path: string) =>
    request<RootDirectory>("/roots", {
      method: "POST",
      body: JSON.stringify({ path }),
    }),
  removeRoot: (rootId: number) =>
    request<{ removed: boolean }>(`/roots/${rootId}`, { method: "DELETE" }),
  rescan: () => request<{ version: number; run_count: number }>("/rescan", { method: "POST" }),
  updateAnnotation: (runId: string, patch: { note?: string; favorite?: boolean }) =>
    request<{ note: string; favorite: boolean }>(
      `/runs/${encodeURIComponent(runId)}/annotation`,
      { method: "PUT", body: JSON.stringify(patch) },
    ),
  savedViews: () => request<{ saved_views: SavedView[] }>("/saved-views"),
  savedView: (viewId: number) => request<SavedView>(`/saved-views/${viewId}`),
  createSavedView: (payload: { name: string; view_kind: string; payload: Record<string, unknown> }) =>
    request<SavedView>("/saved-views", { method: "POST", body: JSON.stringify(payload) }),
  deleteSavedView: (viewId: number) =>
    request<{ removed: boolean }>(`/saved-views/${viewId}`, { method: "DELETE" }),
};

export function runExportUrl(runId: string, options: ExportOptions): string {
  const search = new URLSearchParams();
  for (const key of options.series) {
    search.append("series", key);
  }
  search.set("axis", options.axis);
  search.set("format", options.format);
  search.set("max_points", String(options.maxPoints ?? 1500));
  if (options.smoothingMethod) {
    search.set("smoothing_method", options.smoothingMethod);
  }
  if (options.smoothingWindow) {
    search.set("smoothing_window", String(options.smoothingWindow));
  }
  if (options.scale) {
    search.set("scale", options.scale);
  }
  return `${API_BASE}/runs/${encodeURIComponent(runId)}/metrics/export?${search.toString()}`;
}

export function downloadCompareExport(
  payload: CompareRequest,
  format: "csv" | "json",
  smoothing?: { method: SmoothingMethod; window: number; scale: string },
): Promise<void> {
  return (async () => {
    const response = await fetch(`${API_BASE}/compare/export`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...payload,
        format,
        smoothing_method: smoothing?.method ?? "none",
        smoothing_window: smoothing?.window ?? 0,
        scale: smoothing?.scale ?? "linear",
      }),
    });
    if (!response.ok) {
      let detail = `HTTP ${response.status}`;
      try {
        const body = (await response.json()) as { detail?: string };
        if (body.detail) {
          detail = body.detail;
        }
      } catch {
        // 保持状态码信息。
      }
      throw new ApiError(response.status, detail);
    }
    const blob = await response.blob();
    const disposition = response.headers.get("content-disposition") ?? "";
    const match = /filename="?([^";]+)"?/.exec(disposition);
    const fallback = `training-viewer_comparison.${format}`;
    downloadBlob(blob, match?.[1] ?? fallback);
  })();
}
