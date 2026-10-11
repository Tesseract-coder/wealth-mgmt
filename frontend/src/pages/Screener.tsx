import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { screenerApi, type ScreenerConfig, type ScreenFilter, type ScreenRequest } from "../api/client";
import { FilterBuilder, fromDrafts, SaveScreen, toDraft, type Draft } from "../components/FilterBuilder";
import { ScanPanel } from "../components/ScanPanel";
import { ScreenResults } from "../components/ScreenResults";
import { Alert, Button, Card } from "../components/ui";

/** "preset:growth" | "saved:3" | "custom" */
type Sel = { kind: "preset"; key: string } | { kind: "saved"; id: number } | { kind: "custom" };

export function parseSel(v: string | null, config: ScreenerConfig): Sel {
  if (v === "custom") return { kind: "custom" };
  if (v?.startsWith("saved:")) {
    const id = Number(v.slice(6));
    if (config.screens.some((s) => s.id === id)) return { kind: "saved", id };
  }
  const key = v?.startsWith("preset:") ? v.slice(7) : "";
  return { kind: "preset", key: config.presets.some((p) => p.key === key) ? key : (config.presets[0]?.key ?? "") };
}

const selKey = (s: Sel) => (s.kind === "preset" ? `preset:${s.key}` : s.kind === "saved" ? `saved:${s.id}` : "custom");

function Tab({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={`whitespace-nowrap rounded-full border px-3 py-1 text-sm ${
        active
          ? "border-slate-900 bg-slate-900 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-900"
          : "border-slate-300 hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
      }`}
    >
      {children}
    </button>
  );
}

function Chips({ filters, config }: { filters: ScreenFilter[]; config: ScreenerConfig }) {
  if (filters.length === 0) return <p className="text-sm text-slate-500">No extra filters.</p>;
  return (
    <ul className="flex flex-wrap gap-1.5 text-xs">
      {filters.map((f, i) => {
        const label = config.fields.find((x) => x.key === f.field)?.label ?? f.field;
        const v = Array.isArray(f.value) ? `${f.value[0]} – ${f.value[1]}` : `${config.ops[f.op]} ${f.value}`;
        return (
          <li key={i} className="rounded bg-slate-100 px-2 py-0.5 dark:bg-slate-800">
            {label} {v}
          </li>
        );
      })}
    </ul>
  );
}

function ScreenerBody({ config }: { config: ScreenerConfig }) {
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const sel = parseSel(params.get("screen"), config);
  const [includeHeld, setIncludeHeld] = useState(false);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [applied, setApplied] = useState<ScreenFilter[] | null>(null);
  const [editing, setEditing] = useState(false);
  const select = (s: Sel) => {
    const p = new URLSearchParams(params);
    p.set("screen", selKey(s));
    setParams(p, { replace: true });
    setEditing(false);
  };

  const saved = sel.kind === "saved" ? config.screens.find((s) => s.id === sel.id) : undefined;
  const preset = sel.kind === "preset" ? config.presets.find((p) => p.key === sel.key) : undefined;
  const req: ScreenRequest | null =
    sel.kind === "preset"
      ? { preset: sel.key, include_held: includeHeld }
      : sel.kind === "saved"
        ? { screen_id: sel.id, include_held: includeHeld }
        : applied
          ? { filters: applied, include_held: includeHeld }
          : null;
  const result = useQuery({
    queryKey: ["screen", req],
    queryFn: () => screenerApi.screen(req!),
    enabled: req !== null && config.latest_scan !== null,
  });

  const built = fromDrafts(drafts, config.fields);
  const save = useMutation({
    mutationFn: (name: string) => screenerApi.saveScreen(name, built.filters, saved?.id),
    onSuccess: async (s) => {
      await qc.invalidateQueries({ queryKey: ["screener-config"] });
      void qc.invalidateQueries({ queryKey: ["screen"] });
      select({ kind: "saved", id: s.id });
    },
  });
  const remove = useMutation({
    mutationFn: (id: number) => screenerApi.deleteScreen(id),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["screener-config"] });
      select({ kind: "preset", key: config.presets[0]?.key ?? "" });
    },
  });
  const openBuilder = (filters: ScreenFilter[], asCustom: boolean) => {
    setDrafts(filters.map(toDraft));
    if (asCustom) {
      setApplied(null);
      select({ kind: "custom" });
    } else setEditing(true);
  };
  const showBuilder = sel.kind === "custom" || editing;

  return (
    <>
      <ScanPanel config={config} />
      <Card title="Screens">
        <div className="space-y-3">
          <div role="tablist" aria-label="Screens" className="flex flex-wrap gap-1.5">
            {config.presets.map((p) => (
              <Tab key={p.key} active={sel.kind === "preset" && sel.key === p.key} onClick={() => select({ kind: "preset", key: p.key })}>
                {p.label}
              </Tab>
            ))}
            {config.screens.map((s) => (
              <Tab key={s.id} active={sel.kind === "saved" && sel.id === s.id} onClick={() => select({ kind: "saved", id: s.id })}>
                <span aria-hidden="true">☰ </span>
                {s.name}
              </Tab>
            ))}
            <Tab active={sel.kind === "custom"} onClick={() => openBuilder(applied ?? [], true)}>
              + Build your own
            </Tab>
          </div>

          {preset && (
            <div className="space-y-1.5">
              <p className="text-sm text-slate-600 dark:text-slate-400">{preset.description}</p>
              {preset.filters.length > 0 && <Chips filters={preset.filters} config={config} />}
              <Button variant="secondary" onClick={() => openBuilder(preset.filters, true)}>
                Customise a copy
              </Button>
            </div>
          )}
          {saved && !editing && (
            <div className="space-y-1.5">
              <Chips filters={saved.filters} config={config} />
              <div className="flex gap-2">
                <Button variant="secondary" onClick={() => openBuilder(saved.filters, false)}>
                  Edit
                </Button>
                <Button variant="danger" disabled={remove.isPending} onClick={() => window.confirm(`Delete the screen "${saved.name}"?`) && remove.mutate(saved.id)}>
                  Delete
                </Button>
              </div>
            </div>
          )}
          {showBuilder && (
            <div className="space-y-3 rounded border border-slate-200 p-3 dark:border-slate-800">
              <FilterBuilder fields={config.fields} ops={config.ops} drafts={drafts} onChange={setDrafts} />
              {built.error && drafts.length > 0 && <p className="text-sm text-amber-800 dark:text-amber-300">{built.error}</p>}
              <div className="flex flex-wrap items-end gap-4">
                {sel.kind === "custom" && (
                  <Button disabled={!!built.error || !config.latest_scan} onClick={() => setApplied(built.filters)}>
                    Apply
                  </Button>
                )}
                {!built.error && <SaveScreen key={saved?.id ?? "new"} initial={saved?.name ?? ""} busy={save.isPending} onSave={(n) => save.mutate(n)} />}
                {editing && (
                  <Button variant="secondary" onClick={() => setEditing(false)}>
                    Cancel
                  </Button>
                )}
              </div>
              {save.isError && <Alert tone="error">{save.error.message}</Alert>}
            </div>
          )}

          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={includeHeld} onChange={(e) => setIncludeHeld(e.target.checked)} />
            Include stocks I already hold
          </label>
        </div>
      </Card>

      {!config.latest_scan ? null : result.isError ? (
        <Alert tone="error">{result.error.message}</Alert>
      ) : req === null ? (
        <Card>
          <p className="text-sm text-slate-500">Add conditions and press Apply.</p>
        </Card>
      ) : !result.data ? (
        <Card>Screening…</Card>
      ) : (
        <Card
          title={`${result.data.title}: ${result.data.candidates.length ? `top ${result.data.candidates.length}` : "no ideas"}`}
          actions={
            sel.kind !== "custom" && (
              <a
                className="text-sm underline"
                href={screenerApi.csvHref({ preset: preset?.key, screen_id: saved?.id, include_held: includeHeld })}
              >
                Download CSV
              </a>
            )
          }
        >
          <ScreenResults r={result.data} includeHeld={includeHeld} />
        </Card>
      )}
    </>
  );
}

/** Ranked new-stock ideas: scan a universe, then filter the scan with presets or your own screens. */
export function Screener() {
  const config = useQuery({ queryKey: ["screener-config"], queryFn: screenerApi.config });
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Screener</h1>
        <p className="text-sm text-slate-500">
          Scores every stock in a universe with your style and risk, then ranks the ones that pass a screen, with an entry
          zone, stop-loss and targets for each. Switching screens is instant; run a new scan for fresh data.
        </p>
      </div>
      {config.isError ? <Alert tone="error">{config.error.message}</Alert> : !config.data ? <Card>Loading…</Card> : <ScreenerBody config={config.data} />}
    </div>
  );
}
