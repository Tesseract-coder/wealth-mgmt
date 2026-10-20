import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Bar, FundChart, IndicatorSeries, PriceLevels } from "../api/client";
import { FundChartsBody } from "./FundCharts";
import { dateTick, topSlices } from "./PortfolioCharts";
import { buildChartData, movingAverages, nearestLevels, rsiColumn, startFor } from "./priceData";
import { thinIndices } from "./thin";

// lightweight-charts draws on canvas, which jsdom lacks: record what the chart is asked to draw.
const calls = vi.hoisted(() => ({ series: [] as { type: string; pane: number | undefined; options: Record<string, unknown> }[], priceLines: [] as { title: string; price: number }[], removed: 0 }));
vi.mock("lightweight-charts", () => {
  const series = () => ({
    setData: vi.fn(),
    createPriceLine: (o: { title: string; price: number }) => calls.priceLines.push({ title: o.title, price: o.price }),
    priceScale: () => ({ applyOptions: vi.fn() }),
  });
  return {
    CandlestickSeries: "Candlestick",
    LineSeries: "Line",
    HistogramSeries: "Histogram",
    ColorType: { Solid: "solid" },
    LineStyle: { Solid: 0, Dotted: 1, Dashed: 2 },
    createChart: () => ({
      addSeries: (type: string, options: Record<string, unknown>, pane?: number) => {
        calls.series.push({ type, pane, options });
        return series();
      },
      panes: () => [{ setStretchFactor: vi.fn() }, { setStretchFactor: vi.fn() }, { setStretchFactor: vi.fn() }],
      timeScale: () => ({ fitContent: vi.fn() }),
      remove: () => {
        // Only the live chart counts: it is rebuilt when data or toggles change.
        calls.removed++;
        calls.series = [];
        calls.priceLines = [];
      },
    }),
  };
});

const { PriceChart } = await import("./PriceChart");

const bars: Bar[] = [
  { t: "2026-10-07", open: 100, high: 105, low: 99, close: 104, volume: 1000 },
  { t: "2026-10-08", open: null, high: null, low: null, close: 103, volume: null },
  { t: "2026-10-09", open: 103, high: 108, low: 102, close: 107, volume: 1500 },
];

const ind: IndicatorSeries = {
  ticker: "X.NS",
  interval: "1d",
  t: ["2026-10-07", "2026-10-08", "2026-10-09"],
  columns: {
    sma200: [null, null, 101],
    sma20: [100, 101, 102],
    ema9: [100, 101, 103],
    rsi14: [50, 55, 60],
    macd: [0.1, 0.2, 0.3],
    macd_signal: [0.1, 0.1, 0.2],
    macd_hist: [0, 0.1, 0.1],
    supertrend: [98, 99, 100],
    supertrend_dir: [1, -1, 1],
    bb_upper: [110, 110, 111],
    bb_mid: [100, 101, 102],
    bb_lower: [90, 92, 93],
  },
};

describe("chart data", () => {
  it("builds candles, volume and gap-aware lines", () => {
    const d = buildChartData(bars, ind);
    expect(d.candles).toHaveLength(3);
    expect(d.candles[1]).toEqual({ time: "2026-10-08", open: 103, high: 103, low: 103, close: 103 }); // close-only bar
    expect(d.volume).toHaveLength(2);
    expect(d.lines.sma200?.[0]).toEqual({ time: "2026-10-07" }); // whitespace, not a made-up value
    expect(d.lines.supertrend_up?.map((p) => p.value)).toEqual([98, undefined, 100]);
    expect(d.lines.supertrend_down?.map((p) => p.value)).toEqual([undefined, 99, undefined]);
  });

  it("orders moving averages and finds RSI", () => {
    expect(movingAverages(ind)).toEqual(["sma20", "sma200", "ema9"]);
    expect(rsiColumn(ind)).toBe("rsi14");
    expect(startFor(12, new Date("2026-10-10T00:00:00Z"))).toBe("2025-10-10");
  });

  it("keeps only the nearest support and resistance levels", () => {
    const lv = [90, 95, 99, 101, 120, 130].map((price) => ({ price, kind: (price < 100 ? "support" : "resistance") as "support" | "resistance" }));
    expect(nearestLevels(lv, 100).map((l) => l.price)).toEqual([99, 95, 101, 120]);
  });

  it("folds small slices into Other", () => {
    const s = Array.from({ length: 10 }, (_, i) => ({ key: String(i), label: `S${i}`, value: 10, weight: 0.1 }));
    const t = topSlices(s, 7);
    expect(t).toHaveLength(7);
    expect(t[6]).toMatchObject({ label: "Other (4)", value: 40 });
    expect(t[6]?.weight).toBeCloseTo(0.4);
  });
});

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

const levels: PriceLevels = {
  interval: "1d", close: 107, as_of: "2026-10-09", atr: 3, multiple: 2, trailing_stop: 99.5, entry_stop: 101, stop_breached: false,
  risk_per_share: 6, targets: [{ label: "Target 1 (2R)", price: 119, pct: 11.2 }], basis: "",
};

describe("PriceChart", () => {
  beforeEach(() => {
    calls.series = [];
    calls.priceLines = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const body = url.includes("/series")
          ? ind
          : url.includes("/market/prices/")
            ? { ticker: "X.NS", interval: "1d", source: "yahoo", delayed: true, last_complete: true, freshness: { status: "fresh", reason: "" }, fetch_error: null, bars }
            : { version: 1, styles: {}, risk_levels: {}, technical: { thresholds: { rsi_overbought: 70, rsi_oversold: 30 } }, disclaimer: "" };
        return new Response(JSON.stringify(body), { status: 200 });
      }),
    );
  });
  afterEach(() => vi.unstubAllGlobals());

  it("draws candles, overlays, panes, S/R and stop/target lines, with a text legend", async () => {
    wrap(<PriceChart ticker="X.NS" levels={levels} sr={[{ price: 95, kind: "support", touches: 3 }]} />);
    expect(await screen.findByText(/Last close 107.00 on 09 Oct 2026/)).toBeInTheDocument();
    await waitFor(() => expect(calls.priceLines.some((p) => p.title === "Trailing stop")).toBe(true));
    expect(calls.series.filter((s) => s.type === "Candlestick")).toHaveLength(1);
    expect(calls.priceLines.map((p) => p.title)).toEqual(expect.arrayContaining(["Support (3×)", "Trailing stop", "Target 1 (2R)", ""]));
    const panes = new Set(calls.series.map((s) => s.pane ?? 0));
    expect([...panes].sort()).toEqual([0, 1, 2]); // price, RSI, MACD
    const legend = screen.getByRole("list", { name: "Chart legend" });
    expect(legend).toHaveTextContent("SMA 20");
    expect(legend).toHaveTextContent("Trailing stop");
    expect(screen.getByText(/dashed lines at 30 and 70/)).toBeInTheDocument(); // RSI bands from config
  });

  it("toggles overlays and hides stops on another timeframe", async () => {
    wrap(<PriceChart ticker="X.NS" levels={levels} />);
    await screen.findByText(/Last close/);
    fireEvent.click(screen.getByLabelText("Supertrend"));
    await waitFor(() => expect(screen.getByRole("list", { name: "Chart legend" })).toHaveTextContent("Supertrend: up"));
    fireEvent.click(screen.getByLabelText("RSI pane"));
    fireEvent.click(screen.getByLabelText("MACD pane"));
    await waitFor(() => expect(screen.queryByText(/Lower panes/)).not.toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Weekly" }));
    expect(await screen.findByText(/drawn on the daily chart/)).toBeInTheDocument();
  });

  it("opens on the style's timeframe so the stop is visible", async () => {
    wrap(<PriceChart ticker="X.NS" levels={{ ...levels, interval: "1wk" }} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Weekly" })).toHaveAttribute("aria-pressed", "true"));
  });
});

describe("Fund charts", () => {
  const c: FundChart = {
    code: "1",
    benchmark: { ticker: "^NSEI", label: "Nifty 50" },
    dates: ["2021-10-08", "2026-10-09"],
    fund: [100, 180.5],
    bench: [100, 160.2],
    rolling: [{ years: 3, starts: ["2021-01-01", "2021-02-01", "2021-03-01", "2021-04-01"], fund: [12, 11, 9, 10], benchmark: [10, 10, 10, 10] }],
    notes: ["Nifty 50 is a price index (no dividends), so it understates the index return"],
  };

  it("summarises growth and how often the fund beat its benchmark", () => {
    render(<FundChartsBody c={c} />);
    expect(screen.getByText("₹100 invested on 08 Oct 2021 is now ₹180.5 in the fund and ₹160.2 in Nifty 50: the fund is ahead.")).toBeInTheDocument();
    expect(screen.getByText(/Beat Nifty 50 in 2 of 4 3-year windows \(50%\); the gap ranged from −1.0 pp to \+2.0 pp/)).toBeInTheDocument();
    expect(screen.getByText(/worst fall in this period was 0.0%/)).toBeInTheDocument(); // only two points, both new highs
    expect(screen.getByText(/price index/)).toBeInTheDocument();
  });

  it("says why there's no chart", () => {
    render(<FundChartsBody c={{ ...c, fund: [], dates: [], bench: [], rolling: [], notes: ["No NAV history downloaded yet"] }} />);
    expect(screen.getByText(/No NAV history downloaded yet/)).toBeInTheDocument();
  });
});

describe("Charts load on first use", () => {
  it("shows a loading placeholder, then the chart", async () => {
    const { SectorBars } = await import("./lazy");
    render(<SectorBars items={[{ key: "IT", label: "IT", value: 100, weight: 0.5 }]} limit={0.4} />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading the chart…");
    expect(await screen.findByText(/Above limit: IT 50%/, {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});

describe("thinIndices", () => {
  it("keeps short lines whole", () => {
    expect(thinIndices(5, [[1, 2, 3, 4, 5]], 10)).toEqual([0, 1, 2, 3, 4]);
  });

  it("draws at most about max points, always with the ends and each line's high and low", () => {
    const n = 1230;
    const a = Array.from({ length: n }, (_, i) => Math.sin(i / 50));
    a[617] = -9; // the deepest fall, between the evenly spread points
    const b: (number | null)[] = Array.from({ length: n }, (_, i) => (i % 2 ? null : i));
    b[1001] = 5000; // the peak, on an odd index that a plain stride would skip
    const idx = thinIndices(n, [a, b], 300);
    expect(idx.length).toBeLessThanOrEqual(300 + 4);
    expect(idx[0]).toBe(0);
    expect(idx.at(-1)).toBe(n - 1);
    expect(idx).toContain(617);
    expect(idx).toContain(1001);
    expect([...idx].sort((x, y) => x - y)).toEqual(idx);
  });
});

describe("dateTick", () => {
  it("shows day and month over a short span, month and year over a long one", () => {
    expect(dateTick(["2026-09-24", "2026-10-20"])("2026-10-05")).toBe("05 Oct");
    expect(dateTick(["2024-10-20", "2026-10-20"])("2026-10-05")).toBe("Oct 2026");
  });
});
