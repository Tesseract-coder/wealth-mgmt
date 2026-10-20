import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { api, checksApi, signalApi, type RiskKey, type StyleKey } from "../api/client";
import { FundamentalHoldings } from "../components/FundamentalView";
import { HoldingsPatterns } from "../components/patterns";
import { HoldingsView, type HoldingsLayout } from "../components/portfolio/HoldingsView";
import { HoldingSignalsView } from "../components/SignalView";
import { TechnicalHoldings } from "../components/TechnicalHoldings";
import { ErrorState, inputClass, Loading, PageHeader, Skeleton } from "../components/ui";
import { analysisQuery } from "../lib/links";

const LAYOUT_KEY = "holdings-layout";

/** Every way to look across your stocks. The first shows cards or a table; the others are the
 *  detailed lists (once a separate Analysis page, whose links land here). */
export type HoldingsTab = "holdings" | "signals" | "technical" | "patterns" | "fundamental";
const TABS: { key: HoldingsTab; label: string }[] = [
  { key: "holdings", label: "Summary" },
  { key: "signals", label: "Signals" },
  { key: "technical", label: "Technical" },
  { key: "patterns", label: "Chart patterns" },
  { key: "fundamental", label: "Fundamental" },
];
const isTab = (v: string | null): v is HoldingsTab => TABS.some((t) => t.key === v);

function savedLayout(): HoldingsLayout {
  try {
    return localStorage.getItem(LAYOUT_KEY) === "table" ? "table" : "cards";
  } catch {
    return "cards";
  }
}

function HoldingsData({ style, risk, layout, onLayout }: { style: StyleKey | null; risk: RiskKey | null; layout: HoldingsLayout; onLayout: (l: HoldingsLayout) => void }) {
  const q = useQuery({ queryKey: ["signal-holdings", style, risk], queryFn: () => signalApi.holdings(style, risk) });
  // Shapes come separately: the table and cards show as soon as the signals are in.
  const shapes = useQuery({ queryKey: ["checks-holdings", style, risk], queryFn: () => checksApi.holdings(style, risk), enabled: q.isSuccess });
  if (q.isError) return <ErrorState title="Couldn't score your holdings" detail={q.error.message} hint="Check the backend is running, then retry." onRetry={() => void q.refetch()} />;
  if (!q.data)
    return (
      <Loading label="your holdings">
        <div className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,19rem),1fr))] gap-4">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-56 w-full" />
          ))}
        </div>
      </Loading>
    );
  return <HoldingsView d={q.data} shapes={shapes.data?.holdings} shapesLoading={shapes.isLoading} linkQuery={analysisQuery(style)} layout={layout} onLayout={onLayout} />;
}

/** Every stock holding with its signal, Score Shape, scores, weight and suggested action. */
export function Holdings() {
  const [params, setParams] = useSearchParams();
  const config = useQuery({ queryKey: ["config"], queryFn: api.config });
  const profile = useQuery({ queryKey: ["profile"], queryFn: api.profile });
  const style = (params.get("style") as StyleKey | null) ?? profile.data?.style ?? null;
  const risk = (params.get("risk") as RiskKey | null) ?? profile.data?.risk ?? null;
  const layout: HoldingsLayout = params.get("layout") === "table" ? "table" : params.get("layout") === "cards" ? "cards" : savedLayout();
  const raw = params.get("view");
  const tab: HoldingsTab = isTab(raw) ? raw : "holdings";
  const ready = (params.has("style") && params.has("risk")) || profile.isSuccess || profile.isError;
  const set = (k: "risk" | "layout" | "view", v: string) => {
    const p = new URLSearchParams(params);
    if (v) p.set(k, v);
    else p.delete(k);
    setParams(p, { replace: k === "layout" });
  };
  const onLayout = (l: HoldingsLayout) => {
    try {
      localStorage.setItem(LAYOUT_KEY, l);
    } catch {
      /* private window: the URL still remembers it */
    }
    set("layout", l);
  };
  return (
    <div className="space-y-4">
      <PageHeader
        title="Holdings"
        description="A signal and a Score Shape for each stock, and the readings behind them. Change the style at the top of any page; view them under any risk level here. Open a stock for its full story."
        actions={
          <div className="flex flex-wrap gap-3">
            <label className="text-sm">
              <span className="mb-1 block text-xs font-medium text-fg-muted">Risk</span>
              <select className={inputClass} value={risk ?? ""} onChange={(e) => set("risk", e.target.value)}>
                {config.data &&
                  Object.entries(config.data.risk_levels).map(([k, r]) => (
                    <option key={k} value={k}>
                      {r.label}
                    </option>
                  ))}
              </select>
            </label>
          </div>
        }
      />
      <div role="tablist" aria-label="Holdings views" className="flex gap-1 overflow-x-auto border-b border-border">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => set("view", t.key === "holdings" ? "" : t.key)}
            className={`-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm ${
              tab === t.key ? "border-accent font-medium text-fg" : "border-transparent text-fg-muted hover:text-fg"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === "fundamental" ? (
        <FundamentalHoldings />
      ) : !ready ? (
        <Loading label="your profile">
          <Skeleton className="h-40 w-full" />
        </Loading>
      ) : tab === "signals" ? (
        <HoldingSignalsView style={style} risk={risk} linkQuery={analysisQuery(style)} />
      ) : tab === "technical" ? (
        <TechnicalHoldings style={style} />
      ) : tab === "patterns" ? (
        <HoldingsPatterns style={style} linkQuery={(t) => `/analysis/${encodeURIComponent(t)}${analysisQuery(style, "patterns")}`} />
      ) : (
        <HoldingsData style={style} risk={risk} layout={layout} onLayout={onLayout} />
      )}
    </div>
  );
}
