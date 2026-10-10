import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, portfolioApi, type AppConfig, type Profile, type RiskKey, type StyleKey } from "../api/client";
import { Alert, Button, Card, inputClass } from "../components/ui";

/** First run: pick an investing style and risk level; the Google Sheet link is optional. */
export function Onboarding() {
  const config = useQuery({ queryKey: ["config"], queryFn: api.config });
  const profile = useQuery({ queryKey: ["profile"], queryFn: api.profile });
  if (config.isError) return <Alert tone="error">{config.error.message}</Alert>;
  if (profile.isError) return <Alert tone="error">{profile.error.message}</Alert>;
  if (!config.data || !profile.data) return <Card>Loading…</Card>;
  return <ProfileForm config={config.data} profile={profile.data} firstRun />;
}

export function ProfileForm({ config, profile, firstRun = false }: { config: AppConfig; profile: Profile; firstRun?: boolean }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [style, setStyle] = useState<StyleKey | null>(profile.style);
  const [risk, setRisk] = useState<RiskKey>(profile.risk);
  const [tw, setTw] = useState(profile.custom_technical_weight);
  const [sheet, setSheet] = useState(profile.gsheet_url ?? "");
  const [saved, setSaved] = useState(false);
  useEffect(() => setSaved(false), [style, risk, tw, sheet]);
  const sheetOk = sheet.trim() === "" || /^https:\/\/docs\.google\.com\/spreadsheets\//.test(sheet.trim());
  const save = useMutation({
    mutationFn: () =>
      api.saveProfile({ style: style!, risk, custom_technical_weight: tw, gsheet_url: sheet.trim() || null }),
    onSuccess: async (p) => {
      qc.setQueryData(["profile"], p);
      // Signals depend on the profile; let every view recompute.
      await qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "profile" && q.queryKey[0] !== "config" });
      setSaved(true);
      if (firstRun) {
        const h = await portfolioApi.holdings().catch(() => null);
        const empty = !h || (h.stocks.length === 0 && h.mf.length === 0);
        navigate(empty ? "/import" : "/");
      }
    },
  });

  return (
    <div className="space-y-4">
      {firstRun && (
        <div>
          <h1 className="text-2xl font-semibold">Welcome</h1>
          <p className="text-sm text-slate-500">
            Two choices set how holdings are scored. You can change them any time in Settings. Nothing here asks for broker logins: data
            comes only from files you export or a Google Sheet you share.
          </p>
        </div>
      )}
      <Card title="1. Investing style">
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3" role="radiogroup" aria-label="Investing style">
          {(Object.entries(config.styles) as [StyleKey, AppConfig["styles"][StyleKey]][]).map(([k, s]) => (
            <label
              key={k}
              className={`cursor-pointer rounded-lg border p-3 text-sm ${
                style === k ? "border-slate-900 ring-1 ring-slate-900 dark:border-slate-100 dark:ring-slate-100" : "border-slate-200 dark:border-slate-700"
              }`}
            >
              <input type="radio" name="style" className="sr-only" checked={style === k} onChange={() => setStyle(k)} />
              <div className="font-medium">
                {style === k ? "● " : "○ "}
                {s.label}
              </div>
              <div className="text-slate-500">{s.horizon}</div>
              <div className="mt-1 text-xs text-slate-500">
                Charts: {s.timeframes.join(", ")}
                {k !== "custom" && ` · ${Math.round(s.technical_weight * 100)}% technical / ${Math.round(s.fundamental_weight * 100)}% fundamental`}
              </div>
              {s.note && <div className="mt-1 text-xs text-amber-800 dark:text-amber-300">{s.note}</div>}
            </label>
          ))}
        </div>
        {style === "custom" && (
          <label className="mt-3 block text-sm">
            <span className="mb-1 block">
              Technical weight: {Math.round(tw * 100)}% · fundamental {Math.round((1 - tw) * 100)}%
            </span>
            <input type="range" min={0} max={1} step={0.05} value={tw} onChange={(e) => setTw(Number(e.target.value))} className="w-full max-w-md" />
          </label>
        )}
      </Card>
      <Card title="2. Risk level">
        <div className="grid gap-2 sm:grid-cols-3" role="radiogroup" aria-label="Risk level">
          {(Object.entries(config.risk_levels) as [RiskKey, AppConfig["risk_levels"][RiskKey]][]).map(([k, r]) => (
            <label
              key={k}
              className={`cursor-pointer rounded-lg border p-3 text-sm ${
                risk === k ? "border-slate-900 ring-1 ring-slate-900 dark:border-slate-100 dark:ring-slate-100" : "border-slate-200 dark:border-slate-700"
              }`}
            >
              <input type="radio" name="risk" className="sr-only" checked={risk === k} onChange={() => setRisk(k)} />
              <div className="font-medium">
                {risk === k ? "● " : "○ "}
                {r.label}
              </div>
              <ul className="mt-1 space-y-0.5 text-xs text-slate-500">
                <li>Max {Math.round(r.max_weight_per_stock * 100)}% per stock, {Math.round(r.max_weight_per_sector * 100)}% per sector</li>
                <li>Buy at score ≥ {r.buy_threshold}; stop {r.stop_loss_atr_multiple}× ATR</li>
                <li>
                  Debt/equity ≤ {r.max_debt_to_equity ?? "no limit"}, beta ≤ {r.max_beta ?? "no limit"}
                </li>
              </ul>
            </label>
          ))}
        </div>
      </Card>
      <Card title="3. Google Sheet (optional)">
        <label className="block text-sm">
          <span className="mb-1 block text-slate-500">
            Your sheet's link from the address bar. Connect and test it later in Settings → Google Sheets (docs/GOOGLE_SHEETS_SETUP.md). You can leave this blank.
          </span>
          <input className={inputClass} placeholder="https://docs.google.com/spreadsheets/d/…" value={sheet} onChange={(e) => setSheet(e.target.value)} />
        </label>
        {!sheetOk && <p className="mt-1 text-xs text-red-700 dark:text-red-400">That doesn't look like a Google Sheets link.</p>}
      </Card>
      {save.isError && <Alert tone="error">{save.error.message}</Alert>}
      {saved && !firstRun && <Alert tone="success">Saved. Signals now use the new profile.</Alert>}
      <Button disabled={!style || !sheetOk || save.isPending} onClick={() => save.mutate()}>
        {save.isPending ? "Saving…" : firstRun ? "Save and continue" : "Save profile"}
      </Button>
      {!style && <p className="text-xs text-slate-500">Choose a style to continue.</p>}
    </div>
  );
}
