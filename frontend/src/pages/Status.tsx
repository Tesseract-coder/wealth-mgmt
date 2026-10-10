import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { MarketData } from "../components/MarketData";
import { PortfolioSummaryCard } from "../components/PortfolioSummary";

/** Landing page: backend/config health plus market-data freshness. */
export function Status() {
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });
  const profile = useQuery({ queryKey: ["profile"], queryFn: api.profile });
  const config = useQuery({ queryKey: ["config"], queryFn: api.config });

  if (health.isError) {
    return (
      <div role="alert" className="rounded border border-red-300 bg-red-50 p-4 text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200">
        Backend unreachable. Start it with <code>make dev</code> and check <code>/health</code> on the backend port (BACKEND_PORT in .env, default 8000).
      </div>
    );
  }

  const risk = profile.data && config.data?.risk_levels[profile.data.risk];
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">System status</h1>
      <p className="text-sm text-slate-500">
        {health.data ? `Server time ${health.data.server_time_ist}` : "Checking…"}
      </p>
      <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Card label="Backend" value={health.data?.status ?? "…"} />
        <Card label="Database" value={health.data?.database ?? "…"} />
        <Card label="Config version" value={health.data ? String(health.data.config_version) : "…"} />
        <Card
          label="Profile"
          value={
            profile.data
              ? `${profile.data.style ? config.data?.styles[profile.data.style].label : "Style not chosen"} · ${risk?.label ?? profile.data.risk} risk`
              : "…"
          }
        />
      </dl>
      {risk && (
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Active risk limits: max {Math.round(risk.max_weight_per_stock * 100)}% per stock,{" "}
          {Math.round(risk.max_weight_per_sector * 100)}% per sector, buy threshold ≥ {risk.buy_threshold}.
        </p>
      )}
      <PortfolioSummaryCard />
      <MarketData />
    </div>
  );
}

function Card({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <dt className="text-xs uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="mt-1 font-medium">{value}</dd>
    </div>
  );
}
