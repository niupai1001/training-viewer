/** 与后端 REST 响应一致的 TypeScript 类型。字段名保持协议原始英文，界面显示中文。 */

export type MetricDirection = "min" | "max" | "none";
export type Severity = "info" | "warning" | "error";

export interface WarningItem {
  code: string;
  severity: Severity;
  message: string;
}

export interface MetricDefinition {
  display_name?: string;
  direction?: MetricDirection;
  unit?: string;
  description?: string;
  comparison_key?: string;
  aggregation?: string;
  definition?: string;
}

export interface RunModel {
  name?: string;
  architecture?: string;
  version?: string;
  [key: string]: unknown;
}

export interface RunDataset {
  name?: string;
  version?: string;
  split_definition?: string;
  fingerprint?: string;
  [key: string]: unknown;
}

export interface MetricPointValue {
  value: number;
  global_step: number | null;
  epoch: number | null;
  timestamp: string | null;
}

export interface MetricKey {
  key: string;
  phase: string;
  metric_name: string;
  display_name: string;
  definition_key: string | null;
  unit: string | null;
  direction: MetricDirection | null;
  aggregation: string | null;
  definition: string | null;
  comparison_key: string | null;
  point_count: number;
  min_value: number | null;
  max_value: number | null;
  first_timestamp: string | null;
  last_timestamp: string | null;
  step_point_count: number;
  epoch_point_count: number;
  time_point_count: number;
  session_count: number;
  best: MetricPointValue | null;
  last: MetricPointValue | null;
}

export interface PrimaryMetric {
  key: string;
  phase: string;
  metric_name: string;
  display_name: string;
  unit: string | null;
  direction: MetricDirection | null;
  definition: string | null;
  best: MetricPointValue | null;
  last: MetricPointValue | null;
}

export interface RunConflict {
  conflicting_run_dir: string;
}

export interface RunSummary {
  run_id: string;
  name: string;
  project: string;
  experiment: string | null;
  task: string | null;
  status: string;
  status_label: string;
  status_reason: string;
  activity: string;
  activity_label: string;
  created_at: string | null;
  last_updated_at: string | null;
  started_at: string | null;
  last_metric_at: string | null;
  duration_seconds: number | null;
  model: RunModel | null;
  dataset: RunDataset | null;
  tags: string[];
  seed: number | null;
  source_kind: string;
  adapter_id: string;
  run_directory: string;
  root_path: string;
  metadata_synthetic: boolean;
  directory_available: boolean;
  note: string;
  favorite: boolean;
  artifact_count: number;
  issue_count: number;
  conflict: RunConflict | null;
  primary_metric: PrimaryMetric | null;
}

export interface SessionInfo {
  session_id: string | null;
  first_seen: string | null;
  last_seen: string | null;
  point_count: number;
  event_count?: number;
}

export interface DataSourceInfo {
  file_path: string;
  relative_path: string;
  file_kind: string;
  offset: number;
  size: number;
  updated_at: string;
  health: string;
}

export interface IngestionIssue {
  file_path: string;
  line_number: number;
  message: string;
  severity: Severity;
  created_at?: string;
}

export interface StepWarning {
  session_id: string | null;
  previous_step: number;
  global_step: number;
  timestamp: string | null;
  message: string;
}

export interface ArtifactTagCount {
  tag: string;
  artifact_type: string;
  count: number;
}

export interface RunMetadata {
  schema_version: string;
  run_id: string;
  project: string;
  experiment?: string;
  name: string;
  created_at: string;
  task?: string;
  model?: RunModel;
  dataset?: RunDataset;
  config?: Record<string, unknown>;
  source?: Record<string, unknown>;
  tags?: string[];
  metric_definitions?: Record<string, MetricDefinition>;
  extensions?: Record<string, unknown>;
}

export interface RunDetail {
  run_id: string;
  name: string;
  project: string;
  experiment: string | null;
  task: string | null;
  status: string;
  status_label: string;
  status_reason: string;
  activity: string;
  activity_label: string;
  created_at: string | null;
  last_updated_at: string | null;
  started_at: string | null;
  last_metric_at: string | null;
  duration_seconds: number | null;
  source_kind: string;
  adapter_id: string;
  run_directory: string;
  root_path: string;
  metadata_synthetic: boolean;
  directory_available: boolean;
  note: string;
  favorite: boolean;
  conflict: RunConflict | null;
  metadata: RunMetadata;
  schema_version: string;
  model: RunModel | null;
  dataset: RunDataset | null;
  config: Record<string, unknown>;
  source: Record<string, unknown>;
  tags: string[];
  metric_definitions: Record<string, MetricDefinition>;
  extensions: Record<string, unknown>;
  counts: {
    metric_point_count: number;
    artifact_count: number;
    missing_artifact_count: number;
    event_count: number;
    issue_count: number;
  };
  sessions: SessionInfo[];
  metric_keys: MetricKey[];
  artifact_tags: ArtifactTagCount[];
  data_sources: DataSourceInfo[];
  issues: IngestionIssue[];
  step_warnings: StepWarning[];
  warnings: WarningItem[];
}

export interface SeriesPoint {
  x: number | null;
  value: number;
  global_step: number | null;
  epoch: number | null;
  timestamp: string | null;
  session_id: string | null;
}

export interface SeriesPayload {
  key: string;
  phase: string;
  metric_name: string;
  display_name: string;
  unit: string | null;
  direction: MetricDirection | null;
  definition: string | null;
  definition_key: string | null;
  axis: Axis;
  points: SeriesPoint[];
  total_points: number;
  returned_points: number;
  downsampled: boolean;
  best: MetricPointValue | null;
  last: MetricPointValue | null;
  warnings: WarningItem[];
}

export interface MetricCatalogItem {
  raw_key: string;
  phase: string;
  metric_name: string;
  display_name: string;
  display_name_zh: string;
  display_name_en: string;
  category: string;
  semantic_group: string;
  description: string;
  definition: string | null;
  definition_source: string;
  source: string;
  confidence: string;
  unit: string | null;
  direction: string;
  aggregation: string | null;
  comparison_key: string | null;
  is_primary: boolean;
  default_visibility: boolean;
  role: string;
  group_path: string[];
  point_count: number;
  distinct_x_count: number;
  available_axes: Axis[];
  value_kind: "continuous" | "single_point" | "no_data";
  suggested_view: "line" | "evaluation_table" | "raw";
}

export interface MetricCatalogResponse {
  run_id: string;
  items: MetricCatalogItem[];
  total: number;
  limit: number;
  cursor: number;
  next_cursor: number | null;
  facets: {
    category: Record<string, number>;
    semantic_group: Record<string, number>;
    phase: Record<string, number>;
    value_kind: Record<string, number>;
  };
}

export interface MetricQueryResult {
  run_id: string;
  run_name: string;
  axis: AxisRequest;
  series: SeriesPayload[];
  warnings: WarningItem[];
}

export type Axis = "global_step" | "epoch" | "timestamp";
export type AxisRequest = Axis | "auto";
export type SmoothingMethod = "none" | "moving_average" | "ema";

export interface CompareRunSeries {
  run_id: string;
  name: string;
  axis: Axis;
  points: SeriesPoint[];
  total_points: number;
  returned_points: number;
  downsampled: boolean;
  best: MetricPointValue | null;
  last: MetricPointValue | null;
  warnings: WarningItem[];
}

export interface CompareSeries {
  key: string;
  phase: string | null;
  metric_name: string;
  display_name: string;
  unit: string | null;
  direction: MetricDirection | null;
  definition: string | null;
  axis: Axis;
  runs: CompareRunSeries[];
  warnings: WarningItem[];
  ranking_allowed: boolean;
}

export interface CompareRunInfo {
  run_id: string;
  name: string;
  project: string;
  experiment: string | null;
  status: string;
  status_label: string;
  model: RunModel | null;
  dataset: RunDataset | null;
  tags: string[];
}

export interface HyperparameterRow {
  path: string;
  values: Record<string, unknown>;
  different: boolean;
}

export interface CompareResult {
  axis: AxisRequest;
  x_min?: number | null;
  x_max?: number | null;
  run_ids: string[];
  series: CompareSeries[];
  runs: CompareRunInfo[];
  hyperparameters: { rows: HyperparameterRow[] };
  run_fields: Record<string, Record<string, unknown>>;
  warnings: WarningItem[];
}

export interface Artifact {
  id: number;
  run_id: string;
  path: string;
  artifact_type: string;
  tag: string;
  phase: string | null;
  global_step: number | null;
  epoch: number | null;
  group_id: string | null;
  sample_id: string | null;
  role: string | null;
  mime_type: string | null;
  metadata: Record<string, unknown>;
  timestamp: string | null;
  session_id: string | null;
  exists_on_disk: boolean;
  size: number | null;
  content_url: string;
  download_url: string;
}

export interface ArtifactGroup {
  group_id: string;
  sample_id: string | null;
  epoch: number | null;
  phase: string | null;
  tag: string;
  roles: Record<string, Artifact[]>;
}

export interface ProjectExperiment {
  name: string | null;
  run_count: number;
  running_count: number;
  last_updated_at: string | null;
}

export interface ProjectNode {
  name: string;
  run_count: number;
  running_count: number;
  experiments: ProjectExperiment[];
}

export interface RootDirectory {
  id: number;
  path: string;
  added_at: string;
}

export interface SourceInventoryRow {
  source_path: string | null;
  parser: string;
  run_id: string;
  raw_run_identifier: string;
  logical_run_id: string;
  merged: boolean;
  confidence: string;
  project: string;
  name: string;
  point_count: number;
  bytes_read?: number;
  file_size?: number;
}

export interface ResultCandidate {
  path: string;
  role_guess: string | null;
  sample_id: string;
  epoch: number | null;
  confidence: string;
  requires_confirmation: boolean;
  note: string;
  content_url: string;
}

export interface ProjectTree {
  projects: ProjectNode[];
  roots: RootDirectory[];
}

export interface Diagnostics {
  generated_at: string;
  totals: {
    run_count: number;
    running_count: number | null;
    unknown_count: number | null;
  };
  scan_issues: {
    file_path: string;
    line_number: number;
    message: string;
    severity: Severity;
    created_at: string;
  }[];
  conflicts: {
    run_id: string;
    kept_run_dir: string;
    conflicting_run_dir: string;
    detected_at: string;
  }[];
  problem_runs: {
    run_id: string;
    name: string;
    status: string;
    status_reason: string;
    issue_count: number;
    missing_artifact_count: number;
  }[];
}

export interface SavedView {
  id: number;
  name: string;
  view_kind: string;
  payload: {
    run_ids?: string[];
    series?: string[];
    axis?: AxisRequest;
    smoothing?: SmoothingMethod;
    smoothing_window?: number;
    scale?: string;
    show_raw?: boolean;
  };
  created_at: string;
}

export interface Meta {
  application: string;
  version: string;
  tvlp_schema_version: string;
  source_kinds: Record<string, string>;
  status_labels: Record<string, string>;
  adapters: { adapter_id: string; display_name: string; available: boolean }[];
  export_formats: string[];
  axes: Axis[];
  smoothing_methods: SmoothingMethod[];
}

export interface Facets {
  models: string[];
  datasets: string[];
  tasks: string[];
  tags: string[];
}

export interface TimelineEvent {
  kind: "lifecycle" | "heartbeat" | "artifact";
  status: string | null;
  timestamp: string | null;
  session_id: string | null;
  global_step: number | null;
  epoch: number | null;
  message: string | null;
  tag: string | null;
  path: string | null;
  role: string | null;
  sample_id: string | null;
}

export interface TimelineResult {
  run_id: string;
  events: TimelineEvent[];
}

export interface TablePreview {
  kind: string;
  columns: string[];
  rows: string[][];
  truncated: boolean;
}

export interface RunListResponse {
  runs: RunSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface RunListQuery {
  project?: string;
  experiment?: string;
  status?: string;
  q?: string;
  tag?: string;
  task?: string;
  model?: string;
  dataset?: string;
  favorite?: boolean;
  sort?: string;
  limit?: number;
  offset?: number;
}

export interface CompareRequest {
  run_ids: string[];
  series: string[];
  axis: AxisRequest;
  max_points?: number;
  x_min?: number;
  x_max?: number;
}
