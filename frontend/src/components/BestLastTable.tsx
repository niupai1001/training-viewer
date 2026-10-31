import type { CompareRunInfo, CompareSeries, MetricDirection, MetricPointValue } from "../types";
import { formatMetricValue, formatNumber } from "../utils/format";

function directionLabel(direction: MetricDirection | null): string {
  if (direction === "min") {
    return "越低越好";
  }
  if (direction === "max") {
    return "越高越好";
  }
  return "未声明方向";
}

function pointCell(point: MetricPointValue | null) {
  if (point === null) {
    return <span className="muted">—</span>;
  }
  return (
    <span>
      <strong>{formatNumber(point.value)}</strong>
      <span className="muted small">
        {point.global_step !== null ? ` · Step ${point.global_step}` : ""}
        {point.epoch !== null ? ` · Epoch ${point.epoch}` : ""}
      </span>
    </span>
  );
}

export function BestLastTable({
  series,
  runs,
}: {
  series: CompareSeries[];
  runs: CompareRunInfo[];
}) {
  if (series.length === 0) {
    return null;
  }
  return (
    <div className="best-last-tables">
      {series.map((metric) => {
        const values = metric.runs
          .map((run) => run.best?.value)
          .filter((value): value is number => typeof value === "number");
        const winningValue =
          metric.ranking_allowed && values.length > 0
            ? metric.direction === "min"
              ? Math.min(...values)
              : Math.max(...values)
            : null;
        return (
          <section key={metric.key} className="best-last">
            <header className="best-last-header">
              <div>
                <h3>{metric.key}</h3>
                <p className="muted small">
                  单位：{metric.unit ?? "未声明"} · {directionLabel(metric.direction)}
                  {metric.definition ? ` · 定义：${metric.definition}` : ""}
                </p>
              </div>
              <span
                className={`ranking-badge ${metric.ranking_allowed ? "ranking-ok" : "ranking-blocked"}`}
                title={
                  metric.ranking_allowed
                    ? "单位、数据集和定义一致，且指标有明确方向"
                    : "单位、数据集或定义不一致，或指标没有方向；不自动评优"
                }
              >
                {metric.ranking_allowed ? "可比较并排名" : "不可直接排名"}
              </span>
            </header>
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th scope="col">运行</th>
                    <th scope="col">最佳值</th>
                    <th scope="col">最终值</th>
                    <th scope="col">采样点数</th>
                  </tr>
                </thead>
                <tbody>
                  {metric.runs.map((run) => {
                    const runName = runs.find((item) => item.run_id === run.run_id)?.name ?? run.name;
                    const isWinner =
                      winningValue !== null && run.best?.value === winningValue && values.length > 1;
                    return (
                      <tr key={run.run_id} className={isWinner ? "winner-row" : undefined}>
                        <td>
                          <a href={`#/runs/${encodeURIComponent(run.run_id)}`}>{runName}</a>
                          {isWinner ? <span className="winner-mark"> 最优</span> : null}
                        </td>
                        <td>{pointCell(run.best)}</td>
                        <td>{pointCell(run.last)}</td>
                        <td>{formatNumber(run.total_points, 0)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {metric.warnings.length > 0 ? (
              <ul className="compact-warnings">
                {metric.warnings.map((warning, index) => (
                  <li key={`${warning.code}-${index}`} className={`warning-${warning.severity}`}>
                    {warning.message}
                  </li>
                ))}
              </ul>
            ) : null}
          </section>
        );
      })}
    </div>
  );
}

export function bestValueLabel(
  runs: CompareSeries["runs"],
  direction: MetricDirection | null,
  unit: string | null,
): string {
  const values = runs.map((run) => run.best?.value).filter((value): value is number => value !== undefined);
  if (values.length === 0 || (direction !== "min" && direction !== "max")) {
    return "—";
  }
  const value = direction === "min" ? Math.min(...values) : Math.max(...values);
  return formatMetricValue(value, unit);
}
