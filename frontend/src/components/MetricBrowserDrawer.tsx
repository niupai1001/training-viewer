import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { MetricCatalogItem, MetricCatalogResponse } from "../types";
import { formatNumber, unitLabel } from "../utils/format";

const GROUP_LABELS: Record<string, string> = {
  training_trend: "训练与验证趋势",
  performance: "资源与吞吐",
  evaluation: "单次评估及组合结果",
  other: "其他未分类字段",
};
const CATEGORY_TABS = [
  ["all", "全部"],
  ["training_trend", "训练/验证"],
  ["performance", "资源与吞吐"],
  ["evaluation", "单次评估"],
  ["other", "未分类"],
] as const;
const PAGE_SIZE = 40;

export interface ChartTarget {
  id: string;
  title: string;
  unit: string | null;
}

export function MetricBrowserDrawer({
  runId,
  open,
  charts,
  onClose,
  onAdd,
}: {
  runId: string;
  open: boolean;
  charts: ChartTarget[];
  onClose: () => void;
  onAdd: (items: MetricCatalogItem[], targetId: string | null) => string | null;
}) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const [phase, setPhase] = useState("all");
  const [data, setData] = useState<MetricCatalogResponse | null>(null);
  const [items, setItems] = useState<MetricCatalogItem[]>([]);
  const [selected, setSelected] = useState<Map<string, MetricCatalogItem>>(new Map());
  const [targetId, setTargetId] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const searchRef = useRef<HTMLInputElement | null>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    if (!open) return;
    setSelected(new Map());
    setTargetId("");
    setMessage(null);
    setTimeout(() => searchRef.current?.focus(), 50);
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeRef.current();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, runId]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const result = await api.metricCatalog(runId, {
          query: query.trim() || undefined,
          group: category === "all" ? undefined : category,
          phase: phase === "all" ? undefined : phase,
          limit: PAGE_SIZE,
          cursor: 0,
        });
        if (!cancelled) {
          setData(result);
          setItems(result.items);
        }
      } catch (error) {
        if (!cancelled) setMessage(error instanceof Error ? error.message : String(error));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 180);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [open, runId, query, category, phase]);

  async function loadMore() {
    if (!data?.next_cursor) return;
    setLoading(true);
    try {
      const result = await api.metricCatalog(runId, {
        query: query.trim() || undefined,
        group: category === "all" ? undefined : category,
        phase: phase === "all" ? undefined : phase,
        limit: PAGE_SIZE,
        cursor: data.next_cursor,
      });
      setData(result);
      setItems((current) => [...current, ...result.items]);
    } finally {
      setLoading(false);
    }
  }

  function toggle(item: MetricCatalogItem) {
    setSelected((current) => {
      const next = new Map(current);
      if (next.has(item.raw_key)) next.delete(item.raw_key);
      else next.set(item.raw_key, item);
      return next;
    });
  }

  if (!open) return null;

  const selectedItems = Array.from(selected.values());
  const groups = new Map<string, MetricCatalogItem[]>();
  for (const item of items) {
    const list = groups.get(item.semantic_group) ?? [];
    list.push(item);
    groups.set(item.semantic_group, list);
  }
  const phases = Object.keys(data?.facets.phase ?? {}).sort();

  return (
    <div className="drawer-backdrop" role="presentation" onMouseDown={onClose}>
      <aside
        className="metric-drawer"
        role="dialog"
        aria-modal="true"
        aria-label="添加图表或指标"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="metric-drawer-header">
          <div>
            <h2>添加图表 / 指标</h2>
            <p className="muted small">
              共 {data?.total ?? 0} 个字段；连续曲线与单次评估分开，未知含义不猜测。
            </p>
          </div>
          <button type="button" className="button" onClick={onClose}>关闭</button>
        </header>

        <div className="metric-drawer-filters">
          <input
            ref={searchRef}
            type="search"
            value={query}
            placeholder="搜索中文名、原始键、说明、路径片段"
            aria-label="搜索指标"
            onChange={(event) => setQuery(event.target.value)}
          />
          <div className="metric-category-tabs" role="tablist" aria-label="指标类别">
            {CATEGORY_TABS.map(([key, label]) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={category === key}
                className={category === key ? "active" : ""}
                onClick={() => setCategory(key)}
              >
                {label}
              </button>
            ))}
          </div>
          <label className="metric-phase-filter">
            阶段
            <select value={phase} onChange={(event) => setPhase(event.target.value)}>
              <option value="all">全部</option>
              {phases.map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </label>
        </div>

        {message ? <p className="notice notice-warning">{message}</p> : null}
        <div className="metric-drawer-list">
          {loading && items.length === 0 ? <p className="muted">正在读取指标目录…</p> : null}
          {!loading && items.length === 0 ? <p className="muted">没有匹配的指标。</p> : null}
          {Array.from(groups.entries()).map(([group, groupItems]) => (
            <section key={group} className="metric-group">
              <h3>{GROUP_LABELS[group] ?? group} ({groupItems.length})</h3>
              {groupItems.map((item) => {
                const checked = selected.has(item.raw_key);
                return (
                  <label key={item.raw_key} className={`metric-row ${checked ? "selected" : ""}`}>
                    <input type="checkbox" checked={checked} onChange={() => toggle(item)} />
                    <span className="metric-row-main">
                      <span className="metric-row-title">
                        {item.display_name_zh}
                        {item.value_kind === "single_point" ? <em>单次结果</em> : null}
                        {item.definition_source === "unknown" ? <em>定义未提供</em> : null}
                      </span>
                      <code>{item.raw_key}</code>
                      <span className="muted small">
                        {formatNumber(item.point_count, 0)} 点 · {item.distinct_x_count} 个有效 X ·{" "}
                        {item.available_axes.length ? item.available_axes.map(axisLabel).join("/") : "无横轴"} ·{" "}
                        {unitLabel(item.unit) || "单位未声明"}
                      </span>
                    </span>
                  </label>
                );
              })}
            </section>
          ))}
          {data?.next_cursor != null ? (
            <button type="button" className="button" disabled={loading} onClick={loadMore}>
              加载更多（已显示 {items.length} / {data.total}）
            </button>
          ) : null}
        </div>

        <footer className="metric-drawer-footer">
          <span>已选择 {selectedItems.length} 项</span>
          {charts.length > 0 ? (
            <select value={targetId} onChange={(event) => setTargetId(event.target.value)}>
              <option value="">新建图表</option>
              {charts.map((chart) => <option key={chart.id} value={chart.id}>{chart.title}</option>)}
            </select>
          ) : null}
          <button
            type="button"
            className="button button-primary"
            disabled={selectedItems.length === 0}
            onClick={() => {
              const error = onAdd(selectedItems, targetId || null);
              if (error === null) {
                setSelected(new Map());
                setMessage(null);
                onClose();
              } else {
                setMessage(error);
              }
            }}
          >
            {targetId ? "加入当前图" : "添加为新图"}
          </button>
        </footer>
      </aside>
    </div>
  );
}

function axisLabel(axis: string): string {
  return { global_step: "Step", epoch: "Epoch", timestamp: "时间" }[axis] ?? axis;
}
