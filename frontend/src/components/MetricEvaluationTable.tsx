import type { MetricCatalogItem, SeriesPayload } from "../types";
import { formatMetricValue, unitLabel } from "../utils/format";

export function MetricEvaluationTable({
  items,
  series,
}: {
  items: MetricCatalogItem[];
  series: SeriesPayload[];
}) {
  const values = new Map(series.map((entry) => [entry.key, entry]));
  return (
    <div className="evaluation-table-wrap">
      <table className="data-table evaluation-table">
        <thead>
          <tr>
            <th>指标</th>
            <th>原始键</th>
            <th>值</th>
            <th>单位</th>
            <th>点数</th>
            <th>说明</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const value = values.get(item.raw_key)?.last?.value;
            return (
              <tr key={item.raw_key}>
                <td>{item.display_name_zh}</td>
                <td><code>{item.raw_key}</code></td>
                <td>{formatMetricValue(value, item.unit)}</td>
                <td>{unitLabel(item.unit) || "未声明"}</td>
                <td>{item.point_count}</td>
                <td className="muted small">
                  {item.definition_source === "unknown" ? "定义未提供" : item.description}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
