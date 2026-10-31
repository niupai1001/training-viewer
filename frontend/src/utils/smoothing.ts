import type { SeriesPoint, SmoothingMethod } from "../types";

/**
 * 平滑只影响显示，不改变后端计算的 Best/Last。
 * 会话边界由调用方先拆分，避免把断点续训的前后段连成一条曲线。
 */
export function smoothPoints(
  points: SeriesPoint[],
  method: SmoothingMethod,
  windowSize: number,
): SeriesPoint[] {
  if (method === "none" || windowSize < 2 || points.length < 2) {
    return points;
  }
  if (method === "moving_average") {
    return points.map((point, index) => {
      const start = Math.max(0, index - windowSize + 1);
      let sum = 0;
      for (let cursor = start; cursor <= index; cursor += 1) {
        sum += points[cursor].value;
      }
      return { ...point, value: sum / (index - start + 1) };
    });
  }
  const alpha = 2 / (windowSize + 1);
  let previous = points[0].value;
  return points.map((point, index) => {
    if (index > 0) {
      previous = alpha * point.value + (1 - alpha) * previous;
    }
    return { ...point, value: previous };
  });
}

/** 按 session_id 的连续区段拆分；相同会话内保留原始顺序。 */
export function splitBySession(points: SeriesPoint[]): { sessionId: string | null; points: SeriesPoint[] }[] {
  if (points.length === 0) {
    return [];
  }
  const groups: { sessionId: string | null; points: SeriesPoint[] }[] = [];
  for (const point of points) {
    const last = groups[groups.length - 1];
    if (!last || last.sessionId !== point.session_id) {
      groups.push({ sessionId: point.session_id, points: [point] });
    } else {
      last.points.push(point);
    }
  }
  return groups;
}

export function smoothingLabel(method: SmoothingMethod): string {
  return (
    {
      none: "不平滑",
      moving_average: "移动平均",
      ema: "指数移动平均",
    } as Record<SmoothingMethod, string>
  )[method];
}
