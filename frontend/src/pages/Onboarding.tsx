import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Check, CircleCheck, Circle, FileSpreadsheet, Upload } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { api, portfolioApi, type AppConfig, type Profile, type RiskKey, type StyleKey } from "../api/client";
import { RiskImpact } from "../components/RiskImpact";
import { Alert, Button, Card, ErrorState, inputClass, Loading, Skeleton } from "../components/ui";

/** First run: pick an investing style and risk level; the Google Sheet link is optional. */
export function Onboarding() {
  const config = useQuery({ queryKey: ["config"], queryFn: api.config });
  const profile = useQuery({ queryKey: ["profile"], queryFn: api.profile });
  const failed = config.error ?? profile.error;
  if (failed)
    return <ErrorState title="Couldn't load the setup" detail={failed.message} hint="Check the backend is running (make dev), then retry." onRetry={() => void Promise.all([config.refetch(), profile.refetch()])} />;
  if (!config.data || !profile.data)
    return (
      <Loading label="the setup">
        <Skeleton className="mx-auto h-96 w-full max-w-2xl" />
      </Loading>
    );
  return <ProfileForm config={config.data} profile={profile.data} firstRun />;
}

// ------------------------------------------------------------------------------- choices

function Choice({ checked, name, onChange, title, children }: { checked: boolean; name: string; onChange: () => void; title: string; children: ReactNode }) {
  return (
    <label
      className={`flex cursor-pointer gap-2.5 rounded-card border p-3 text-sm transition-colors has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-[var(--focus)] ${
        checked ? "border-accent bg-accent-soft" : "border-border bg-surface hover:border-border-strong"
      }`}
    >
      <input type="radio" name={name} className="sr-only" checked={checked} onChange={onChange} />
      {checked ? <CircleCheck aria-hidden className="mt-0.5 size-4 shrink-0 text-accent-text" /> : <Circle aria-hidden className="mt-0.5 size-4 shrink-0 text-fg-subtle" />}
      <span className="min-w-0">
        <span className={`block font-semibold ${checked ? "text-accent-text" : "text-fg"}`}>{title}</span>
        {children}
      </span>
    </label>
  );
}

function StyleChoices({ config, style, setStyle, tw, setTw }: { config: AppConfig; style: StyleKey | null; setStyle: (s: StyleKey) => void; tw: number; setTw: (v: number) => void }) {
  return (
    <>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3" role="radiogroup" aria-label="Investing style">
        {(Object.entries(config.styles) as [StyleKey, AppConfig["styles"][StyleKey]][]).map(([k, s]) => (
          <Choice key={k} name="style" checked={style === k} onChange={() => setStyle(k)} title={s.label}>
            <span className="block text-fg-muted">{s.horizon}</span>
            <span className="mt-1 block text-xs text-fg-subtle">
              Charts: {s.timeframes.join(", ")}
              {k !== "custom" && ` · ${Math.round(s.technical_weight * 100)}% technical / ${Math.round(s.fundamental_weight * 100)}% fundamental`}
            </span>
            {s.note && <span className="mt-1 block text-xs text-caution">{s.note}</span>}
          </Choice>
        ))}
      </div>
      {style === "custom" && (
        <label className="mt-3 block text-sm text-fg">
          <span className="mb-1 block">
            Technical weight: {Math.round(tw * 100)}% · fundamental {Math.round((1 - tw) * 100)}%
          </span>
          <input type="range" min={0} max={1} step={0.05} value={tw} onChange={(e) => setTw(Number(e.target.value))} className="w-full max-w-md accent-[var(--accent)]" />
        </label>
      )}
    </>
  );
}

function RiskChoices({ config, risk, setRisk }: { config: AppConfig; risk: RiskKey; setRisk: (r: RiskKey) => void }) {
  return (
    <div className="grid gap-2 sm:grid-cols-3" role="radiogroup" aria-label="Risk level">
      {(Object.entries(config.risk_levels) as [RiskKey, AppConfig["risk_levels"][RiskKey]][]).map(([k, r]) => (
        <Choice key={k} name="risk" checked={risk === k} onChange={() => setRisk(k)} title={r.label}>
          <ul className="mt-1 space-y-0.5 text-xs text-fg-muted">
            <li>
              Max {Math.round(r.max_weight_per_stock * 100)}% per stock, {Math.round(r.max_weight_per_sector * 100)}% per sector
            </li>
            <li>
              Buy at score ≥ {r.buy_threshold}; stop {r.stop_loss_atr_multiple}× ATR
            </li>
            <li>
              Debt/equity ≤ {r.max_debt_to_equity ?? "no limit"}, beta ≤ {r.max_beta ?? "no limit"}
            </li>
          </ul>
        </Choice>
      ))}
    </div>
  );
}

const sheetValid = (sheet: string) => sheet.trim() === "" || /^https:\/\/docs\.google\.com\/spreadsheets\//.test(sheet.trim());

function SheetField({ sheet, setSheet }: { sheet: string; setSheet: (s: string) => void }) {
  return (
    <>
      <label className="block text-sm">
        <span className="mb-1 block text-fg-muted">
          Your sheet&apos;s link from the address bar. Connect and test it later in Settings → Google Sheets (docs/GOOGLE_SHEETS_SETUP.md). You can leave this blank.
        </span>
        <input className={inputClass} placeholder="https://docs.google.com/spreadsheets/d/…" value={sheet} onChange={(e) => setSheet(e.target.value)} />
      </label>
      {!sheetValid(sheet) && <p className="mt-1 text-xs text-bad">That doesn&apos;t look like a Google Sheets link. It should start with https://docs.google.com/spreadsheets/.</p>}
    </>
  );
}

// ------------------------------------------------------------------------------ illustrations

/** Simple shapes, drawn here (no image files), one per step. Decorative only. */
function Illustration({ step }: { step: number }) {
  const common = { width: 120, height: 84, viewBox: "0 0 120 84", "aria-hidden": true } as const;
  if (step === 0)
    // Candles of different lengths: short-term to long-term.
    return (
      <svg {...common}>
        <line x1="8" y1="74" x2="112" y2="74" stroke="var(--border-strong)" strokeWidth="2" />
        {[18, 34, 26, 44, 38, 56].map((h, i) => (
          <g key={i}>
            <line x1={18 + i * 17} y1={74 - h - 8} x2={18 + i * 17} y2={74 - 2} stroke="var(--fg-subtle)" strokeWidth="1.5" />
            <rect x={13 + i * 17} y={74 - h} width="10" height={h - 6} rx="2" fill={i % 2 ? "var(--chart-up)" : "var(--accent)"} />
          </g>
        ))}
      </svg>
    );
  if (step === 1)
    // A gauge from careful to bold.
    return (
      <svg {...common}>
        <path d="M18 70 A42 42 0 0 1 60 28" stroke="var(--score-5)" strokeWidth="10" fill="none" />
        <path d="M60 28 A42 42 0 0 1 90 40" stroke="var(--score-3)" strokeWidth="10" fill="none" />
        <path d="M90 40 A42 42 0 0 1 102 70" stroke="var(--score-1)" strokeWidth="10" fill="none" />
        <line x1="60" y1="70" x2="74" y2="38" stroke="var(--fg)" strokeWidth="3" strokeLinecap="round" />
        <circle cx="60" cy="70" r="5" fill="var(--fg)" />
      </svg>
    );
  // A file and a sheet grid flowing into the app.
  return (
    <svg {...common}>
      <path d="M12 12 h22 l8 8 v42 h-30z" fill="var(--surface-3)" stroke="var(--border-strong)" />
      <rect x="18" y="32" width="18" height="3" rx="1.5" fill="var(--fg-subtle)" />
      <rect x="18" y="40" width="14" height="3" rx="1.5" fill="var(--fg-subtle)" />
      <rect x="78" y="12" width="32" height="50" rx="3" fill="var(--surface-3)" stroke="var(--border-strong)" />
      {[0, 1, 2, 3].map((r) => (
        <line key={r} x1="78" y1={24 + r * 10} x2="110" y2={24 + r * 10} stroke="var(--border-strong)" />
      ))}
      <line x1="94" y1="12" x2="94" y2="62" stroke="var(--border-strong)" />
      <path d="M46 40 h24 m-6 -6 l6 6 -6 6" stroke="var(--accent)" strokeWidth="3" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="60" cy="74" r="6" fill="var(--accent)" />
    </svg>
  );
}

const STEPS = [
  { title: "Your investing style", lead: "How long you usually hold a stock. It sets which charts the signals read and how much weight goes to price trends versus the business." },
  { title: "Your risk level", lead: "How much you're willing to put in one stock or sector, and how tight the stop-losses are. It also sets the debt limit in the Financial Health checks." },
  { title: "Your data", lead: "Nothing here asks for broker logins. Data comes only from files you export, or a Google Sheet you share." },
];

/** Progress dots with the step names: done steps get a tick, the current one is marked for screen readers. */
function Progress({ step }: { step: number }) {
  return (
    <ol aria-label="Setup progress" className="flex items-center justify-center gap-2">
      {STEPS.map((s, i) => (
        <li key={s.title} aria-current={i === step ? "step" : undefined} className="flex items-center gap-2">
          <span
            className={`grid size-7 place-items-center rounded-full border text-xs font-semibold ${
              i < step ? "border-accent bg-accent text-accent-fg" : i === step ? "border-accent bg-accent-soft text-accent-text" : "border-border text-fg-subtle"
            }`}
          >
            {i < step ? <Check aria-hidden className="size-3.5" /> : i + 1}
            <span className="sr-only">
              {" "}
              {s.title}
              {i < step ? " (done)" : ""}
            </span>
          </span>
          {i < STEPS.length - 1 && <span aria-hidden className={`h-0.5 w-8 rounded ${i < step ? "bg-accent" : "bg-border"}`} />}
        </li>
      ))}
    </ol>
  );
}

// ------------------------------------------------------------------------------------ form

export function ProfileForm({ config, profile, firstRun = false }: { config: AppConfig; profile: Profile; firstRun?: boolean }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [style, setStyle] = useState<StyleKey | null>(profile.style);
  const [risk, setRisk] = useState<RiskKey>(profile.risk);
  const [tw, setTw] = useState(profile.custom_technical_weight);
  const [sheet, setSheet] = useState(profile.gsheet_url ?? "");
  const [saved, setSaved] = useState(false);
  const [step, setStep] = useState(0);
  useEffect(() => setSaved(false), [style, risk, tw, sheet]);
  const sheetOk = sheetValid(sheet);
  const save = useMutation({
    mutationFn: () => api.saveProfile({ style: style!, risk, custom_technical_weight: tw, gsheet_url: sheet.trim() || null }),
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

  if (firstRun) {
    const s = STEPS[step]!;
    const canNext = step === 0 ? !!style : true;
    return (
      <div className="mx-auto max-w-3xl space-y-6">
        <header className="space-y-1 text-center">
          <h1 className="text-xl font-semibold text-fg">Welcome</h1>
          <p className="text-sm text-fg-muted">Three quick choices set how your holdings are scored. You can change them any time in Settings.</p>
        </header>
        <Progress step={step} />
        <section aria-labelledby="step-title" className="space-y-4 rounded-card border border-border bg-surface p-4 shadow-card sm:p-6">
          <div className="flex flex-col items-center gap-3 text-center sm:flex-row sm:text-left">
            <Illustration step={step} />
            <div>
              <p className="text-xs font-medium text-fg-subtle">
                Step {step + 1} of {STEPS.length}
              </p>
              <h2 id="step-title" className="text-lg font-semibold text-fg">
                {s.title}
              </h2>
              <p className="text-sm text-fg-muted">{s.lead}</p>
            </div>
          </div>
          {step === 0 && <StyleChoices config={config} style={style} setStyle={setStyle} tw={tw} setTw={setTw} />}
          {step === 1 && <RiskChoices config={config} risk={risk} setRisk={setRisk} />}
          {step === 2 && (
            <div className="grid gap-4 md:grid-cols-2">
              <div className="rounded-card border border-border p-4">
                <h3 className="flex items-center gap-1.5 text-sm font-semibold text-fg">
                  <Upload aria-hidden className="size-4 text-fg-subtle" /> Files from Groww (next)
                </h3>
                <p className="mt-1 text-sm text-fg-muted">After this step you&apos;ll go to Import, where you can drop your Groww holdings and mutual fund files, or a CAS PDF.</p>
              </div>
              <div className="rounded-card border border-border p-4">
                <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-fg">
                  <FileSpreadsheet aria-hidden className="size-4 text-fg-subtle" /> Google Sheet (optional)
                </h3>
                <SheetField sheet={sheet} setSheet={setSheet} />
              </div>
            </div>
          )}
          {save.isError && <Alert tone="error">{save.error.message}</Alert>}
          <div className="flex items-center justify-between gap-2 border-t border-border pt-4">
            {step > 0 ? (
              <Button variant="ghost" icon={ArrowLeft} onClick={() => setStep(step - 1)}>
                Back
              </Button>
            ) : (
              <span />
            )}
            {step < STEPS.length - 1 ? (
              <Button disabled={!canNext} onClick={() => setStep(step + 1)}>
                Next <ArrowRight aria-hidden className="size-4" />
              </Button>
            ) : (
              <Button disabled={!style || !sheetOk || save.isPending} onClick={() => save.mutate()}>
                {save.isPending ? "Saving…" : "Save and continue"}
              </Button>
            )}
          </div>
          {step === 0 && !style && <p className="text-right text-xs text-fg-subtle">Choose a style to continue.</p>}
        </section>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <Card title="Investing style" description={STEPS[0]!.lead}>
        <StyleChoices config={config} style={style} setStyle={setStyle} tw={tw} setTw={setTw} />
      </Card>
      <Card title="Risk level" description={STEPS[1]!.lead}>
        <RiskChoices config={config} risk={risk} setRisk={setRisk} />
        <div className="mt-4">
          <h3 className="mb-2 text-sm font-semibold text-fg">What your risk level changes</h3>
          <RiskImpact config={config} selected={risk} saved={profile.risk} />
        </div>
      </Card>
      <Card title="Google Sheet (optional)">
        <SheetField sheet={sheet} setSheet={setSheet} />
      </Card>
      {save.isError && <Alert tone="error">{save.error.message}</Alert>}
      {saved && <Alert tone="success">Saved. Signals now use the new profile.</Alert>}
      <Button disabled={!style || !sheetOk || save.isPending} onClick={() => save.mutate()}>
        {save.isPending ? "Saving…" : "Save profile"}
      </Button>
      {!style && <p className="text-xs text-fg-subtle">Choose a style to continue.</p>}
    </div>
  );
}
