import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MetricChart } from "./MetricChart";
import type { SeriesPoint } from "../types";

const { chartMock } = vi.hoisted(() => ({
  chartMock: {
    setOption: vi.fn(),
    resize: vi.fn(),
    dispose: vi.fn(),
    on: vi.fn(),
    off: vi.fn(),
    getOption: vi.fn(() => ({ dataZoom: [{ start: 0, end: 100 }], series: [] })),
    getDataURL: vi.fn(() => "data:image/png;base64,stub"),
    group: "",
  },
}));

vi.mock("../charts/echarts", () => ({
  echarts: {
    init: vi.fn(() => chartMock),
    connect: vi.fn(),
  },
}));

const point: SeriesPoint = {
  x: 10,
  value: 0.5,
  global_step: 10,
  epoch: 1,
  timestamp: "2026-10-31T08:00:00.000000Z",
  session_id: "s1",
};

function renderChart(points: SeriesPoint[]) {
  return render(
    <MetricChart
      title="val/loss"
      lines={[{ id: "val/loss", label: "val/loss", points, unit: "none" }]}
      axis="global_step"
      smoothing="none"
      smoothingWindow={5}
      logScale={false}
      showRaw={false}
    />,
  );
}

describe("MetricChart lifecycle", () => {
  beforeEach(() => {
    chartMock.setOption.mockClear();
    chartMock.dispose.mockClear();
    chartMock.on.mockClear();
    chartMock.off.mockClear();
  });

  it("keeps the chart container mounted when data is empty and later receives points", () => {
    const view = renderChart([]);
    expect(screen.getByRole("img", { name: /val\/loss/i })).toBeInTheDocument();
    expect(screen.getByText(/当前没有可绘制的数据点/i)).toBeInTheDocument();
    expect(chartMock.setOption).toHaveBeenCalled();

    view.rerender(
      <MetricChart
        title="val/loss"
        lines={[{ id: "val/loss", label: "val/loss", points: [point], unit: "none" }]}
        axis="global_step"
        smoothing="none"
        smoothingWindow={5}
        logScale={false}
        showRaw={false}
      />,
    );
    expect(screen.queryByText(/当前没有可绘制的数据点/i)).not.toBeInTheDocument();
    const lastOption = chartMock.setOption.mock.calls.at(-1)?.[0] as {
      series?: { data?: { value?: number[] }[] }[];
    };
    expect(lastOption.series?.[0]?.data?.[0]?.value).toEqual([10, 0.5]);
  });

  it("splits multiple sessions instead of connecting step resets", () => {
    const second: SeriesPoint = {
      ...point,
      x: 100,
      value: 0.4,
      session_id: "s2",
      epoch: 2,
    };
    renderChart([point, { ...point, x: 20, value: 0.45 }, second]);
    const lastOption = chartMock.setOption.mock.calls.at(-1)?.[0] as {
      series?: { name?: string }[];
    };
    expect(lastOption.series?.length).toBe(2);
    expect(lastOption.series?.[1]?.name).toContain("会话 2");
  });

  it("reports a dataZoom range for server-side window queries", () => {
    const onRangeChange = vi.fn();
    render(
      <MetricChart
        title="val/loss"
        lines={[{ id: "val/loss", label: "val/loss", points: [point], unit: "none" }]}
        axis="global_step"
        smoothing="none"
        smoothingWindow={5}
        logScale={false}
        showRaw={false}
        onRangeChange={onRangeChange}
      />,
    );
    const handler = chartMock.on.mock.calls
      .filter(([event]) => event === "datazoom")
      .at(-1)?.[1] as (() => void) | undefined;
    expect(handler).toBeTypeOf("function");
    (chartMock.getOption as unknown as {
      mockReturnValueOnce: (value: unknown) => void;
    }).mockReturnValueOnce({
      dataZoom: [{ startValue: 10, endValue: 30 }],
      series: [],
    });
    handler?.();
    expect(onRangeChange).toHaveBeenCalledWith({ min: 10, max: 30 });
  });
});
