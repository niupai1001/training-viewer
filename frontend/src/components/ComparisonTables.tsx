import { useState } from "react";
import type { HyperparameterRow } from "../types";
import { statusLabel } from "../utils/format";

function formatValue(value: unknown): string {
  if (value === undefined) {
    return "—";
  }
  if (value === null) {
    return "null";
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
}

export function HyperparameterDiffTable({
  rows,
  runs,
}: {
  rows: HyperparameterRow[];
  runs: { run_id: string; name: string }[];
}) {
  const [onlyDifferences, setOnlyDifferences] = useState(true);
  const [search, setSearch] = useState("");
  const visibleRows = rows.filter((row) => {
    if (onlyDifferences && !row.different) {
      return false;
    }
    return row.path.toLowerCase().includes(search.toLowerCase());
  });

  return (
    <div className="hyperparameter-table">
      <div className="toolbar">
        <label className="inline-check">
          <input
            type="checkbox"
            checked={onlyDifferences}
            onChange={(event) => setOnlyDifferences(event.target.checked)}
          />
          只显示有差异的配置项
        </label>
        <input
          type="search"
          value={search}
          placeholder="搜索配置项路径"
          aria-label="搜索配置项路径"
          onChange={(event) => setSearch(event.target.value)}
        />
        <span className="muted small">
          共 {rows.length} 项，差异 {rows.filter((row) => row.different).length} 项
        </span>
      </div>
      {visibleRows.length === 0 ? (
        <p className="muted">没有符合条件的配置项。</p>
      ) : (
        <div className="table-scroll">
          <table className="data-table config-diff-table">
            <thead>
              <tr>
                <th scope="col">配置项</th>
                {runs.map((run) => (
                  <th key={run.run_id} scope="col" title={run.run_id}>
                    {run.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((row) => (
                <tr key={row.path} className={row.different ? "different-row" : undefined}>
                  <th scope="row" className="config-path">
                    {row.path}
                  </th>
                  {runs.map((run) => (
                    <td key={run.run_id}>{formatValue(row.values[run.run_id])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="muted small">
        配置项来自 run.json 的 config 字段。数值不同不代表实验结论不同，请结合数据集、代码版本和随机种子判断。
      </p>
    </div>
  );
}

export function RunFieldsTable({
  fields,
  runs,
}: {
  fields: Record<string, Record<string, unknown>>;
  runs: { run_id: string; name: string }[];
}) {
  const labels: Record<string, string> = {
    project: "项目",
    experiment: "实验组",
    task: "任务",
    model: "模型",
    dataset: "数据集",
    seed: "随机种子",
    status: "状态",
  };
  const fieldNames = Object.keys(fields);
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            <th scope="col">字段</th>
            {runs.map((run) => (
              <th key={run.run_id} scope="col" title={run.run_id}>
                {run.name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {fieldNames.map((field) => (
            <tr key={field}>
              <th scope="row">{labels[field] ?? field}</th>
              {runs.map((run) => {
                const value = fields[field]?.[run.run_id];
                return <td key={run.run_id}>{formatFieldValue(field, value)}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatFieldValue(field: string, value: unknown): string {
  if (value === undefined || value === null) {
    return "—";
  }
  if (field === "status" && typeof value === "string") {
    return statusLabel(value);
  }
  if (field === "model" || field === "dataset") {
    if (typeof value === "object") {
      const record = value as Record<string, unknown>;
      const parts = [record.name, record.architecture, record.version]
        .filter((part) => typeof part === "string" && part)
        .join(" · ");
      return parts || JSON.stringify(value);
    }
  }
  return typeof value === "string" ? value : JSON.stringify(value);
}
