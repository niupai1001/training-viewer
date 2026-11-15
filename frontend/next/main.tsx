import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
echarts.use([
  LineChart,
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
  CanvasRenderer,
]);
import "./style.css";

declare global {
  interface Window {
    pywebview?: {
      api: {
        choose_directory(): Promise<string | null>;
        save_writer(): Promise<boolean>;
      };
    };
  }
}
type Definition = {
  label: string;
  unit: string;
  direction: string;
  role: string;
};
type View = { charts: string[]; numbers: string[]; primary_metric: string };
type Run = {
  meta: {
    run_id: string;
    created_at: string;
    experiment: { id: string; name: string };
    variant: { id: string; name: string; kind: string; description?: string };
    metrics: Record<string, Definition>;
    view: View;
    config: unknown;
  };
  revision: number;
  status: string;
  sessions: string[];
  source: string;
};
type Point = {
  x: number;
  value: number;
  session: string;
  step: number;
  epoch: number | null;
};
type Curve = {
  points: Point[];
  count: number;
  x_min: number | null;
  x_max: number | null;
  y_min: number | null;
  y_max: number | null;
  downsampled: boolean;
};
type Summary = Record<string, { latest: Point | null; best: Point | null }>;
const token = new URLSearchParams(location.hash.slice(1)).get("token") || "";
history.replaceState(null, "", location.pathname);
async function api(path: string, method = "GET", body?: unknown) {
  const r = await fetch("/api/v2/" + path, {
    method,
    headers: { "x-viewer-token": token, "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await r.json();
  if (!r.ok) throw Error(data.detail || "请求失败");
  return data;
}
const fmt = (v: number | undefined | null, unit = "") =>
  v == null
    ? "—"
    : unit === "ratio"
      ? (v * 100).toFixed(2) + "%"
      : new Intl.NumberFormat("zh-CN", { maximumSignificantDigits: 6 }).format(
          v,
        );
const status: Record<string, string> = {
  running: "训练中",
  completed: "已完成",
  failed: "失败",
  interrupted: "更新中断",
  unknown: "等待数据",
};

function duration(seconds: number | null) {
  if (seconds == null) return "未记录";
  if (seconds > 0 && seconds < 1) return "不足 1 秒";
  const total = Math.floor(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor(total / 60) % 60;
  return [hours ? hours + " 小时" : "", minutes ? minutes + " 分钟" : "",
    total % 60 + " 秒"].filter(Boolean).join(" ");
}

function RunOverview({ run, summary, seconds }: { run: Run; summary: Summary; seconds: number | null }) {
  const metrics = run.meta.metrics;
  const orderedKeys = Array.from(new Set([run.meta.view.primary_metric, ...run.meta.view.charts, ...Object.keys(metrics)]));
  const accuracy = orderedKeys.find((key) => /(?:^|[^a-z])(?:accuracy|acc|top[_-]?1)(?:[^a-z]|$)|准确率/.test((key + " " + metrics[key].label).toLowerCase()));
  const score = accuracy || orderedKeys.find((key) => metrics[key].role === "score");
  const loss = orderedKeys.find((key) => metrics[key].role === "loss");
  function display(key: string | undefined) {
    if (!key || !summary[key]?.latest) return "未记录";
    const { unit } = metrics[key];
    return fmt(summary[key].latest.value, unit) + (unit === "%" ? "%" : unit && !["1", "ratio"].includes(unit) ? " " + unit : "");
  }
  return (
    <dl className="run-overview" aria-label="训练摘要">
      <div><dt>{accuracy ? "精度" : "精度 / 评估指标"}</dt><dd>{display(score)}</dd>
        {score && <small>{metrics[score].label}</small>}</div>
      <div><dt>损失</dt><dd>{display(loss)}</dd>
        {loss && <small>{metrics[loss].label}</small>}</div>
      <div><dt>训练时长</dt><dd>{duration(seconds)}</dd>
        <small>{run.status === "running" || run.status === "interrupted" ? "截至最近记录" : "各训练阶段累计"}</small></div>
    </dl>
  );
}

function Chart({
  run,
  metric,
  summary,
}: {
  run: Run;
  metric: string;
  summary: Summary;
}) {
  const definition = run.meta.metrics[metric];
  const savedKey = "chart." + run.meta.experiment.id + "." + metric;
  const [mode, setMode] = useState(
    definition.role === "loss" ? "late" : "full",
  );
  const [session, setSession] = useState(run.sessions.at(-1) || "");
  const [axis, setAxis] = useState("step");
  const [range, setRange] = useState<[number, number] | null>(null);
  const [manual, setManual] = useState<[number, number] | null>(null);
  const [log, setLog] = useState(false);
  const [large, setLarge] = useState(false);
  const [menu, setMenu] = useState(false);
  const [curve, setCurve] = useState<Curve | null>(null);
  const [overview, setOverview] = useState<Curve | null>(null);
  const [error, setError] = useState("");
  const [minText, setMinText] = useState("");
  const [maxText, setMaxText] = useState("");
  const node = useRef<HTMLDivElement>(null),
    thumb = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null),
    mini = useRef<echarts.ECharts | null>(null);
  const rangeRef = useRef(setRange);
  rangeRef.current = setRange;
  const bounds = useRef<{ value: [number, number]; at: number } | null>(null);
  const ready = useRef(false);
  useEffect(() => {
    bounds.current = null;
  }, [mode, session, axis, range, manual]);
  useEffect(() => {
    let live = true;
    api("settings/" + encodeURIComponent(savedKey))
      .then((s) => {
        if (live && s) {
          setMode(s.mode);
          setAxis(s.axis);
          setLog(s.log);
          setManual(s.manual);
          setRange(s.range);
        }
      })
      .finally(() => {
        ready.current = true;
      });
    return () => {
      live = false;
    };
  }, [savedKey]);
  useEffect(() => {
    if (ready.current)
      api("settings/" + encodeURIComponent(savedKey), "PUT", {
        value: { mode, axis, log, manual, range },
      }).catch(() => {});
  }, [mode, axis, log, manual, range]);
  useEffect(() => {
    const c = echarts.init(node.current!),
      m = echarts.init(thumb.current!);
    chart.current = c;
    mini.current = m;
    const observer = new ResizeObserver(() => {
      c.resize();
      m.resize();
    });
    observer.observe(node.current!);
    observer.observe(thumb.current!);
    const zoom = (e: any) => {
      const z = e.batch?.[0] || e;
      const o = m.getOption() as any;
      const lo = z.startValue ?? o.xAxis?.[0]?.min;
      const hi = z.endValue ?? o.xAxis?.[0]?.max;
      const a = o.xAxis?.[0]?.min,
        b = o.xAxis?.[0]?.max;
      if (Number.isFinite(a) && Number.isFinite(b))
        rangeRef.current([
          z.startValue ?? a + ((b - a) * (z.start ?? 0)) / 100,
          z.endValue ?? a + ((b - a) * (z.end ?? 100)) / 100,
        ]);
    };
    m.on("datazoom", zoom);
    c.on("datazoom", (e: any) => {
      const z = e.batch?.[0] || e;
      const o = c.getOption() as any;
      const a = o.xAxis[0].min,
        b = o.xAxis[0].max;
      if (Number.isFinite(a) && Number.isFinite(b))
        rangeRef.current([
          z.startValue ?? a + ((b - a) * (z.start ?? 0)) / 100,
          z.endValue ?? a + ((b - a) * (z.end ?? 100)) / 100,
        ]);
    });
    return () => {
      observer.disconnect();
      c.dispose();
      m.dispose();
    };
  }, []);
  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const base =
          "runs/" +
          run.meta.run_id +
          "/curve?key=" +
          encodeURIComponent(metric) +
          "&axis=" +
          axis +
          (session ? "&session=" + encodeURIComponent(session) : "");
        const all: Curve = await api(base + "&budget=400");
        if (!live) return;
        setOverview(all);
        let selected = range;
        if (
          !selected &&
          mode === "late" &&
          all.x_min != null &&
          all.x_max != null
        )
          selected = [all.x_max - (all.x_max - all.x_min) * 0.2, all.x_max];
        let data: Curve = await api(
          base +
            "&budget=2000" +
            (selected ? "&low=" + selected[0] + "&high=" + selected[1] : ""),
        );
        if (mode === "late" && !range && data.count < 2)
          data = await api(base + "&budget=2000");
        if (live) {
          setCurve(data);
          setError("");
        }
      } catch (e) {
        if (live) setError(String(e));
      }
    })();
    return () => {
      live = false;
    };
  }, [run.meta.run_id, run.revision, metric, mode, session, axis, range]);
  useEffect(() => {
    if (!curve || !chart.current || !overview || !mini.current) return;
    const lo = curve.y_min ?? 0,
      hi = curve.y_max ?? 1,
      pad = lo === hi ? Math.max(Math.abs(lo) * 0.05, 1e-6) : (hi - lo) * 0.05;
    const target: [number, number] = [lo - pad, hi + pad];
    const old = bounds.current;
    if (!old || Date.now() - old.at > 10000)
      bounds.current = { value: target, at: Date.now() };
    else
      bounds.current = {
        value: [
          Math.min(old.value[0], target[0]),
          Math.max(old.value[1], target[1]),
        ],
        at: old.at,
      };
    const y = manual || bounds.current.value;
    const positive = lo > 0;
    const groups = Array.from(new Set(curve.points.map((p) => p.session)));
    chart.current.setOption(
      {
        animation: false,
        grid: { left: 62, right: 20, top: 24, bottom: 36 },
        tooltip: {
          trigger: "axis",
          valueFormatter: (v: any) => fmt(Number(v), definition.unit),
        },
        xAxis: {
          type: "value",
          min: curve.x_min ?? 0,
          max: curve.x_max ?? 1,
          name: axis === "step" ? "Step" : "Epoch",
          nameLocation: "middle",
          nameGap: 24,
        },
        yAxis: {
          type: log && positive ? "log" : "value",
          min: log && positive ? Math.max(lo * 0.95, Number.MIN_VALUE) : y[0],
          max: log && positive ? hi * 1.05 : y[1],
          axisLabel: { formatter: (v: number) => fmt(v, definition.unit) },
          splitLine: { lineStyle: { color: "#edf0f4" } },
        },
        dataZoom: [{ type: "inside", filterMode: "none" }],
        series: groups.map((s, i) => ({
          name: "阶段 " + (i + 1),
          type: "line",
          showSymbol: curve.points.filter((p) => p.session === s).length < 3,
          connectNulls: false,
          lineStyle: { width: 2, color: "#4f65dc" },
          itemStyle: { color: "#4f65dc" },
          data: curve.points
            .filter((p) => p.session === s)
            .map((p) => [p.x, p.value]),
        })),
      },
      { notMerge: true },
    );
    mini.current.setOption(
      {
        animation: false,
        grid: { left: 10, right: 10, top: 4, bottom: 22 },
        xAxis: {
          type: "value",
          min: overview.x_min ?? 0,
          max: overview.x_max ?? 1,
          show: false,
        },
        yAxis: { type: "value", show: false, scale: true },
        series: [
          {
            type: "line",
            symbol: "none",
            lineStyle: { width: 1, color: "#a2abd1" },
            data: overview.points.map((p) => [p.x, p.value]),
          },
        ],
        dataZoom: [
          {
            type: "slider",
            height: 14,
            bottom: 2,
            startValue: curve.x_min,
            endValue: curve.x_max,
            showDetail: false,
            filterMode: "none",
          },
        ],
      },
      { notMerge: true },
    );
  }, [curve, overview, manual, log]);
  const latest = summary[metric]?.latest,
    best = summary[metric]?.best;
  return (
    <article className={"chart-card " + (large ? "expanded" : "")}>
      <header>
        <div>
          <h3>{definition.label}</h3>
          <span className="muted">
            最新 <b>{fmt(latest?.value, definition.unit)}</b>{" "}
            {best && <> · 全程最佳 {fmt(best.value, definition.unit)}</>}
          </span>
          <small>
            {latest && "最近记录 Step " + latest.step}
            {best && " · 最佳 Step " + best.step}
          </small>
        </div>
        <button onClick={() => setMenu(!menu)} aria-label="图表设置">
          ···
        </button>
      </header>
      <div className="chart-tools">
        <div className="segmented">
          <button
            className={mode === "full" ? "active" : ""}
            onClick={() => {
              setMode("full");
              setRange(null);
            }}
          >
            完整过程
          </button>
          <button
            className={mode === "late" ? "active" : ""}
            onClick={() => {
              setMode("late");
              setRange(null);
            }}
          >
            后期细节
          </button>
        </div>
        {range && (
          <button
            onClick={() => {
              setRange(null);
              setManual(null);
              setMode("late");
            }}
          >
            返回实时
          </button>
        )}
      </div>
      {menu && (
        <div className="chart-menu">
          <select
            value={session}
            onChange={(e) => {
              setSession(e.target.value);
              setRange(null);
            }}
          >
            <option value="">全部阶段</option>
            {run.sessions.map((s, i) => (
              <option key={s} value={s}>
                阶段 {i + 1}
              </option>
            ))}
          </select>
          <select
            value={axis}
            onChange={(e) => {
              setAxis(e.target.value);
              setRange(null);
            }}
          >
            <option value="step">Step</option>
            <option value="epoch">Epoch</option>
          </select>
          <label>
            <input
              type="checkbox"
              checked={log}
              onChange={(e) => setLog(e.target.checked)}
            />
            对数轴
          </label>
          <div className="inline">
            <input
              aria-label="Y 轴最小值"
              placeholder="Y 最小"
              value={minText}
              onChange={(e) => setMinText(e.target.value)}
            />
            <input
              aria-label="Y 轴最大值"
              placeholder="Y 最大"
              value={maxText}
              onChange={(e) => setMaxText(e.target.value)}
            />
            <button
              onClick={() => {
                const a = Number(minText),
                  b = Number(maxText);
                if (
                  minText &&
                  maxText &&
                  Number.isFinite(a) &&
                  Number.isFinite(b) &&
                  a < b
                )
                  setManual([a, b]);
                else setError("请输入有效且递增的 Y 轴范围");
              }}
            >
              应用
            </button>
            <button
              onClick={() => {
                setManual(null);
                setMinText("");
                setMaxText("");
                setError("");
              }}
            >
              自动
            </button>
          </div>
          <button
            onClick={() => {
              setLarge(!large);
              setTimeout(() => {
                chart.current?.resize();
                mini.current?.resize();
              }, 0);
            }}
          >
            {large ? "还原" : "放大图表"}
          </button>
          <button
            onClick={() => {
              const a = document.createElement("a");
              a.href = chart.current!.getDataURL({
                type: "png",
                pixelRatio: 2,
                backgroundColor: "#fff",
              });
              a.download = definition.label + ".png";
              a.click();
            }}
          >
            导出 PNG
          </button>
        </div>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div ref={node} className="plot" />
      <div ref={thumb} className="thumbnail" />
      <footer>
        {curve?.count
          ? `${mode === "late" ? "后期细节" : "完整过程"} · ${axis} ${fmt(curve.x_min)}–${fmt(curve.x_max)}`
          : "等待有效数据"}
        {curve?.downsampled ? " · 已保留极值采样" : ""}
        {log && curve?.y_min != null && curve.y_min <= 0
          ? " · 存在非正值，使用线性轴"
          : ""}
        {manual &&
        curve?.y_min != null &&
        (manual[0] > curve.y_min || manual[1] < (curve.y_max ?? 0))
          ? " · 手动范围外存在数据"
          : ""}
      </footer>
    </article>
  );
}

function AddExperiment({ close, onAdded }: { close: () => void; onAdded: () => void }) {
  const [tab, setTab] = useState("existing"),
    [path, setPath] = useState(""),
    [preview, setPreview] = useState<any>(null),
    [error, setError] = useState(""),
    [code, setCode] = useState("");
  const [name, setName] = useState(""),
    [variant, setVariant] = useState("基线"),
    [kind, setKind] = useState("baseline"),
    [description, setDescription] = useState("");
  const [metric, setMetric] = useState("validation/accuracy"),
    [label, setLabel] = useState("验证准确率"),
    [unit, setUnit] = useState("ratio"),
    [direction, setDirection] = useState("max");
  const alive = useRef(true);
  useEffect(
    () => () => {
      alive.current = false;
    },
    [],
  );
  async function choose() {
    try {
      const p = await window.pywebview?.api.choose_directory();
      if (p) {
        setPath(p);
        setPreview(null);
      }
    } catch (e) {
      setError(String(e));
    }
  }
  async function inspect() {
    try {
      const job = await api("previews", "POST", { path });
      setPreview({ done: false, items: [], issues: [] });
      while (alive.current) {
        const p = await api("previews/" + job.id);
        if (!alive.current) return;
        setPreview(p);
        if (p.done) break;
        await new Promise((r) => setTimeout(r, 350));
      }
    } catch (e) {
      setError(String(e));
    }
  }
  async function confirm() {
    try {
      await api("roots", "POST", { path });
      onAdded();
      close();
    } catch (e) {
      setError(String(e));
    }
  }
  async function generate() {
    try {
      const score = metric.trim();
      const loss = "train/loss";
      if (
        !name.trim() ||
        !variant.trim() ||
        (score && (!label.trim() || score === loss)) ||
        (kind !== "baseline" && !description.trim())
      )
        throw Error("请填写实验、方案、指标和改动说明");
      const identityKey = "identity." + name.trim();
      const id =
        (await api("settings/" + encodeURIComponent(identityKey))) ||
        crypto.randomUUID();
      await api("settings/" + encodeURIComponent(identityKey), "PUT", {
        value: id,
      });
      const variantKey = "variant." + id + "." + variant.trim();
      const variantId =
        (await api("settings/" + encodeURIComponent(variantKey))) ||
        crypto.randomUUID();
      await api("settings/" + encodeURIComponent(variantKey), "PUT", {
        value: variantId,
      });
      const metadata = {
        experiment: { id, name: name.trim() },
        variant: { id: variantId, name: variant.trim(), kind, description },
        metrics: {
          [loss]: { label: "训练损失", unit: "1", direction: "min", role: "loss" },
          ...(score ? { [score]: { label: label.trim(), unit, direction, role: "score" } } : {}),
        },
        charts: score ? [loss, score] : [loss],
        primary_metric: score || loss,
      };
      await api("roots", "POST", { path });
      onAdded();
      setCode(
        "from pathlib import Path\nfrom uuid import uuid4\nfrom tvlp_writer import RunWriter\n\nsettings = " +
          JSON.stringify(metadata, null, 2) +
          "\noutput = Path(" +
          JSON.stringify(path) +
          ") / uuid4().hex\nwith RunWriter(output, **settings) as writer:\n    # 在训练循环中记录实际 step 和损失：\n    # writer.log(step, {\"train/loss\": float(training_loss)})\n" +
          (score ? "    # 验证完成时，记录同一进度的实际评估值：\n    # writer.log(step, {" + JSON.stringify(score) + ": float(validation_score)})\n" : "") +
          "    pass  # 在这里运行你的训练循环\n",
      );
    } catch (e) {
      setError(String(e));
    }
  }
  return (
    <div className="backdrop" onClick={close}>
      <section
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-label="添加实验"
        onClick={(e) => e.stopPropagation()}
      >
        <header>
          <h2>添加实验</h2>
          <button onClick={close}>关闭</button>
        </header>
        <div className="segmented">
          <button
            className={tab === "existing" ? "active" : ""}
            onClick={() => setTab("existing")}
          >
            已有训练目录
          </button>
          <button
            className={tab === "new" ? "active" : ""}
            onClick={() => setTab("new")}
          >
            接入新训练
          </button>
        </div>
        <label>
          训练输出目录
          <div className="inline">
            <input
              value={path}
              onChange={(e) => {
                setPath(e.target.value);
                setPreview(null);
              }}
              placeholder="选择包含训练记录的目录"
            />
            <button onClick={choose}>选择目录</button>
          </div>
        </label>
        {tab === "existing" ? (
          <>
            <button className="primary" disabled={!path} onClick={inspect}>
              预览目录
            </button>
            {preview && (
              <>
                <p>
                  {preview.done ? "扫描完成" : "正在扫描…"} · 发现{" "}
                  {preview.items.length} 条训练记录
                </p>
                <div className="preview">
                  {preview.items.map((x: any, i: number) => (
                    <p key={i}>
                      {x.experiment} / {x.variant}
                    </p>
                  ))}
                  {preview.issues.map((x: any, i: number) => (
                    <p key={i} className="error">
                      {x.path}：{x.message}
                    </p>
                  ))}
                </div>
                {preview.done && (
                  <button className="primary" onClick={confirm}>
                    {preview.items.length
                      ? "添加并切换到此目录"
                      : "监视目录，等待训练写入"}
                  </button>
                )}
              </>
            )}
          </>
        ) : (
          <>
            {!code ? (
              <>
                <label>
                  实验名称
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="例如：注意力模块消融"
                  />
                </label>
                <div className="inline">
                  <label>
                    方案名称
                    <input
                      value={variant}
                      onChange={(e) => setVariant(e.target.value)}
                    />
                  </label>
                  <label>
                    方案类型
                    <select
                      value={kind}
                      onChange={(e) => setKind(e.target.value)}
                    >
                      <option value="baseline">基线</option>
                      <option value="ablation">消融</option>
                      <option value="modification">改动</option>
                    </select>
                  </label>
                </div>
                <label>
                  改动说明
                  <input
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="一句话说明本方案"
                  />
                </label>
                <div className="inline">
                  <label>
                    评估指标键（可留空）
                    <input
                      value={metric}
                      onChange={(e) => setMetric(e.target.value)}
                    />
                  </label>
                  <label>
                    显示名称
                    <input
                      value={label}
                      onChange={(e) => setLabel(e.target.value)}
                    />
                  </label>
                </div>
                <div className="inline">
                  <select aria-label="评估指标方向" value={direction} onChange={(e) => setDirection(e.target.value)}>
                    <option value="min">越低越好</option>
                    <option value="max">越高越好</option>
                    <option value="none">无优化方向</option>
                  </select>
                  <select aria-label="评估指标单位" value={unit} onChange={(e) => setUnit(e.target.value)}>
                    <option value="ratio">比例（0–1，显示为百分比）</option>
                    <option value="%">百分值（0–100）</option>
                    <option value="1">普通数值</option>
                  </select>
                </div>
                <button className="primary" disabled={!path} onClick={generate}>
                  生成接入代码并监视目录
                </button>
              </>
            ) : (
              <>
                <p>
                  目录已加入监视。保存写入器，将记录调用放进训练循环；应用会自动发现数据。
                </p>
                <pre>{code}</pre>
                <div className="inline">
                  <button onClick={() => navigator.clipboard.writeText(code)}>
                    复制代码
                  </button>
                  <button onClick={() => window.pywebview?.api.save_writer()}>
                    保存独立写入器
                  </button>
                  <button className="primary" onClick={close}>
                    完成
                  </button>
                </div>
              </>
            )}
          </>
        )}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </section>
    </div>
  );
}

function App() {
  const [runs, setRuns] = useState<Run[]>([]),
    [selected, setSelected] = useState(""),
    [limit, setLimit] = useState(50),
    [overview, setOverview] = useState<{ id: string; summary: Summary; seconds: number | null } | null>(null),
    [view, setView] = useState<View | null>(null),
    [add, setAdd] = useState(false),
    [drawer, setDrawer] = useState(false),
    [search, setSearch] = useState(""),
    [error, setError] = useState(""),
    [roots, setRoots] = useState<string[]>([]),
    [folderChange, setFolderChange] = useState(0),
    [health, setHealth] = useState<any>(null),
    [settings, setSettings] = useState(false);
  const run = runs.find((r) => r.meta.run_id === selected);
  const summary = overview?.id === selected ? overview.summary : {};
  const initialized = useRef(false);
  function refreshFolder() {
    setRuns([]);
    setSelected("");
    setDrawer(false);
    setLimit(50);
    setFolderChange((value) => value + 1);
  }
  async function selectFolder(path: string) {
    try {
      await api("roots/active", "PUT", { path });
      refreshFolder();
    } catch (e) {
      setError(String(e));
    }
  }
  async function removeFolder(path: string) {
    try {
      await api("roots", "DELETE", { path });
      refreshFolder();
    } catch (e) {
      setError(String(e));
    }
  }
  useEffect(() => {
    let live = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const [items, paths, h] = await Promise.all([
          api("runs?limit=" + limit),
          api("roots"),
          api("health"),
        ]);
        if (!live) return;
        setRuns(items);
        setRoots(paths);
        setHealth(h);
        setError("");
        if (!initialized.current) {
          const saved = await api("settings/workspace");
          if (!live) return;
          setSelected(
            items.find((r: Run) => r.meta.run_id === saved)?.meta.run_id ||
              items[0]?.meta.run_id ||
              "",
          );
          initialized.current = true;
        } else setSelected((current) =>
          items.some((item: Run) => item.meta.run_id === current) ? current : items[0]?.meta.run_id || "",
        );
      } catch (e) {
        if (live) setError(String(e));
      }
      if (live) timer = setTimeout(poll, document.hidden ? 10000 : 2000);
    }
    poll();
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [limit, folderChange]);
  useEffect(() => {
    if (selected)
      api("settings/workspace", "PUT", { value: selected }).catch(() => {});
  }, [selected]);
  useEffect(() => {
    let live = true;
    if (run) {
      const path = "runs/" + encodeURIComponent(selected);
      Promise.all([api(path + "/summary"), api(path)])
        .then(([summary, detail]) => {
          if (live) setOverview({ id: selected, summary, seconds: detail.training_seconds });
        })
        .catch((e) => {
          if (live) setError(String(e));
        });
    }
    return () => {
      live = false;
    };
  }, [selected, run?.revision]);
  useEffect(() => {
    let live = true;
    setView(null);
    if (run)
      api("settings/view." + run.meta.experiment.id)
        .then((v) => {
          if (live) setView(v || run.meta.view);
        })
        .catch(() => {
          if (live) setView(run.meta.view);
        });
    return () => {
      live = false;
    };
  }, [selected]);
  function updateView(v: View) {
    setView(v);
    api("settings/view." + run!.meta.experiment.id, "PUT", { value: v }).catch(
      (e) => setError(String(e)),
    );
  }
  const experiments = Array.from(
    new Set(runs.map((r) => r.meta.experiment.id)),
  );
  useEffect(() => {
    if (!add && !drawer) return;
    const before = document.activeElement as HTMLElement;
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setAdd(false);
        setDrawer(false);
      }
      if (e.key === "Tab") {
        const dialog = document.querySelector('[role="dialog"]');
        const focus = Array.from(
          dialog?.querySelectorAll<HTMLElement>(
            "button,input,select,textarea",
          ) || [],
        ).filter((e) => !e.hasAttribute("disabled"));
        if (focus.length) {
          const i = focus.indexOf(document.activeElement as HTMLElement);
          if (e.shiftKey && i <= 0) {
            e.preventDefault();
            focus.at(-1)!.focus();
          } else if (!e.shiftKey && i === focus.length - 1) {
            e.preventDefault();
            focus[0].focus();
          }
        }
      }
    };
    document.addEventListener("keydown", key);
    setTimeout(
      () =>
        document.querySelector<HTMLElement>('[role="dialog"] button')?.focus(),
      0,
    );
    return () => {
      document.removeEventListener("keydown", key);
      before?.focus();
    };
  }, [add, drawer]);
  return (
    <>
      <div className="app">
        <aside className="sidebar">
          <div className="brand">
            <span className="brand-icon">↗</span> Training Viewer
          </div>
          <button className="primary add" onClick={() => setAdd(true)}>
            ＋ 添加实验
          </button>
          {roots.length > 0 && (
            <label className="folder-picker">
              当前目录
              <select value={health?.active_root ?? ""} onChange={(e) => selectFolder(e.target.value)}>
                {roots.map((path) => <option key={path} value={path} title={path}>{path}</option>)}
              </select>
            </label>
          )}
          <div className="nav-title">实验</div>
          <nav>
            {experiments.map((id) => {
              const group = runs.filter((r) => r.meta.experiment.id === id);
              return (
                <section key={id}>
                  <h3>{group[0].meta.experiment.name}</h3>
                  {Array.from(new Set(group.map((r) => r.meta.variant.id))).map(
                    (v) => (
                      <div key={v}>
                        <h4>
                          {
                            group.find((r) => r.meta.variant.id === v)!.meta
                              .variant.name
                          }
                        </h4>
                        {group
                          .filter((r) => r.meta.variant.id === v)
                          .map((r) => (
                            <button
                              className={
                                "run-link " +
                                (selected === r.meta.run_id ? "selected" : "")
                              }
                              key={r.meta.run_id}
                              onClick={() => setSelected(r.meta.run_id)}
                            >
                              <span className={"dot " + r.status} />
                              {new Date(r.meta.created_at).toLocaleString(
                                "zh-CN",
                                {
                                  month: "numeric",
                                  day: "numeric",
                                  hour: "2-digit",
                                  minute: "2-digit",
                                },
                              )}
                            </button>
                          ))}
                      </div>
                    ),
                  )}
                </section>
              );
            })}
          </nav>
          {runs.length >= limit && (
            <button onClick={() => setLimit(limit + 50)}>加载更多</button>
          )}
          <button className="settings" onClick={() => setSettings(!settings)}>
            目录与设置
          </button>
        </aside>
        <main>
          <div className="topline">
            <span>训练工作区</span>
            <span className="muted">
              {health?.progress.scanning ? "正在更新目录…" : "本地工作区"}
            </span>
          </div>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          {settings && (
            <section className="settings-panel">
              <h3>监视目录</h3>
              {roots.map((p) => (
                <div className="inline" key={p}>
                  <code>{p}</code>
                  <button onClick={() => removeFolder(p)}>
                    移除监视
                  </button>
                </div>
              ))}
              <p className="muted">
                实验列表显示当前目录。移除监视后，可重新添加该目录查看日志。
              </p>
              <details>
                <summary>读取问题 {health?.issues.length || 0}</summary>
                {health?.issues.map((i: any, n: number) => (
                  <p key={n}>
                    {i.path}：{i.message}
                  </p>
                ))}
              </details>
            </section>
          )}
          {!run ? (
            <div className="empty">
              <div className="empty-icon">↗</div>
              <h1>{roots.length ? "等待训练写入" : "开始查看你的训练"}</h1>
              <p>选择训练输出目录，核心指标会在这里自动更新。</p>
              <button className="primary" onClick={() => setAdd(true)}>
                添加实验
              </button>
            </div>
          ) : (
            <>
              <header className="run-header">
                <p className="eyebrow">{run.meta.experiment.name}</p>
                <div className="inline">
                  <h1>{run.meta.variant.name}</h1>
                  <span className={"status " + run.status}>
                    {status[run.status]}
                  </span>
                </div>
                <p className="muted">
                  {run.meta.variant.description || "基线方案"} ·{" "}
                  {new Date(run.meta.created_at).toLocaleString("zh-CN")}
                  {view && summary[view.charts[0]]?.latest && (
                    <> · Step {summary[view.charts[0]].latest!.step}
                      {summary[view.charts[0]].latest!.epoch != null &&
                        ` · Epoch ${fmt(summary[view.charts[0]].latest!.epoch)}`}
                    </>
                  )}
                </p>
              </header>
              <RunOverview run={run} summary={summary}
                seconds={overview?.id === selected ? overview.seconds : null} />
              <div className="section-heading">
                <h2>核心指标</h2>
                <button onClick={() => setDrawer(true)}>
                  全部指标 · {Object.keys(run.meta.metrics).length}
                </button>
              </div>
              <div className="charts">
                {view?.charts
                  .filter((k) => run.meta.metrics[k])
                  .map((k) => (
                    <Chart
                      key={selected + k}
                      run={run}
                      metric={k}
                      summary={summary}
                    />
                  ))}
              </div>
              <div className="numbers">
                {view?.numbers
                  .filter((k) => run.meta.metrics[k])
                  .map((k) => (
                    <span key={k}>
                      {run.meta.metrics[k].label}{" "}
                      <b>
                        {fmt(
                          summary[k]?.latest?.value,
                          run.meta.metrics[k].unit,
                        )}
                      </b>
                    </span>
                  ))}
              </div>
              <details className="config">
                <summary>配置与实验说明</summary>
                <p>{run.meta.variant.description}</p>
                <pre>{JSON.stringify(run.meta.config, null, 2)}</pre>
                <p className="muted">来源：{run.source}</p>
              </details>
            </>
          )}
        </main>
      </div>
      {add && <AddExperiment close={() => setAdd(false)} onAdded={refreshFolder} />}{" "}
      {drawer && run && view && (
        <div className="backdrop" onClick={() => setDrawer(false)}>
          <section
            className="dialog"
            role="dialog"
            aria-modal="true"
            aria-label="全部指标"
            onClick={(e) => e.stopPropagation()}
          >
            <header>
              <h2>全部指标</h2>
              <button onClick={() => setDrawer(false)}>关闭</button>
            </header>
            <input
              autoFocus
              placeholder="搜索名称或指标键"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <p className="muted">
              最多固定四张曲线和四项数字。取消现有选择后可替换。
            </p>
            {Object.entries(run.meta.metrics)
              .filter(([k, d]) =>
                (k + d.label).toLowerCase().includes(search.toLowerCase()),
              )
              .map(([k, d]) => (
                <div className="metric-row" key={k}>
                  <div>
                    <strong>{d.label}</strong>
                    <small>
                      {k} · {fmt(summary[k]?.latest?.value, d.unit)}
                    </small>
                  </div>
                  <label>
                    <input
                      type="checkbox"
                      checked={view.charts.includes(k)}
                      disabled={
                        (!view.charts.includes(k) && view.charts.length >= 4) ||
                        (view.charts.includes(k) && view.charts.length === 1)
                      }
                      onChange={(e) =>
                        updateView({
                          ...view,
                          charts: e.target.checked
                            ? [...view.charts, k]
                            : view.charts.filter((x) => x !== k),
                        })
                      }
                    />
                    曲线
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={view.numbers.includes(k)}
                      disabled={
                        !view.numbers.includes(k) && view.numbers.length >= 4
                      }
                      onChange={(e) =>
                        updateView({
                          ...view,
                          numbers: e.target.checked
                            ? [...view.numbers, k]
                            : view.numbers.filter((x) => x !== k),
                        })
                      }
                    />
                    数字
                  </label>
                </div>
              ))}
          </section>
        </div>
      )}
    </>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
