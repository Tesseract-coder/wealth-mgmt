import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { api, type RiskKey, type StyleKey } from "../api/client";
import { HoldingSignalsView } from "../components/SignalView";
import { Card, inputClass } from "../components/ui";
import { analysisQuery } from "./Technical";

/** Every stock holding with its signal, scores, weight and suggested action. */
export function Holdings() {
  const [params, setParams] = useSearchParams();
  const config = useQuery({ queryKey: ["config"], queryFn: api.config });
  const profile = useQuery({ queryKey: ["profile"], queryFn: api.profile });
  const style = (params.get("style") as StyleKey | null) ?? profile.data?.style ?? null;
  const risk = (params.get("risk") as RiskKey | null) ?? profile.data?.risk ?? null;
  const ready = (params.has("style") && params.has("risk")) || profile.isSuccess || profile.isError;
  const set = (k: "style" | "risk", v: string) => {
    const p = new URLSearchParams(params);
    if (v) p.set(k, v);
    else p.delete(k);
    setParams(p);
  };
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Holdings</h1>
          <p className="text-sm text-slate-500">
            A Buy / Hold / Sell signal for each stock, with the rule and readings behind it. View them under any style or
            risk level; your saved profile is the default.
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <label className="text-sm">
            <span className="mb-1 block text-slate-500">Style</span>
            <select className={inputClass} value={style ?? ""} onChange={(e) => set("style", e.target.value)}>
              <option value="">Your saved style</option>
              {config.data &&
                Object.entries(config.data.styles).map(([k, s]) => (
                  <option key={k} value={k}>
                    {s.label}
                  </option>
                ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-slate-500">Risk</span>
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
      </div>
      {ready ? <HoldingSignalsView style={style} risk={risk} linkQuery={analysisQuery(style)} /> : <Card>Loading…</Card>}
    </div>
  );
}
