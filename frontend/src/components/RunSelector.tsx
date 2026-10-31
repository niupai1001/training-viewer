import { useMemo, useState } from "react";
import type { RunSummary } from "../types";
import { StatusBadge } from "./Common";

export function RunSelector({
  runs,
  selectedIds,
  onChange,
  maxSelected = 12,
}: {
  runs: RunSummary[];
  selectedIds: string[];
  onChange: (ids: string[]) => void;
  maxSelected?: number;
}) {
  const [search, setSearch] = useState("");
  const grouped = useMemo(() => {
    const groups = new Map<string, Map<string, RunSummary[]>>();
    for (const run of runs) {
      const project = run.project || "未命名项目";
      const experiment = run.experiment || "未分组";
      if (!groups.has(project)) {
        groups.set(project, new Map());
      }
      const experiments = groups.get(project)!;
      const list = experiments.get(experiment) ?? [];
      list.push(run);
      experiments.set(experiment, list);
    }
    return groups;
  }, [runs]);

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) {
      return grouped;
    }
    const result = new Map<string, Map<string, RunSummary[]>>();
    for (const [project, experiments] of grouped) {
      for (const [experiment, list] of experiments) {
        const matches = list.filter(
          (run) =>
            run.name.toLowerCase().includes(term) ||
            run.run_id.toLowerCase().includes(term) ||
            project.toLowerCase().includes(term) ||
            experiment.toLowerCase().includes(term),
        );
        if (matches.length > 0) {
          if (!result.has(project)) {
            result.set(project, new Map());
          }
          result.get(project)!.set(experiment, matches);
        }
      }
    }
    return result;
  }, [grouped, search]);

  function toggle(runId: string) {
    if (selectedIds.includes(runId)) {
      onChange(selectedIds.filter((id) => id !== runId));
      return;
    }
    if (selectedIds.length >= maxSelected) {
      return;
    }
    onChange([...selectedIds, runId]);
  }

  return (
    <div className="run-selector">
      <div className="run-selector-header">
        <input
          type="search"
          value={search}
          placeholder="搜索运行、项目或实验组"
          aria-label="搜索运行"
          onChange={(event) => setSearch(event.target.value)}
        />
        <span className="muted small">
          已选 {selectedIds.length} / 最多 {maxSelected}
        </span>
        {selectedIds.length > 0 ? (
          <button type="button" className="button button-small" onClick={() => onChange([])}>
            清空
          </button>
        ) : null}
      </div>
      <div className="run-selector-list">
        {filtered.size === 0 ? <p className="muted">没有匹配的运行。</p> : null}
        {Array.from(filtered.entries()).map(([project, experiments]) => (
          <section key={project} className="run-selector-project">
            <h3>
              <a href={`#/runs?${new URLSearchParams({ project }).toString()}`}>{project}</a>
            </h3>
            {Array.from(experiments.entries()).map(([experiment, list]) => (
              <div key={`${project}/${experiment}`} className="run-selector-experiment">
                <h4>
                  <a
                    href={`#/runs?${new URLSearchParams({
                      project,
                      ...(experiment === "未分组" ? {} : { experiment }),
                    }).toString()}`}
                  >
                    {experiment}
                  </a>
                </h4>
                {list.map((run) => {
                  const checked = selectedIds.includes(run.run_id);
                  const disabled = !checked && selectedIds.length >= maxSelected;
                  return (
                    <label
                      key={run.run_id}
                      className={`run-selector-item ${checked ? "run-selector-checked" : ""}`}
                      title={run.status_reason}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={disabled}
                        onChange={() => toggle(run.run_id)}
                      />
                      <span
                        className="run-selector-name"
                        role="button"
                        tabIndex={0}
                        title="查看此实验"
                        onClick={(event) => {
                          event.preventDefault();
                          event.stopPropagation();
                          onChange([run.run_id]);
                        }}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            onChange([run.run_id]);
                          }
                        }}
                      >
                        {run.name}
                      </span>
                      <StatusBadge status={run.status} label={run.status_label} reason={run.status_reason} />
                      {run.primary_metric?.last ? (
                        <span className="run-selector-value">
                          {run.primary_metric.key}: {run.primary_metric.last.value.toPrecision(4)}
                        </span>
                      ) : null}
                    </label>
                  );
                })}
              </div>
            ))}
          </section>
        ))}
      </div>
    </div>
  );
}
