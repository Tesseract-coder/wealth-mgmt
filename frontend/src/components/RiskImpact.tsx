import type { AppConfig, RiskConfig, RiskKey } from "../api/client";

type Row = { label: string; affects: string; value: (r: RiskConfig) => string };

const pct = (v: number) => `${Math.round(v * 100)}%`;

/**
 * What each risk setting feeds. The one check that reads a risk setting is "Debt within your risk
 * limit" (checks.yaml: health.debt_equity → risk.max_debt_to_equity); keep this list in step.
 */
const ROWS: Row[] = [
  { label: "Debt/equity limit", affects: "Check: Debt within your risk limit (Financial Health) and the Screener's pre-filter", value: (r) => (r.max_debt_to_equity === null ? "No limit" : `${r.max_debt_to_equity.toFixed(2)}×`) },
  { label: "Buy at score", affects: "When a signal says Buy / Add", value: (r) => `≥ ${r.buy_threshold}` },
  { label: "Stop-loss", affects: "Trailing stops, entry stops and targets", value: (r) => `${r.stop_loss_atr_multiple}× ATR` },
  { label: "Max per stock", affects: "Trim suggestions and the weight warning", value: (r) => pct(r.max_weight_per_stock) },
  { label: "Max per sector", affects: "Sector warnings, portfolio risks and the Screener's sector effect", value: (r) => pct(r.max_weight_per_sector) },
  { label: "Max beta", affects: "Screener pre-filter", value: (r) => (r.max_beta === null ? "No limit" : r.max_beta.toFixed(2)) },
  { label: "Min market cap", affects: "Screener pre-filter", value: (r) => `₹${r.min_market_cap_cr.toLocaleString("en-IN")} Cr` },
];

/** Every risk level side by side; cells that differ from your saved level are marked, with a word as well as weight. */
export function RiskImpact({ config, selected, saved }: { config: AppConfig; selected: RiskKey; saved: RiskKey }) {
  const levels = Object.entries(config.risk_levels) as [RiskKey, RiskConfig][];
  const base = config.risk_levels[saved];
  const changes = ROWS.filter((row) => row.value(config.risk_levels[selected]) !== row.value(base));
  return (
    <div className="space-y-3">
      {selected !== saved && (
        <p className="text-sm text-fg">
          Switching from {base.label} to {config.risk_levels[selected].label} changes {changes.length} setting{changes.length === 1 ? "" : "s"}
          {changes.some((c) => c.label === "Debt/equity limit") ? ", including the Financial Health check “Debt within your risk limit”" : ""}. Scores themselves don&apos;t change.
        </p>
      )}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[34rem] text-sm">
          <caption className="sr-only">What each risk level sets</caption>
          <thead className="text-left text-xs text-fg-muted">
            <tr className="border-b border-border">
              <th className="py-2 pr-3 font-medium">Setting</th>
              {levels.map(([k, r]) => (
                <th key={k} className={`py-2 pr-3 font-medium ${k === selected ? "text-accent-text" : ""}`}>
                  {r.label}
                  {k === saved && <span className="font-normal text-fg-subtle"> (saved)</span>}
                  {k === selected && k !== saved && <span className="font-normal"> (chosen)</span>}
                </th>
              ))}
              <th className="py-2 font-medium">What it changes</th>
            </tr>
          </thead>
          <tbody>
            {ROWS.map((row) => (
              <tr key={row.label} className="border-b border-border align-top">
                <th scope="row" className="py-2 pr-3 text-left font-medium text-fg">
                  {row.label}
                </th>
                {levels.map(([k, r]) => {
                  const differs = k === selected && selected !== saved && row.value(r) !== row.value(base);
                  return (
                    <td key={k} className={`py-2 pr-3 ${k === selected ? "bg-accent-soft/60 font-semibold text-fg" : "text-fg-muted"}`}>
                      {row.value(r)}
                      {differs && <span className="ml-1 text-xs font-normal text-accent-text">changes</span>}
                    </td>
                  );
                })}
                <td className="py-2 text-xs text-fg-muted">{row.affects}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
