import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  analysisApi,
  api,
  portfolioApi,
  type Direction,
  type FrameAnalysis,
  type Observation,
  type StyleKey,
  type TimeframeReport,
} from "../api/client";
import { FreshnessBadge } from "../components/MarketData";
import { FundamentalHoldings } from "../components/FundamentalView";
import { HoldingSignalsView } from "../components/SignalView";
import { HoldingsPatterns } from "../components/patterns";
import { StockStory } from "../components/stock/StockStory";
import { PriceChart } from "../charts/lazy";
import { Alert, Card, ErrorState, inputClass, SkeletonCard } from "../components/ui";
import { useDebounced } from "../hooks/useDebounced";
import { formatDate, formatINR } from "../lib/format";

const DIR: Record<Direction, { label: string; icon: string; cls: string }> = {
  bullish: { label: "Bullish", icon: "▲", cls: "text-good" },
  bearish: { label: "Bearish", icon: "▼", cls: "text-bad" },
  neutral: { label: "Neutral", icon: "●", cls: "text-fg-subtle" },
};

const INTERVAL_LABEL: Record<string, string> = {
  "15m": "15-minute",
  "1h": "Hourly",
  "1d": "Daily",
  "1wk": "Weekly",
  "1mo": "Monthly",
};

export function DirectionTag({ d }: { d: Direction }) {
  const s = DIR[d];
  return (
    <span className={`whitespace-nowrap text-xs font-medium ${s.cls}`}>
      {s.icon} {s.label}
    </span>
  );
}

/** Signal (with chart), technical and fundamental views of a holding or any NSE stock. */
type View = "signal" | "technical" | "patterns" | "fundamental" | "backtest";
const VIEWS: { key: View; label: string }[] = [
  { key: "signal", label: "Signal" },
  { key: "technical", label: "Technical" },
  { key: "patterns", label: "Chart patterns" },
  { key: "fundamental", label: "Fundamental" },
  { key: "backtest", label: "Backtest" },
];

/** Query string for links within the page, keeping the chosen style and view. */
export function analysisQuery(style: StyleKey | null, view: View = "signal"): string {
  const p = new URLSearchParams();
  if (style) p.set("style", style);
  if (view !== "signal") p.set("view", view);
  const s = p.toString();
  return s ? `?${s}` : "";
}

export function Technical() {
  const { ticker } = useParams();
  const [params, setParams] = useSearchParams();
  const profile = useQuery({ queryKey: ["profile"], queryFn: api.profile });
  const style = (params.get("style") as StyleKey | null) ?? profile.data?.style ?? null;
  const raw = params.get("view");
  const view: View = raw === "fundamental" || raw === "technical" || raw === "backtest" || raw === "patterns" ? raw : "signal";
  const styleKnown = params.has("style") || profile.isSuccess || profile.isError;
  const update = (next: { view?: View }) => {
    const p = new URLSearchParams(params);
    if (next.view !== undefined) {
      if (next.view === "signal") p.delete("view");
      else p.set("view", next.view);
    }
    setParams(p);
  };

  // One stock: the whole story on one page. The old tabs' content lives in its sections.
  if (ticker)
    return (
      <div className="space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <Link to={`/analysis${analysisQuery(style)}`} className="inline-flex min-h-6 items-center gap-1 py-1 text-sm text-fg-muted hover:text-fg">
            <ArrowLeft aria-hidden className="size-4" /> All holdings
          </Link>
          <div className="flex flex-wrap items-end gap-3">
            <TickerSearch style={style} view="signal" />
          </div>
        </div>
        {styleKnown ? <StockStory ticker={ticker} style={style} view={view} /> : <SkeletonCard label={ticker} />}
      </div>
    );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Analysis</h1>
          <p className="text-sm text-fg-subtle">
            Buy / Hold / Sell signals with the scores and readings behind them, under your investing style (change it at the top of the page). Open a stock for its full story.
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <TickerSearch style={style} view={view} />
        </div>
      </div>
      <div role="tablist" className="flex gap-1 overflow-x-auto border-b border-border">
        {VIEWS.map(({ key: v, label }) => (
          <button
            key={v}
            type="button"
            role="tab"
            aria-selected={view === v}
            onClick={() => update({ view: v })}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${
              view === v ? "border-accent font-medium text-fg" : "border-transparent text-fg-muted hover:text-fg"
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      {/* Wait for the saved profile so we don't analyse twice (once without, once with the style). */}
      {view === "fundamental" ? (
        <FundamentalHoldings />
      ) : !styleKnown ? (
        <SkeletonCard label="your holdings" />
      ) : view === "signal" ? (
        <HoldingSignalsView style={style} linkQuery={analysisQuery(style)} />
      ) : view === "patterns" ? (
        <HoldingsPatterns style={style} linkQuery={(t) => `/analysis/${encodeURIComponent(t)}${analysisQuery(style, "patterns")}`} />
      ) : view === "backtest" ? (
        <Card>Choose a stock with the search box above (or open one from your holdings) to replay the signal rules on its history.</Card>
      ) : (
        <HoldingsSummary style={style} />
      )}
    </div>
  );
}

function TickerSearch({ style, view }: { style: StyleKey | null; view: View }) {
  const [q, setQ] = useState("");
  const navigate = useNavigate();
  const dq = useDebounced(q.trim());
  const results = useQuery({
    queryKey: ["ref", "stock", dq],
    queryFn: () => portfolioApi.searchSecurities(dq),
    enabled: dq.length >= 2,
  });
  const go = (t: string) => {
    setQ("");
    navigate(`/analysis/${encodeURIComponent(t)}${analysisQuery(style, view)}`);
  };
  return (
    <div className="relative w-72 text-sm">
      <label>
        <span className="mb-1 block text-fg-subtle">Stock</span>
        <input
          className={inputClass}
          placeholder="Search NSE symbol or company…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && q.trim()) {
              const t = q.trim().toUpperCase();
              go(t.includes(".") || t.startsWith("^") ? t : `${t}.NS`);
            }
          }}
        />
      </label>
      {dq.length >= 2 && results.data && results.data.length > 0 && (
        <ul className="absolute z-10 mt-1 w-full overflow-hidden rounded-control border border-border bg-surface shadow-pop">
          {results.data.map((s) => (
            <li key={s.symbol}>
              <button
                type="button"
                className="w-full px-2 py-1 text-left hover:bg-surface-2"
                onClick={() => go(`${s.symbol}.NS`)}
              >
                <span className="font-mono">{s.symbol}</span> · {s.name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function HoldingsSummary({ style }: { style: StyleKey | null }) {
  const q = useQuery({ queryKey: ["tech-holdings", style], queryFn: () => analysisApi.holdings(style) });
  if (q.isError) return <ErrorState title="Couldn't summarise your holdings" detail={q.error.message} onRetry={() => void q.refetch()} />;
  if (!q.data) return <SkeletonCard label="your holdings" lines={6} />;
  if (q.data.length === 0)
    return (
      <Alert tone="info">
        No stock holdings yet. <Link className="underline" to="/import">Import your Groww file</Link>, or search for any stock above.
      </Alert>
    );
  return (
    <Card title="Your holdings">
      <p className="mb-3 text-sm text-fg-subtle">
        Uses cached prices only. If a row says Unavailable, run <b>Refresh now</b> in Settings → Data refresh.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase text-fg-subtle">
            <tr>
              <th className="py-1 pr-2">Stock</th>
              <th className="pr-2">As of</th>
              <th className="pr-2 text-right">▲ Bullish</th>
              <th className="pr-2 text-right">▼ Bearish</th>
              <th className="pr-2">Main readings</th>
              <th>Data</th>
            </tr>
          </thead>
          <tbody>
            {q.data.map((r) => (
              <tr key={r.ticker} className="border-t border-border align-top">
                <td className="py-1 pr-2">
                  <Link className="underline" to={`/analysis/${encodeURIComponent(r.ticker)}${analysisQuery(style, "technical")}`}>
                    {r.label}
                  </Link>
                  <div className="font-mono text-xs text-fg-subtle">{r.ticker}</div>
                </td>
                <td className="pr-2 whitespace-nowrap">{formatDate(r.as_of)}</td>
                <td className="pr-2 text-right tabular-nums">{r.bullish}</td>
                <td className="pr-2 text-right tabular-nums">{r.bearish}</td>
                <td className="pr-2 text-xs">
                  {r.top_bullish.slice(0, 1).map((t) => (
                    <div key={t}>▲ {t}</div>
                  ))}
                  {r.top_bearish.slice(0, 1).map((t) => (
                    <div key={t}>▼ {t}</div>
                  ))}
                </td>
                <td>
                  <FreshnessBadge f={r.freshness} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

/** Every timeframe's readings. `chart` false when the page already shows the price chart. */
export function TechnicalReportView({ ticker, style, chart = true }: { ticker: string; style: StyleKey | null; chart?: boolean }) {
  const q = useQuery({ queryKey: ["technical", ticker, style], queryFn: () => analysisApi.technical(ticker, style) });
  if (q.isError) return <ErrorState title="Couldn't read the technical readings" detail={q.error.message} onRetry={() => void q.refetch()} />;
  if (!q.data) return <SkeletonCard label={`readings for ${ticker} (the first look downloads its price history)`} lines={6} />;
  const r = q.data;
  return (
    <div className="space-y-4">
      {r.fetch_errors.map((e) => (
        <Alert key={e} tone="warning">
          Could not refresh: {e}. Showing cached data where available.
        </Alert>
      ))}
      {r.notes.map((n) => (
        <Alert key={n} tone="info">
          {n}
        </Alert>
      ))}
      {chart && <PriceChart ticker={ticker} sr={r.timeframes.find((t) => t.interval === "1d")?.analysis.levels ?? r.context.levels} />}
      {r.timeframes.map((tf) => (
        <TimeframeCard key={tf.interval} tf={tf} isIndex={ticker.startsWith("^")} />
      ))}
      <Card title="Context (daily)">
        <Readings a={r.context} />
      </Card>
    </div>
  );
}

function TimeframeCard({ tf, isIndex }: { tf: TimeframeReport; isIndex: boolean }) {
  const px = (v: number | null | undefined) =>
    v == null ? "—" : isIndex ? v.toLocaleString("en-IN", { maximumFractionDigits: 2 }) : formatINR(v);
  const v = tf.analysis.values;
  const keyVals: [string, string][] = [
    ["Close", px(tf.last_close)],
    ["SMA 50", px(v.sma50)],
    ["SMA 200", px(v.sma200)],
    ["RSI 14", v.rsi14 == null ? "—" : v.rsi14.toFixed(1)],
    ["ADX", v.adx == null ? "—" : v.adx.toFixed(1)],
    ["ATR 14", px(v.atr14)],
    ["Support", px(v.support)],
    ["Resistance", px(v.resistance)],
  ];
  return (
    <Card
      title={`${INTERVAL_LABEL[tf.interval] ?? tf.interval} · ${tf.bars} bars`}
      actions={
        <span className="flex items-center gap-2 text-sm text-fg-subtle">
          as of {tf.as_of ? (tf.as_of.length > 10 ? new Date(tf.as_of).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" }) : formatDate(tf.as_of)) : "—"}
          <FreshnessBadge f={tf.freshness} />
        </span>
      }
    >
      {tf.freshness.status !== "fresh" && <p className="mb-2 text-xs text-fg-subtle">{tf.freshness.reason}</p>}
      {tf.notes.map((n) => (
        <p key={n} className="mb-2 text-xs text-caution">
          {n}
        </p>
      ))}
      {tf.bars > 0 && (
        <dl className="mb-3 grid grid-cols-2 gap-2 text-sm sm:grid-cols-4 lg:grid-cols-8">
          {keyVals.map(([k, val]) => (
            <div key={k}>
              <dt className="text-xs text-fg-subtle">{k}</dt>
              <dd className="tabular-nums">{val}</dd>
            </div>
          ))}
        </dl>
      )}
      <Readings a={tf.analysis} />
    </Card>
  );
}

const ORDER: Direction[] = ["bullish", "bearish", "neutral"];

function Readings({ a }: { a: FrameAnalysis }) {
  const by = (d: Direction): Observation[] => a.observations.filter((o) => o.direction === d);
  return (
    <div>
      <div className="grid gap-4 md:grid-cols-3">
        {ORDER.map((d) => (
          <div key={d}>
            <h3 className="mb-1 text-sm font-semibold">
              <DirectionTag d={d} /> ({by(d).length})
            </h3>
            <ul className="space-y-1 text-sm">
              {by(d).map((o) => (
                <li key={o.key}>
                  {o.text}
                  {o.minor && <span className="ml-1 text-xs text-fg-subtle">(minor)</span>}
                </li>
              ))}
              {by(d).length === 0 && <li className="text-fg-subtle">None</li>}
            </ul>
          </div>
        ))}
      </div>
      {a.unavailable.length > 0 && (
        <div className="mt-3 text-xs text-fg-subtle">
          <span className="font-medium">Not available:</span> {a.unavailable.join("; ")}
        </div>
      )}
    </div>
  );
}
