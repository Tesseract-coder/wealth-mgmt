import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { Link, Navigate, useParams, useSearchParams } from "react-router-dom";
import {
  analysisApi,
  api,
  type Direction,
  type FrameAnalysis,
  type Observation,
  type StyleKey,
  type TimeframeReport,
} from "../api/client";
import { FreshnessBadge } from "../components/MarketData";
import { StockStory } from "../components/stock/StockStory";
import { PriceChart } from "../charts/lazy";
import { Alert, Card, ErrorState, SkeletonCard } from "../components/ui";
import { formatDate, formatINR } from "../lib/format";
import type { AnalysisView } from "../lib/links";

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

/** One stock's story page (any NSE stock, held or not). */
type View = AnalysisView;

export function Technical() {
  const { ticker } = useParams();
  const [params] = useSearchParams();
  const profile = useQuery({ queryKey: ["profile"], queryFn: api.profile });
  const style = (params.get("style") as StyleKey | null) ?? profile.data?.style ?? null;
  const raw = params.get("view");
  const view: View = raw === "fundamental" || raw === "technical" || raw === "backtest" || raw === "patterns" ? raw : "signal";
  const styleKnown = params.has("style") || profile.isSuccess || profile.isError;

  // One stock: the whole story on one page. The old tabs' content lives in its sections.
  if (ticker)
    return (
      <div className="space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <Link to={`/holdings${style ? `?style=${style}` : ""}`} className="inline-flex min-h-6 items-center gap-1 py-1 text-sm text-fg-muted hover:text-fg">
            <ArrowLeft aria-hidden className="size-4" /> All holdings
          </Link>
        </div>
        {styleKnown ? <StockStory ticker={ticker} style={style} view={view} /> : <SkeletonCard label={ticker} />}
      </div>
    );

  // The holdings lists moved to the Holdings page; old links land on the matching view there.
  const target = view === "signal" ? "signals" : view === "backtest" ? null : view;
  const p = new URLSearchParams(params);
  p.delete("view");
  if (target) p.set("view", target);
  const qs = p.toString();
  return <Navigate replace to={`/holdings${qs ? `?${qs}` : ""}`} />;
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
