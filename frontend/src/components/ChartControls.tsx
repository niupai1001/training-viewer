import type { AxisRequest, SmoothingMethod } from "../types";
import { axisLabel } from "../utils/format";
import { smoothingLabel } from "../utils/smoothing";

export interface ChartPreferences {
  axis: AxisRequest;
  smoothing: SmoothingMethod;
  smoothingWindow: number;
  logScale: boolean;
  showRaw: boolean;
}

export const DEFAULT_CHART_PREFERENCES: ChartPreferences = {
  axis: "auto",
  smoothing: "none",
  smoothingWindow: 5,
  logScale: false,
  showRaw: false,
};

export function ChartControls({
  value,
  onChange,
  axes = ["auto", "global_step", "epoch", "timestamp"],
}: {
  value: ChartPreferences;
  onChange: (next: ChartPreferences) => void;
  axes?: AxisRequest[];
}) {
  return (
    <div className="chart-controls" role="group" aria-label="图表显示设置">
      <div className="chart-control">
        <span className="control-label">横轴</span>
        <div className="segmented">
          {axes.map((axis) => (
            <button
              key={axis}
              type="button"
              className={`segment ${value.axis === axis ? "segment-active" : ""}`}
              onClick={() => onChange({ ...value, axis })}
              title={
                axis === "auto"
                  ? "按每个指标实际存在的数据自动选择优化步或训练轮次"
                  : `按${axisLabel(axis)}绘制`
              }
            >
              {axis === "auto"
                ? "自动"
                : axis === "global_step"
                  ? "优化步"
                  : axis === "epoch"
                    ? "训练轮次"
                    : "时间"}
            </button>
          ))}
        </div>
      </div>
      <label className="chart-control">
        <span className="control-label">平滑</span>
        <select
          value={value.smoothing}
          onChange={(event) =>
            onChange({ ...value, smoothing: event.target.value as SmoothingMethod })
          }
          title="平滑只影响曲线显示，不改变最佳/最终统计"
        >
          <option value="none">{smoothingLabel("none")}</option>
          <option value="moving_average">{smoothingLabel("moving_average")}</option>
          <option value="ema">{smoothingLabel("ema")}</option>
        </select>
      </label>
      <label className="chart-control chart-control-range">
        <span className="control-label">平滑窗口</span>
        <input
          type="range"
          min={2}
          max={50}
          step={1}
          value={value.smoothingWindow}
          disabled={value.smoothing === "none"}
          onChange={(event) =>
            onChange({ ...value, smoothingWindow: Number(event.target.value) })
          }
        />
        <span className="range-value">{value.smoothingWindow}</span>
      </label>
      <label className="chart-control chart-control-check">
        <input
          type="checkbox"
          checked={value.logScale}
          onChange={(event) => onChange({ ...value, logScale: event.target.checked })}
        />
        对数轴
      </label>
      <label className="chart-control chart-control-check">
        <input
          type="checkbox"
          checked={value.showRaw}
          disabled={value.smoothing === "none"}
          onChange={(event) => onChange({ ...value, showRaw: event.target.checked })}
        />
        同时显示原始曲线
      </label>
    </div>
  );
}
