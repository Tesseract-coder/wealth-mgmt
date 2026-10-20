import { useQuery } from "@tanstack/react-query";
import {
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  HistogramSeries,
  LineSeries,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type SeriesMarker,
  type SeriesType,
  type Time,
} from "lightweight-charts";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, chartApi, patternApi, type ChartInterval, type Direction, type PatternMatch, type PriceLevels } from "../api/client";
import { FreshnessBadge } from "../components/MarketData";
import { Alert, Button, Card, ErrorState, Loading, Skeleton } from "../components/ui";
import { useIsDark } from "../hooks/useIsDark";
import { formatDate, formatNumber } from "../lib/format";
import { palette, seriesColor } from "./palette";
import { buildChartData, movingAverages, nearestLevels, rsiColumn, startFor, type ChartData } from "./priceData";

export interface SRLevel {
  price: number;
  kind: "support" | "resistance";
  touches: number;
}

type Overlay = "ma" | "bollinger" | "supertrend" | "sr" | "stops" | "patterns" | "volume" | "rsi" | "macd";

/** A pattern to draw on its own, from a card's "Show on the price chart"; `n` makes each click new. */
export interface PatternFocus {
  key: string;
  name: string;
  interval: ChartInterval;
  n: number;
}

const OVERLAYS: { key: Overlay; label: string }[] = [
  { key: "ma", label: "Moving averages" },
  { key: "bollinger", label: "Bollinger bands" },
  { key: "supertrend", label: "Supertrend" },
  { key: "sr", label: "Support / resistance" },
  { key: "stops", label: "Stop-loss & targets" },
  { key: "patterns", label: "Chart patterns" },
  { key: "volume", label: "Volume" },
  { key: "rsi", label: "RSI pane" },
  { key: "macd", label: "MACD pane" },
];

const RANGES: { months: number; label: string }[] = [
  { months: 6, label: "6M" },
  { months: 12, label: "1Y" },
  { months: 36, label: "3Y" },
  { months: 60, label: "5Y" },
];

const INTERVALS: { key: ChartInterval; label: string }[] = [
  { key: "1d", label: "Daily" },
  { key: "1wk", label: "Weekly" },
  { key: "1mo", label: "Monthly" },
];

const MA_LABEL = (k: string) => `${k.slice(0, 3).toUpperCase()} ${k.slice(3)}`;

export function PriceChart({
  ticker,
  levels,
  sr = [],
  panes = true,
  embedded = false,
  focus = null,
}: {
  ticker: string;
  levels?: PriceLevels | null;
  sr?: SRLevel[];
  /** Open with the RSI and MACD panes showing (the stock page starts with them collapsed). */
  panes?: boolean;
  /** Inside a page section that already has the heading and the card around it. */
  embedded?: boolean;
  /** Draw this one pattern (switching to its timeframe). */
  focus?: PatternFocus | null;
}) {
  const [interval, setIv] = useState<ChartInterval>("1d");
  // Open on the style's timeframe (where the stop and targets live) once the signal arrives,
  // unless you've already picked one.
  const picked = useRef(false);
  useEffect(() => {
    const iv = levels?.interval;
    if (!picked.current && iv && INTERVALS.some((i) => i.key === iv)) {
      picked.current = true;
      setIv(iv as ChartInterval);
    }
  }, [levels?.interval]);
  const [months, setMonths] = useState(12);
  const [on, setOn] = useState<Set<Overlay>>(() => new Set<Overlay>(["ma", "sr", "stops", "volume", ...(panes ? (["rsi", "macd"] as const) : [])]));
  const [only, setOnly] = useState<PatternFocus | null>(null);
  useEffect(() => {
    if (!focus) return;
    picked.current = true;
    setIv(focus.interval);
    setOn((s) => new Set([...s, "patterns" as const]));
    setOnly(focus);
  }, [focus?.n]); // eslint-disable-line react-hooks/exhaustive-deps
  const start = useMemo(() => startFor(months), [months]);
  const config = useQuery({ queryKey: ["config"], queryFn: api.config });
  const prices = useQuery({
    queryKey: ["chart-prices", ticker, interval, start],
    queryFn: () => chartApi.prices(ticker, interval, start),
  });
  const ind = useQuery({
    queryKey: ["chart-ind", ticker, interval, start],
    queryFn: () => chartApi.indicators(ticker, interval, start),
    enabled: prices.isSuccess, // the prices call downloads the history if it isn't cached
  });
  const pats = useQuery({
    queryKey: ["patterns", ticker, interval],
    queryFn: () => patternApi.stock(ticker, interval),
    enabled: on.has("patterns") && prices.isSuccess,
  });
  const showOnly = only && only.interval === interval ? only : null;
  const drawn = on.has("patterns") ? (pats.data?.patterns ?? []).filter((m) => !showOnly || m.key === showOnly.key) : [];
  const data = useMemo(() => (prices.data ? buildChartData(prices.data.bars, ind.data) : null), [prices.data, ind.data]);
  const mas = movingAverages(ind.data);
  const rsiKey = rsiColumn(ind.data);
  const th = config.data?.technical?.thresholds;
  const toggle = (k: Overlay) =>
    setOn((s) => {
      const n = new Set(s);
      if (n.has(k)) n.delete(k);
      else n.add(k);
      return n;
    });

  const last = data?.candles.at(-1);
  // Stop and targets are worked out on the style's timeframe; only draw them on that one.
  const showStops = !!levels && on.has("stops") && levels.interval === interval;
  return (
    <Card
      title={embedded ? undefined : "Price chart"}
      className={embedded ? "border-0! bg-transparent! p-0! shadow-none!" : ""}
      actions={
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <Segmented options={INTERVALS.map((i) => ({ key: i.key, label: i.label }))} value={interval} onChange={(v) => {
              picked.current = true;
              setIv(v as ChartInterval);
            }} label="Interval" />
          <Segmented options={RANGES.map((r) => ({ key: String(r.months), label: r.label }))} value={String(months)} onChange={(v) => setMonths(Number(v))} label="Range" />
        </div>
      }
    >
      <fieldset className="mb-3 flex flex-wrap gap-x-4 gap-y-1 text-sm">
        <legend className="sr-only">Overlays</legend>
        {OVERLAYS.map((o) => (
          <label key={o.key} className="inline-flex items-center gap-1">
            <input type="checkbox" checked={on.has(o.key)} onChange={() => toggle(o.key)} />
            {o.label}
          </label>
        ))}
      </fieldset>
      {prices.isError && <ErrorState title="Couldn't load the price history" detail={prices.error.message} hint="Yahoo Finance may not have answered. Retry, or run Refresh now in Settings." onRetry={() => void prices.refetch()} />}
      {prices.data?.fetch_error && <Alert tone="warning">Could not refresh: {prices.data.fetch_error}. Showing cached bars.</Alert>}
      {!data ? (
        <Loading label="the price history">
          <Skeleton className="h-96 w-full" />
        </Loading>
      ) : data.candles.length === 0 ? (
        <Alert tone="info">No price history for {ticker} yet. Run Refresh now in Settings, or check the ticker.</Alert>
      ) : (
        <>
          <ChartCanvas data={data} on={on} mas={mas} rsiKey={rsiKey} levels={showStops ? levels : null} sr={on.has("sr") && last ? nearestLevels(sr, last.close) : []} bands={th ? [th.rsi_oversold, th.rsi_overbought] : null} patterns={drawn} focused={!!showOnly} />
          <Legend on={on} mas={mas} showStops={showStops} hasSr={sr.length > 0 && on.has("sr")} patterns={drawn} focused={!!showOnly} />
          {on.has("patterns") && (
            <p className="mt-2 flex flex-wrap items-center gap-2 text-xs text-fg-muted">
              {showOnly ? (
                <>
                  <span>
                    Showing the <b className="text-fg">{showOnly.name}</b> with its breakout and target.
                  </span>
                  <Button variant="ghost" size="sm" onClick={() => setOnly(null)}>
                    Show all patterns
                  </Button>
                </>
              ) : pats.data ? (
                <span>
                  {drawn.length ? `Patterns drawn: ${drawn.map((m) => m.name).join(", ")}.` : "No chart pattern on this timeframe right now."} See the Chart patterns section for what each means.
                </span>
              ) : pats.isError ? (
                <span>Couldn't scan for patterns.</span>
              ) : (
                <span>Looking for patterns…</span>
              )}
            </p>
          )}
          <p className="mt-2 flex flex-wrap items-center gap-2 text-xs text-fg-subtle">
            {last && (
              <span>
                Last close {formatNumber(last.close)} on {formatDate(last.time)}. {data.candles.length} bars.
              </span>
            )}
            {prices.data && <FreshnessBadge f={prices.data.freshness} />}
            <span>Yahoo Finance end-of-day data (delayed). Indicators are computed on the full history.</span>
            {levels && on.has("stops") && levels.interval !== interval && (
              <span>Stop and targets are drawn on the {INTERVALS.find((i) => i.key === levels.interval)?.label.toLowerCase() ?? levels.interval} chart, the style's timeframe.</span>
            )}
          </p>
        </>
      )}
    </Card>
  );
}

function Segmented({ options, value, onChange, label }: { options: { key: string; label: string }[]; value: string; onChange: (v: string) => void; label: string }) {
  return (
    <div role="group" aria-label={label} className="inline-flex overflow-hidden rounded border border-border-strong">
      {options.map((o) => (
        <button
          key={o.key}
          type="button"
          aria-pressed={value === o.key}
          onClick={() => onChange(o.key)}
          className={`px-2 py-1 ${value === o.key ? "bg-accent text-accent-fg" : "text-fg-muted hover:bg-surface-2 hover:text-fg"}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function Legend({ on, mas, showStops, hasSr, patterns, focused }: { on: Set<Overlay>; mas: string[]; showStops: boolean; hasSr: boolean; patterns: PatternMatch[]; focused: boolean }) {
  const p = palette(useIsDark());
  const items: { label: string; color: string; dashed?: boolean }[] = [];
  if (on.has("ma")) mas.forEach((m, i) => items.push({ label: MA_LABEL(m), color: seriesColor(p, i) }));
  if (on.has("bollinger")) items.push({ label: "Bollinger (upper / mid / lower)", color: p.neutral });
  if (on.has("supertrend")) items.push({ label: "Supertrend: up", color: p.up }, { label: "Supertrend: down", color: p.down });
  if (hasSr) items.push({ label: "Support", color: p.support, dashed: true }, { label: "Resistance", color: p.resistance, dashed: true });
  if (showStops) items.push({ label: "Trailing stop", color: p.stop, dashed: true }, { label: "Targets", color: p.target, dashed: true });
  for (const d of ["bullish", "bearish", "neutral"] as const)
    if (patterns.some((m) => m.direction === d)) items.push({ label: `${d[0]!.toUpperCase()}${d.slice(1)} pattern lines`, color: patternColour(p, d), dashed: true });
  if (focused && patterns.length) items.push({ label: "Pattern breakout & target", color: p.neutral, dashed: true });
  if (!items.length) return null;
  return (
    <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs" aria-label="Chart legend">
      {items.map((it) => (
        <li key={it.label} className="inline-flex items-center gap-1">
          <span aria-hidden="true" className="inline-block w-4 border-t-2" style={{ borderColor: it.color, borderStyle: it.dashed ? "dashed" : "solid" }} />
          {it.label}
        </li>
      ))}
    </ul>
  );
}

function ChartCanvas({
  data,
  on,
  mas,
  rsiKey,
  levels,
  sr,
  bands,
  patterns,
  focused,
}: {
  data: ChartData;
  on: Set<Overlay>;
  mas: string[];
  rsiKey: string | null;
  levels: PriceLevels | null | undefined;
  sr: SRLevel[];
  bands: [number, number] | null;
  patterns: PatternMatch[];
  focused: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const isDark = useIsDark();
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const p = palette(isDark);
    const chart: IChartApi = createChart(el, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: p.bg }, textColor: p.text, panes: { separatorColor: p.grid } },
      grid: { vertLines: { color: p.grid }, horzLines: { color: p.grid } },
      rightPriceScale: { borderColor: p.grid },
      timeScale: { borderColor: p.grid },
      localization: { locale: "en-IN" },
    });
    const line = (pane: number, color: string, points: ChartData["lines"][string] | undefined, opts: { dashed?: boolean; width?: 1 | 2 } = {}) => {
      if (!points) return null;
      const s = chart.addSeries(
        LineSeries,
        { color, lineWidth: opts.width ?? 1, lineStyle: opts.dashed ? LineStyle.Dashed : LineStyle.Solid, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false },
        pane,
      );
      s.setData(points);
      return s;
    };

    const candles: ISeriesApi<SeriesType> = chart.addSeries(CandlestickSeries, {
      upColor: p.up,
      downColor: p.down,
      wickUpColor: p.up,
      wickDownColor: p.down,
      borderVisible: false,
    });
    candles.setData(data.candles);

    if (on.has("volume") && data.volume.length) {
      const vol = chart.addSeries(HistogramSeries, { priceScaleId: "vol", priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false });
      vol.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
      vol.setData(data.volume.map((v) => ({ time: v.time, value: v.value, color: `${v.up ? p.up : p.down}55` })));
    }
    if (on.has("ma")) mas.forEach((m, i) => line(0, seriesColor(p, i), data.lines[m]));
    if (on.has("bollinger")) {
      line(0, p.neutral, data.lines.bb_upper, { dashed: true });
      line(0, p.neutral, data.lines.bb_mid);
      line(0, p.neutral, data.lines.bb_lower, { dashed: true });
    }
    if (on.has("supertrend")) {
      line(0, p.up, data.lines.supertrend_up, { width: 2 });
      line(0, p.down, data.lines.supertrend_down, { width: 2 });
    }
    for (const lv of sr) {
      candles.createPriceLine({
        price: lv.price,
        color: lv.kind === "support" ? p.support : p.resistance,
        lineStyle: LineStyle.Dashed,
        lineWidth: 1,
        axisLabelVisible: true,
        title: `${lv.kind === "support" ? "Support" : "Resistance"} (${lv.touches}×)`,
      });
    }
    if (levels) {
      candles.createPriceLine({ price: levels.trailing_stop, color: p.stop, lineStyle: LineStyle.Dashed, lineWidth: 2, axisLabelVisible: true, title: "Trailing stop" });
      for (const t of levels.targets) {
        candles.createPriceLine({ price: t.price, color: p.target, lineStyle: LineStyle.Dotted, lineWidth: 1, axisLabelVisible: true, title: t.label });
      }
    }

    // Chart patterns: their lines, labelled points, and (for one pattern) breakout and target.
    const first = data.candles[0]?.time;
    const markers: SeriesMarker<Time>[] = [];
    const candleAt = new Map(data.candles.map((c) => [c.time, c]));
    for (const m of patterns) {
      const colour = patternColour(p, m.direction);
      for (const ln of m.lines) {
        const pts = first ? clipLine(ln.points.map((pt) => ({ time: pt.t.slice(0, 10), value: pt.price })), first) : [];
        if (pts.length >= 2) line(0, colour, pts, { dashed: ln.kind !== "curve", width: 2 });
      }
      for (const pt of m.points) {
        const time = pt.t.slice(0, 10);
        const c = candleAt.get(time);
        if (!pt.label || !c) continue;
        const above = pt.price >= (c.high + c.low) / 2;
        markers.push({ time, position: above ? "aboveBar" : "belowBar", color: colour, shape: "circle", text: pt.label });
      }
      if (focused) {
        if (m.breakout != null) candles.createPriceLine({ price: m.breakout, color: p.neutral, lineStyle: LineStyle.Solid, lineWidth: 1, axisLabelVisible: true, title: m.direction === "neutral" ? "Breaks up above" : "Pattern breakout" });
        if (m.target != null) candles.createPriceLine({ price: m.target, color: colour, lineStyle: LineStyle.Dotted, lineWidth: 2, axisLabelVisible: true, title: "Pattern target" });
      }
    }
    if (markers.length) createSeriesMarkers(candles, markers.sort((a, b) => (String(a.time) < String(b.time) ? -1 : 1)));

    let pane = 1;
    if (on.has("rsi") && rsiKey) {
      const s = line(pane, seriesColor(p, 2), data.lines[rsiKey], { width: 2 });
      if (s && bands) {
        for (const b of bands) s.createPriceLine({ price: b, color: p.neutral, lineStyle: LineStyle.Dashed, lineWidth: 1, axisLabelVisible: true, title: "" });
      }
      pane++;
    }
    if (on.has("macd") && data.lines.macd) {
      const hist = chart.addSeries(HistogramSeries, { priceLineVisible: false, lastValueVisible: false }, pane);
      hist.setData(
        (data.lines.macd_hist ?? []).map((pt) => (pt.value === undefined ? { time: pt.time } : { time: pt.time, value: pt.value, color: pt.value >= 0 ? `${p.up}99` : `${p.down}99` })),
      );
      line(pane, seriesColor(p, 0), data.lines.macd, { width: 2 });
      line(pane, seriesColor(p, 1), data.lines.macd_signal);
      pane++;
    }
    // Price pane three times the height of each indicator pane.
    chart.panes().forEach((pn, i) => pn.setStretchFactor(i === 0 ? 3 : 1));
    chart.timeScale().fitContent();
    return () => chart.remove();
    // The props are rebuilt on every render; redraw only when their contents change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, isDark, JSON.stringify([[...on], mas, rsiKey, levels, sr, bands, patterns.map((m) => [m.key, m.end]), focused])]);

  const panes = 1 + (on.has("rsi") && rsiKey ? 1 : 0) + (on.has("macd") && data.lines.macd ? 1 : 0);
  return (
    <div>
      <div ref={ref} style={{ height: 380 + (panes - 1) * 120 }} role="img" aria-label="Candlestick price chart with the selected indicators" />
      {panes > 1 && (
        <p className="mt-1 text-xs text-fg-subtle">
          Lower panes: {[on.has("rsi") && rsiKey ? `RSI (${bands ? `dashed lines at ${bands[0]} and ${bands[1]}` : ""})` : null, on.has("macd") && data.lines.macd ? "MACD line, signal line and histogram" : null].filter(Boolean).join(" · ")}
        </p>
      )}
    </div>
  );
}

const patternColour = (p: ReturnType<typeof palette>, d: Direction) => (d === "bullish" ? p.up : d === "bearish" ? p.down : seriesColor(p, 0));

/** A pattern line cut to start at the chart's first bar (the chart may show less history). */
function clipLine(points: { time: string; value: number }[], first: string): { time: string; value: number }[] {
  const pts = points.filter((pt, i) => i === 0 || pt.time > points[i - 1]!.time);
  const k = pts.findIndex((pt) => pt.time >= first);
  if (k <= 0) return k === 0 ? pts : [];
  const a = pts[k - 1]!;
  const b = pts[k]!;
  if (b.time === first) return pts.slice(k);
  const f = (Date.parse(first) - Date.parse(a.time)) / (Date.parse(b.time) - Date.parse(a.time));
  return [{ time: first, value: a.value + (b.value - a.value) * f }, ...pts.slice(k)];
}
