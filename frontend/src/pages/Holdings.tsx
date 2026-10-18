import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { api, checksApi, signalApi, type RiskKey, type StyleKey } from "../api/client";
import { HoldingsView, type HoldingsLayout } from "../components/portfolio/HoldingsView";
import { ErrorState, inputClass, Loading, PageHeader, Skeleton } from "../components/ui";
import { analysisQuery } from "./Technical";

const LAYOUT_KEY = "holdings-layout";

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
  const ready = (params.has("style") && params.has("risk")) || profile.isSuccess || profile.isError;
  const set = (k: "risk" | "layout", v: string) => {
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
        description="A signal and a Score Shape for each stock. Change the style at the top of any page; view them under any risk level here."
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
      {ready ? (
        <HoldingsData style={style} risk={risk} layout={layout} onLayout={onLayout} />
      ) : (
        <Loading label="your profile">
          <Skeleton className="h-40 w-full" />
        </Loading>
      )}
    </div>
  );
}
