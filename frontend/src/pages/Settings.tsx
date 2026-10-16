import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { api, dashboardApi, EXPORTS, REPORT_URL, sheetsApi, type Threshold, type Thresholds } from "../api/client";
import { GoogleSheetsSettings, SheetsExportButton } from "../components/GoogleSheets";
import { MarketData } from "../components/MarketData";
import { Download, FileText, MessageSquare } from "lucide-react";
import { Alert, Button, buttonClass, Card, ErrorState, inputClass, PageHeader, Skeleton, SkeletonCard, Stat } from "../components/ui";
import { feedbackUrl } from "../lib/feedback";
import { ProfileForm } from "./Onboarding";

const TABS = [
  { key: "profile", label: "Profile" },
  { key: "thresholds", label: "Thresholds" },
  { key: "data", label: "Data refresh" },
  { key: "sheets", label: "Google Sheets" },
  { key: "export", label: "Export" },
  { key: "system", label: "System" },
] as const;
type Tab = (typeof TABS)[number]["key"];

export function Settings() {
  const [tab, setTab] = useState<Tab>(() => {
    const h = window.location.hash.slice(1);
    return (TABS.find((t) => t.key === h)?.key ?? "profile") as Tab;
  });
  const config = useQuery({ queryKey: ["config"], queryFn: api.config });
  const profile = useQuery({ queryKey: ["profile"], queryFn: api.profile });
  const pick = (t: Tab) => {
    setTab(t);
    window.history.replaceState(null, "", `#${t}`);
  };
  return (
    <div className="space-y-4">
      <PageHeader title="Settings" description="Your profile, thresholds, data refresh, Google Sheets, exports and system status." />
      <div role="tablist" aria-label="Settings sections" className="flex gap-1 overflow-x-auto border-b border-border">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => pick(t.key)}
            className={`-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium ${tab === t.key ? "border-accent text-fg" : "border-transparent text-fg-muted hover:text-fg"}`}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === "profile" &&
        (config.error || profile.error ? (
          <ErrorState
            title="Couldn't load your profile"
            detail={(config.error ?? profile.error)?.message ?? ""}
            onRetry={() => void Promise.all([config.refetch(), profile.refetch()])}
          />
        ) : config.data && profile.data ? (
          <ProfileForm config={config.data} profile={profile.data} />
        ) : (
          <SkeletonCard label="your profile" lines={6} />
        ))}
      {tab === "thresholds" && <ThresholdsEditor />}
      {tab === "data" && <MarketData />}
      {tab === "sheets" && <GoogleSheetsSettings />}
      {tab === "export" && <ExportCard />}
      {tab === "system" && <SystemCard />}
    </div>
  );
}

const LINK_BTN = buttonClass("secondary", "md");

function ExportCard() {
  const sheets = useQuery({ queryKey: ["sheets"], queryFn: sheetsApi.status });
  return (
    <div className="space-y-4">
      <Card title="Portfolio report (HTML / PDF)">
        <p className="mb-3 text-sm text-fg-subtle">
          One page with your summary, actions, allocation, every stock and fund with its signal and reasons, the top screener ideas,
          data freshness and the disclaimer. Open it and use <strong>Print / Save as PDF</strong> for a PDF (it is laid out for A4
          landscape, with the disclaimer on every page). Built from cached data, so it opens in a few seconds.
        </p>
        <div className="flex flex-wrap gap-2">
          <a href={REPORT_URL} target="_blank" rel="noreferrer" className={LINK_BTN}>
            <FileText aria-hidden className="size-4" />
            Open report<span className="sr-only"> (opens in a new tab)</span>
          </a>
          <a href={`${REPORT_URL}?download=true`} download className={LINK_BTN}>
            <Download aria-hidden className="size-4" />
            Download HTML
          </a>
        </div>
      </Card>
      <Card title="Download">
        <p className="mb-3 text-sm text-fg-subtle">
          Signals with their scores and reasons, under your saved profile. Each file ends with the date and the disclaimer. Screener
          ideas download from the Screener page (Download CSV on any screen).
        </p>
        <div className="flex flex-wrap gap-2">
          {EXPORTS.map((e) => (
            <a key={e.href} href={e.href} download className={LINK_BTN}>
              <Download aria-hidden className="size-4" />
              {e.label}
            </a>
          ))}
        </div>
      </Card>
      <Card title="Google Sheets">
        <p className="mb-3 text-sm text-fg-subtle">Writes the Summary, stock, fund and Screener tabs of your sheet. Set it up under the Google Sheets tab.</p>
        <SheetsExportButton status={sheets.data} />
      </Card>
    </div>
  );
}

function SystemCard() {
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });
  if (health.isError)
    return <ErrorState title="The backend isn't answering" detail={health.error.message} hint="Start it with make dev, then retry." onRetry={() => void health.refetch()} />;
  const h = health.data;
  return (
    <Card title="System">
      <dl className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
        {[
          ["Backend", h?.status],
          ["Database", h?.database],
          ["Config version", h ? String(h.config_version) : undefined],
          ["Server time", h?.server_time_ist],
          ["App version", __APP_VERSION__],
        ].map(([k, v]) => (
          <Stat key={k} label={k!} value={v ?? <Skeleton className="h-5 w-20" />} />
        ))}
      </dl>
      <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-border pt-4 text-sm text-fg-muted">
        <a href={feedbackUrl("/settings")} target="_blank" rel="noreferrer" className={LINK_BTN}>
          <MessageSquare aria-hidden className="size-4" />
          Send feedback<span className="sr-only"> (opens a new GitHub issue in a new tab)</span>
        </a>
        <span>Opens a GitHub issue with the app version filled in. Describe the problem; don't paste your holdings or values.</span>
      </div>
    </Card>
  );
}

// ------------------------------------------------------------------ thresholds

/** Shown in the units people think in: fractions as %, the rest as plain numbers. */
export function toDisplay(t: Pick<Threshold, "unit">, v: number | null): string {
  if (v === null) return "";
  return t.unit === "fraction" ? String(+(v * 100).toFixed(4)) : String(v);
}

export function fromDisplay(t: Pick<Threshold, "unit" | "nullable">, s: string): number | null | "invalid" {
  const x = s.trim();
  if (x === "") return t.nullable ? null : "invalid";
  const n = Number(x);
  if (!Number.isFinite(n)) return "invalid";
  return t.unit === "fraction" ? +(n / 100).toFixed(6) : n;
}

const UNIT: Record<Threshold["unit"], string> = { fraction: "%", score: "/100", x: "× ATR", cr: "₹ Cr", ratio: "" };

function ThresholdsEditor() {
  const q = useQuery({ queryKey: ["thresholds"], queryFn: dashboardApi.thresholds });
  if (q.isError) return <ErrorState title="Couldn't load the thresholds" detail={q.error.message} onRetry={() => void q.refetch()} />;
  if (!q.data) return <SkeletonCard label="the thresholds" lines={8} />;
  return <ThresholdsForm d={q.data} />;
}

export function ThresholdsForm({ d }: { d: Thresholds }) {
  const qc = useQueryClient();
  const initial = useMemo(() => Object.fromEntries(d.items.map((t) => [t.path, toDisplay(t, t.value)])), [d]);
  const [draft, setDraft] = useState<Record<string, string>>(initial);
  useEffect(() => setDraft(initial), [initial]);
  const after = async (next: Thresholds) => {
    qc.setQueryData(["thresholds"], next);
    await qc.invalidateQueries({ predicate: (x) => x.queryKey[0] !== "thresholds" });
  };
  const save = useMutation({ mutationFn: dashboardApi.saveThresholds, onSuccess: after });
  const reset = useMutation({ mutationFn: dashboardApi.resetThresholds, onSuccess: after });

  const byPath = Object.fromEntries(d.items.map((t) => [t.path, t]));
  const changed: Record<string, number | null> = {};
  const invalid: string[] = [];
  for (const [path, s] of Object.entries(draft)) {
    const t = byPath[path];
    if (!t || s === initial[path]) continue;
    const v = fromDisplay(t, s);
    if (v === "invalid") invalid.push(t.label);
    else changed[path] = v;
  }
  const groups = [...new Set(d.items.map((t) => t.group))];
  const nChanged = Object.keys(changed).length;
  return (
    <div className="space-y-4">
      <Alert tone="info">
        These override <code>backend/config/profiles.yaml</code> and are saved in <code className="break-all">{d.override_file}</code>. Values are
        checked against the whole config before saving. {d.note}
      </Alert>
      <div className="grid gap-4 lg:grid-cols-2">
        {groups.map((g) => (
          <Card key={g} title={g.replace(/^Risk: (\w)/, (_, c: string) => `Risk: ${c.toUpperCase()}`)}>
            <div className="space-y-2">
              {d.items
                .filter((t) => t.group === g)
                .map((t) => {
                  const dirty = draft[t.path] !== initial[t.path];
                  return (
                    <label key={t.path} className="grid grid-cols-[1fr_8rem] items-center gap-2 text-sm">
                      <span className="text-fg">
                        {t.label}
                        {t.edited && <span className="ml-1 text-xs text-caution">(edited; default {toDisplay(t, t.default) || "none"})</span>}
                        {dirty && <span className="ml-1 text-xs text-fg-subtle">(unsaved)</span>}
                      </span>
                      <span className="flex items-center gap-1">
                        <input
                          className={inputClass}
                          inputMode="decimal"
                          aria-label={`${g}: ${t.label}`}
                          value={draft[t.path] ?? ""}
                          placeholder={t.nullable ? "no limit" : ""}
                          onChange={(e) => setDraft({ ...draft, [t.path]: e.target.value })}
                        />
                        <span className="w-12 text-xs text-fg-subtle">{UNIT[t.unit]}</span>
                      </span>
                    </label>
                  );
                })}
            </div>
          </Card>
        ))}
      </div>
      {invalid.length > 0 && <Alert tone="error">Not a number: {invalid.join(", ")}</Alert>}
      {save.isError && <Alert tone="error">{save.error.message}</Alert>}
      {save.isSuccess && nChanged === 0 && <Alert tone="success">Saved. Signals now use the new thresholds.</Alert>}
      <div className="flex flex-wrap gap-2">
        <Button disabled={nChanged === 0 || invalid.length > 0 || save.isPending} onClick={() => save.mutate(changed)}>
          {save.isPending ? "Saving…" : `Save ${nChanged || ""} change${nChanged === 1 ? "" : "s"}`}
        </Button>
        <Button variant="secondary" disabled={nChanged === 0} onClick={() => setDraft(initial)}>
          Discard
        </Button>
        <Button variant="danger" disabled={d.edited === 0 || reset.isPending} onClick={() => reset.mutate()}>
          Reset all to profiles.yaml ({d.edited} edited)
        </Button>
      </div>
    </div>
  );
}
