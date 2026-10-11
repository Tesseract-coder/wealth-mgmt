import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  ForeignTabsError,
  screenerApi,
  sheetsApi,
  type ColumnMappingIn,
  type HoldingKind,
  type Imported,
  type NeedsMapping,
  type SheetCheck,
  type SheetExport,
  type SheetsStatus,
} from "../api/client";
import { formatFreshness } from "../lib/format";
import { ColumnMapper } from "./ColumnMapper";
import { Alert, Button, Card, ErrorState, inputClass, SkeletonCard } from "./ui";

const when = (iso: string) => formatFreshness(new Date(iso));

/** ✓ / ✗ / – with words, so the result never depends on colour alone. */
export function CheckRow({ c }: { c: SheetCheck }) {
  const [icon, word, tone] =
    c.ok === true
      ? ["✓", "OK", "text-good"]
      : c.ok === false
        ? ["✗", "Problem", "text-bad"]
        : ["–", "Not checked", "text-fg-subtle"];
  return (
    <li className="flex gap-2 text-sm">
      <span aria-hidden="true" className={`w-4 shrink-0 font-bold ${tone}`}>
        {icon}
      </span>
      <div className="min-w-0">
        <span className="font-medium">{c.name}</span> <span className={`text-xs ${tone}`}>({word})</span>
        <p className="break-words text-fg-muted">{c.detail}</p>
      </div>
    </li>
  );
}

/** Export button that asks before overwriting tabs the app didn't create. */
export function SheetsExportButton({ status }: { status: SheetsStatus | undefined }) {
  const qc = useQueryClient();
  const [confirm, setConfirm] = useState<string[] | null>(null);
  const run = useMutation({
    mutationFn: (overwrite: string[]) => sheetsApi.export(overwrite),
    onSuccess: () => setConfirm(null),
    onError: (e) => {
      if (e instanceof ForeignTabsError) setConfirm(e.tabs);
    },
    onSettled: () => void qc.invalidateQueries({ queryKey: ["sheets"] }),
  });
  const ready = !!status?.service_account.configured && !!status.spreadsheet_url;
  return (
    <div className="space-y-2">
      <Button disabled={!ready || run.isPending} onClick={() => run.mutate([])} title={ready ? undefined : "Add the key and the sheet link first"}>
        {run.isPending ? "Exporting…" : "Export to Google Sheets"}
      </Button>
      {!ready && status && <p className="text-xs text-fg-subtle">Needs a service-account key and your sheet's link (Settings → Google Sheets).</p>}
      {confirm && (
        <Alert tone="warning">
          <p>
            Your sheet already has {confirm.length === 1 ? "a tab" : "tabs"} named <strong>{confirm.join(", ")}</strong> with content this app
            didn't write. Exporting replaces everything on {confirm.length === 1 ? "it" : "them"}. Your other tabs are never touched.
          </p>
          <div className="mt-2 flex gap-2">
            <Button variant="danger" onClick={() => run.mutate(confirm)} disabled={run.isPending}>
              Overwrite {confirm.join(", ")}
            </Button>
            <Button variant="secondary" onClick={() => setConfirm(null)}>
              Cancel
            </Button>
          </div>
        </Alert>
      )}
      {run.isError && !(run.error instanceof ForeignTabsError) && <Alert tone="error">{run.error.message}</Alert>}
      {run.data && <ExportDone r={run.data} />}
    </div>
  );
}

function ExportDone({ r }: { r: SheetExport }) {
  return (
    <Alert tone="success">
      Exported to “{r.title}” at {when(r.at)}: {r.tabs.map((t) => `${t.name} (${t.rows} rows)`).join(", ")}.{" "}
      <a href={r.url} target="_blank" rel="noreferrer" className="underline">
        Open the sheet ↗
      </a>
    </Alert>
  );
}

function KeyUpload({ status }: { status: SheetsStatus }) {
  const qc = useQueryClient();
  const sa = status.service_account;
  const [copied, setCopied] = useState(false);
  const upload = useMutation({
    mutationFn: sheetsApi.uploadKey,
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["sheets"] }),
  });
  return (
    <div className="space-y-2 text-sm">
      {sa.configured && sa.client_email ? (
        <div className="space-y-1">
          <p>
            <span aria-hidden="true" className="text-good">
              ✓{" "}
            </span>
            Key found. Share your sheet with this address as an <strong>Editor</strong>:
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <code className="break-all rounded bg-surface-2 px-2 py-1">{sa.client_email}</code>
            <Button
              variant="secondary"
              className="!px-2 !py-0.5 text-xs"
              onClick={() => {
                void navigator.clipboard?.writeText(sa.client_email!).then(() => setCopied(true));
              }}
            >
              {copied ? "Copied" : "Copy"}
            </Button>
          </div>
          <p className="break-all text-xs text-fg-subtle">
            Stored at {sa.path}
            {sa.path.includes("/secrets/") ? " (gitignored)" : ""}. The private key is never shown, and is used only to sign in to Google.
          </p>
        </div>
      ) : (
        <p className="text-fg-muted">
          {sa.error ? <span className="text-bad">✗ {sa.error}</span> : "No service-account key yet."} A service account is a
          Google Cloud robot you share one sheet with. It is <strong>not</strong> your Google or broker login. Steps: docs/GOOGLE_SHEETS_SETUP.md.
        </p>
      )}
      <label className="block">
        <span className="mb-1 block text-fg-subtle">{sa.configured ? "Replace the key (JSON)" : "Upload the key (JSON)"}</span>
        <input
          type="file"
          accept=".json,application/json"
          className="text-sm"
          disabled={upload.isPending}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) upload.mutate(f);
            e.target.value = "";
          }}
        />
      </label>
      {upload.isError && <Alert tone="error">{upload.error.message}</Alert>}
      {upload.isSuccess && <Alert tone="success">Key saved for {upload.data.client_email}.</Alert>}
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-medium">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-fg-subtle">{hint}</span>}
    </label>
  );
}

export function SheetsSettingsForm({ status }: { status: SheetsStatus }) {
  const qc = useQueryClient();
  const s = status.settings;
  const screener = useQuery({ queryKey: ["screener-config"], queryFn: screenerApi.config });
  const [draft, setDraft] = useState({
    sheet_url: status.sheet_url ?? "",
    stocks_tab: s.stocks_tab,
    mf_tab: s.mf_tab,
    stocks_csv_url: s.stocks_csv_url ?? "",
    mf_csv_url: s.mf_csv_url ?? "",
    screener_screen: s.screener_screen ?? "",
    auto_export: s.auto_export,
  });
  const set = (k: keyof typeof draft) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setDraft({ ...draft, [k]: e.target.type === "checkbox" ? (e.target as HTMLInputElement).checked : e.target.value });
  const save = useMutation({
    mutationFn: () =>
      sheetsApi.save({
        ...draft,
        sheet_url: draft.sheet_url.trim() || null,
        stocks_csv_url: draft.stocks_csv_url.trim() || null,
        mf_csv_url: draft.mf_csv_url.trim() || null,
        screener_screen: draft.screener_screen || null,
      }),
    onSuccess: (d) => {
      qc.setQueryData(["sheets"], d);
      void qc.invalidateQueries({ queryKey: ["profile"] });
    },
  });
  const cfg = screener.data;
  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <Field label="Your sheet's link" hint="Copy it from the browser's address bar (…/spreadsheets/d/…/edit). Used for export, and for import with the service account.">
        <input className={inputClass} value={draft.sheet_url} onChange={set("sheet_url")} placeholder="https://docs.google.com/spreadsheets/d/…/edit" />
      </Field>
      {status.link_error && <Alert tone="warning">{status.link_error}</Alert>}
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Stocks tab to import" hint={`Default ${status.default_import_tabs.stocks}`}>
          <input className={inputClass} value={draft.stocks_tab} onChange={set("stocks_tab")} />
        </Field>
        <Field label="Mutual funds tab to import" hint={`Default ${status.default_import_tabs.mf}`}>
          <input className={inputClass} value={draft.mf_tab} onChange={set("mf_tab")} />
        </Field>
      </div>
      <details className="text-sm">
        <summary className="cursor-pointer font-medium">No service account? Import from published CSV links instead (read-only)</summary>
        <div className="mt-2 grid gap-3 sm:grid-cols-2">
          <Field label="Stocks: published CSV link" hint="File → Share → Publish to web → pick the tab → CSV → Publish, then copy the link.">
            <input className={inputClass} value={draft.stocks_csv_url} onChange={set("stocks_csv_url")} placeholder="https://docs.google.com/spreadsheets/d/e/…/pub?output=csv" />
          </Field>
          <Field label="Mutual funds: published CSV link" hint="Anyone with this link can read that tab, so publish only holdings you're happy to share.">
            <input className={inputClass} value={draft.mf_csv_url} onChange={set("mf_csv_url")} placeholder="https://docs.google.com/spreadsheets/d/e/…/pub?output=csv" />
          </Field>
        </div>
      </details>
      <Field label="Screen written to the Screener tab" hint="Uses your latest scan.">
        <select className={inputClass} value={draft.screener_screen} onChange={set("screener_screen")}>
          <option value="">{cfg?.presets[0] ? `${cfg.presets[0].label} (default)` : "First preset (default)"}</option>
          {cfg?.presets.slice(1).map((p) => (
            <option key={p.key} value={`preset:${p.key}`}>
              {p.label}
            </option>
          ))}
          {cfg?.screens.map((x) => (
            <option key={x.id} value={`saved:${x.id}`}>
              {x.name} (saved)
            </option>
          ))}
        </select>
      </Field>
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" className="mt-1" checked={draft.auto_export} onChange={set("auto_export")} />
        <span>
          Export automatically after the daily refresh (Mon–Fri, {status.refresh_time_ist} IST, while the app is running)
        </span>
      </label>
      <div className="flex items-center gap-3">
        <Button type="submit" disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save"}
        </Button>
        {save.isSuccess && <span className="text-sm text-good">✓ Saved</span>}
      </div>
      {save.isError && <Alert tone="error">{save.error.message}</Alert>}
    </form>
  );
}

function ConnectionTest() {
  const qc = useQueryClient();
  const run = useMutation({ mutationFn: sheetsApi.test, onSettled: () => void qc.invalidateQueries({ queryKey: ["sheets"] }) });
  return (
    <div className="space-y-3">
      <p className="text-sm text-fg-subtle">Checks the key, the link, sign-in, opening the sheet, write access, the tabs and any published links. Changes nothing.</p>
      <Button onClick={() => run.mutate()} disabled={run.isPending}>
        {run.isPending ? "Testing…" : "Test connection"}
      </Button>
      {run.isError && <Alert tone="error">{run.error.message}</Alert>}
      {run.data && (
        <>
          <Alert tone={run.data.ok ? "success" : "warning"}>{run.data.ok ? "Connection works." : "Something needs fixing; see below."}</Alert>
          <ul className="space-y-2">
            {run.data.checks.map((c) => (
              <CheckRow key={c.name} c={c} />
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

const DIRECTION: Record<string, string> = { export: "Export", import: "Import", test: "Test" };

function History({ status }: { status: SheetsStatus }) {
  if (status.history.length === 0) return <p className="text-sm text-fg-subtle">Nothing synced yet.</p>;
  return (
    <ul className="space-y-1 text-sm">
      {status.history.map((h, i) => (
        <li key={i} className="flex gap-2">
          <span aria-hidden="true" className={h.ok ? "text-good" : "text-bad"}>
            {h.ok ? "✓" : "✗"}
          </span>
          <span className="min-w-0">
            <span className="font-medium">
              {DIRECTION[h.direction]} {h.ok ? "succeeded" : "failed"}
            </span>
            {h.detail && <span className="text-fg-subtle"> · {h.detail}</span>} <span className="text-xs text-fg-subtle">{when(h.at)}</span>
            <span className="block break-words text-xs text-fg-muted">{h.message}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

/** Settings → Google Sheets. */
export function GoogleSheetsSettings() {
  const q = useQuery({ queryKey: ["sheets"], queryFn: sheetsApi.status });
  if (q.isError) return <ErrorState title="Couldn't load the Google Sheets settings" detail={q.error.message} onRetry={() => void q.refetch()} />;
  if (!q.data) return <SkeletonCard label="the Google Sheets settings" lines={5} />;
  const d = q.data;
  const lastExport = d.history.find((h) => h.direction === "export" && h.ok);
  return (
    <div className="space-y-4">
      <Alert tone="info">
        The app only reads the tabs you point it at and only writes {Object.values(d.export_tabs).join(", ")}. It never asks for your Google
        or broker password. Setup guide: <code>docs/GOOGLE_SHEETS_SETUP.md</code>.
      </Alert>
      <Card title="1. Service account">
        <KeyUpload status={d} />
      </Card>
      <Card title="2. Sheet and tabs">
        <SheetsSettingsForm status={d} />
      </Card>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="3. Test">
          <ConnectionTest />
        </Card>
        <Card
          title="4. Export"
          actions={
            d.spreadsheet_url && (
              <a href={d.spreadsheet_url} target="_blank" rel="noreferrer" className="text-sm underline">
                Open the sheet ↗
              </a>
            )
          }
        >
          <p className="mb-2 text-sm text-fg-subtle">
            Writes {d.export_tabs.summary}, {d.export_tabs.stocks}, {d.export_tabs.mf} and {d.export_tabs.screener}, each stamped with the time and
            the disclaimer. {lastExport ? `Last export: ${when(lastExport.at)}.` : "Not exported yet."}
          </p>
          <SheetsExportButton status={d} />
        </Card>
      </div>
      <Card title="Recent activity">
        <History status={d} />
      </Card>
    </div>
  );
}

/** Import page tab: holdings from a sheet tab (service account) or a published CSV link. */
export function SheetImport({ onDone }: { onDone: (r: Imported) => void }) {
  const status = useQuery({ queryKey: ["sheets"], queryFn: sheetsApi.status });
  const qc = useQueryClient();
  const [kind, setKind] = useState<HoldingKind>("stocks");
  const [source, setSource] = useState<"tab" | "csv">("tab");
  const [tab, setTab] = useState<string | null>(null);
  const [url, setUrl] = useState<string | null>(null);
  const [need, setNeed] = useState<NeedsMapping | null>(null);
  const d = status.data;
  const savedTab = d ? (kind === "stocks" ? d.settings.stocks_tab : d.settings.mf_tab) : "";
  const savedUrl = d ? ((kind === "stocks" ? d.settings.stocks_csv_url : d.settings.mf_csv_url) ?? "") : "";
  const tabValue = tab ?? savedTab;
  const urlValue = url ?? savedUrl;
  const run = useMutation({
    mutationFn: (mapping?: ColumnMappingIn) =>
      sheetsApi.import({ kind, source, tab: source === "tab" ? tabValue : undefined, url: source === "csv" ? urlValue : undefined, mapping }),
    onSuccess: (r) => {
      if (r.status === "needs_mapping") setNeed(r);
      else {
        setNeed(null);
        onDone(r);
      }
    },
    onSettled: () => void qc.invalidateQueries({ queryKey: ["sheets"] }),
  });
  const tabReady = !!d?.service_account.configured && !!d.spreadsheet_url;
  const ready = source === "tab" ? tabReady && !!tabValue.trim() : !!urlValue.trim();
  if (need)
    return (
      <ColumnMapper
        key={`${need.header_row}-${need.headers.join("|")}`}
        need={need}
        busy={run.isPending}
        onSubmit={(m) => run.mutate(m)}
        onCancel={() => setNeed(null)}
      />
    );
  return (
    <div className="space-y-3 text-sm">
      <p className="text-fg-subtle">
        Same columns as a Groww export (name, quantity, average price; ISIN or symbol helps). Each import is a new snapshot that replaces the
        previous one of that kind.
      </p>
      <div className="flex flex-wrap gap-4">
        <fieldset>
          <legend className="mb-1 font-medium">Holdings</legend>
          {(["stocks", "mf"] as const).map((k) => (
            <label key={k} className="mr-3">
              <input type="radio" name="sheet-kind" checked={kind === k} onChange={() => setKind(k)} /> {k === "stocks" ? "Stocks" : "Mutual funds"}
            </label>
          ))}
        </fieldset>
        <fieldset>
          <legend className="mb-1 font-medium">Read from</legend>
          <label className="mr-3">
            <input type="radio" name="sheet-source" checked={source === "tab"} onChange={() => setSource("tab")} /> A tab of my sheet (service account)
          </label>
          <label>
            <input type="radio" name="sheet-source" checked={source === "csv"} onChange={() => setSource("csv")} /> A published CSV link
          </label>
        </fieldset>
      </div>
      {source === "tab" ? (
        <>
          <label className="block max-w-xs">
            <span className="mb-1 block font-medium">Tab name</span>
            <input className={inputClass} value={tabValue} onChange={(e) => setTab(e.target.value)} />
          </label>
          {d && !tabReady && <Alert tone="info">Add the service-account key and your sheet's link in Settings → Google Sheets first.</Alert>}
        </>
      ) : (
        <label className="block">
          <span className="mb-1 block font-medium">Published CSV link</span>
          <input className={inputClass} value={urlValue} onChange={(e) => setUrl(e.target.value)} placeholder="https://docs.google.com/spreadsheets/d/e/…/pub?output=csv" />
          <span className="mt-1 block text-xs text-fg-subtle">File → Share → Publish to web → choose the tab → Comma-separated values (.csv).</span>
        </label>
      )}
      <Button disabled={!ready || run.isPending} onClick={() => run.mutate(undefined)}>
        {run.isPending ? "Importing…" : "Import from Google Sheets"}
      </Button>
      {run.isError && <Alert tone="error">{run.error.message}</Alert>}
    </div>
  );
}
