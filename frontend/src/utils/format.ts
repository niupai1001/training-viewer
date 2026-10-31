/** 数值、时间和状态的中文显示规则。单位不做未经声明的换算。 */

export function formatNumber(value: number | null | undefined, maximumFractionDigits = 4): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  if (!Number.isFinite(value)) {
    return String(value);
  }
  if (value !== 0 && Math.abs(value) < 0.001) {
    return value.toExponential(3);
  }
  if (Number.isInteger(value)) {
    return value.toLocaleString("zh-CN");
  }
  return value.toLocaleString("zh-CN", {
    maximumFractionDigits,
    minimumFractionDigits: 0,
  });
}

const UNIT_LABELS: Record<string, string> = {
  ratio: "比例（0–1）",
  percent: "%",
  ms: "毫秒",
  none: "",
  "1/step": "1/步",
};

export function unitLabel(unit: string | null | undefined): string {
  if (!unit) {
    return "";
  }
  return UNIT_LABELS[unit] ?? unit;
}

export function formatMetricValue(value: number | null | undefined, unit?: string | null): string {
  const label = unitLabel(unit);
  const number = formatNumber(value);
  return label ? `${number} ${label}` : number;
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return "—";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN", { hour12: false });
}

export function formatTimeOfDay(value: string | null | undefined): string {
  if (!value) {
    return "—";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleTimeString("zh-CN", { hour12: false });
}

export function formatRelativeTime(value: string | null | undefined): string {
  if (!value) {
    return "—";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  const seconds = Math.round((Date.now() - date.getTime()) / 1000);
  if (Math.abs(seconds) < 60) {
    return seconds >= 0 ? `${seconds} 秒前` : `未来 ${-seconds} 秒`;
  }
  const minutes = Math.round(seconds / 60);
  if (Math.abs(minutes) < 60) {
    return minutes >= 0 ? `${minutes} 分钟前` : `未来 ${-minutes} 分钟`;
  }
  const hours = Math.round(minutes / 60);
  if (Math.abs(hours) < 48) {
    return hours >= 0 ? `${hours} 小时前` : `未来 ${-hours} 小时`;
  }
  return formatDateTime(value);
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) {
    return "—";
  }
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const remaining = total % 60;
  if (hours > 0) {
    return `${hours} 小时 ${minutes} 分`;
  }
  if (minutes > 0) {
    return `${minutes} 分 ${remaining} 秒`;
  }
  return `${remaining} 秒`;
}

export function statusTone(status: string): "success" | "running" | "danger" | "warning" | "muted" {  switch (status) {
    case "completed":
      return "success";
    case "running":
      return "running";
    case "failed":
      return "danger";
    case "cancelled":
      return "warning";
    case "imported":
      return "muted";
    default:
      return "warning";
  }
}

export function statusLabel(status: string, fallback?: string): string {
  const labels: Record<string, string> = {
    running: "运行中",
    completed: "已完成",
    failed: "失败",
    cancelled: "已取消",
    unknown: "状态未知（可能中断）",
    imported: "已导入（无生命周期事件）",
  };
  return fallback ?? labels[status] ?? status;
}

export function axisLabel(axis: string): string {
  return (
    {
      global_step: "优化步（global_step）",
      epoch: "训练轮次（epoch）",
      timestamp: "时间",
    } as Record<string, string>
  )[axis] ?? axis;
}

export function axisShortLabel(axis: string): string {
  return (
    {
      global_step: "优化步",
      epoch: "训练轮次",
      timestamp: "时间",
    } as Record<string, string>
  )[axis] ?? axis;
}

export function formatAxisTime(seconds: number): string {
  const date = new Date(seconds * 1000);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return date.toLocaleTimeString("zh-CN", { hour12: false });
}

export function formatAxisTimestampLong(seconds: number): string {
  const date = new Date(seconds * 1000);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return date.toLocaleString("zh-CN", { hour12: false });
}

export function roleLabel(role: string | null | undefined): string {
  if (!role) {
    return "文件";
  }
  return (
    {
      input: "原图",
      ground_truth: "真实标签",
      prediction: "预测结果",
      probability: "概率图",
      confusion_matrix: "混淆矩阵",
    } as Record<string, string>
  )[role] ?? role;
}

export function eventLabel(kind: string, status?: string | null): string {
  if (kind === "artifact") {
    return "生成实验产物";
  }
  if (kind === "heartbeat") {
    return "心跳";
  }
  return (
    {
      started: "训练启动",
      resumed: "恢复训练",
      completed: "训练完成",
      failed: "训练失败",
      cancelled: "训练取消",
    } as Record<string, string>
  )[status ?? ""] ?? "生命周期事件";
}

export function shortRunId(runId: string): string {
  return runId.length > 12 ? `${runId.slice(0, 8)}…` : runId;
}

export function truncate(value: string, length = 80): string {
  return value.length > length ? `${value.slice(0, length)}…` : value;
}

export function formatFileSize(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) {
    return "—";
  }
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KiB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`;
}

export function directionLabel(direction: string | null | undefined): string {
  if (direction === "min") {
    return "越低越好（min）";
  }
  if (direction === "max") {
    return "越高越好（max）";
  }
  if (direction === "none") {
    return "无优化方向（none）";
  }
  return "未声明方向";
}
