import { useQuery } from "@tanstack/react-query";
import { Link, Navigate } from "react-router-dom";
import { api, REPORT_URL } from "../api/client";
import { ActionList } from "../components/ActionList";
import { PortfolioSummaryCard } from "../components/PortfolioSummary";
import { Alert } from "../components/ui";

/** KPIs, allocation, sectors, value vs Nifty 50, and what needs attention. */
export function Overview() {
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });
  const profile = useQuery({ queryKey: ["profile"], queryFn: api.profile });
  const config = useQuery({ queryKey: ["config"], queryFn: api.config });
  if (health.isError) {
    return (
      <Alert tone="error">
        Backend unreachable. Start it with <code>make dev</code> and check <code>/health</code> on the backend port (BACKEND_PORT in .env).
      </Alert>
    );
  }
  if (profile.data && !profile.data.onboarded) return <Navigate replace to="/onboarding" />;
  const risk = profile.data && config.data?.risk_levels[profile.data.risk];
  const style = profile.data?.style ? config.data?.styles[profile.data.style] : null;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold">Overview</h1>
          {style && risk && (
            <p className="text-sm text-slate-500">
              {style.label} style · {risk.label} risk (max {Math.round(risk.max_weight_per_stock * 100)}% per stock,{" "}
              {Math.round(risk.max_weight_per_sector * 100)}% per sector, buy at ≥ {risk.buy_threshold}).{" "}
              <Link className="underline" to="/settings">
                Change
              </Link>
            </p>
          )}
        </div>
        <a
          href={REPORT_URL}
          target="_blank"
          rel="noreferrer"
          className="rounded border border-slate-300 px-3 py-1.5 text-sm font-medium hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
        >
          📄 Portfolio report<span className="sr-only"> (opens in a new tab)</span>
        </a>
      </div>
      <PortfolioSummaryCard sectorLimit={risk ? risk.max_weight_per_sector : null} />
      <ActionList />
    </div>
  );
}
