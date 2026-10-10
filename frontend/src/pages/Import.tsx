import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import {
  importApi,
  portfolioApi,
  type ColumnMappingIn,
  type HoldingKind,
  type Imported,
  type MFHolding,
  type NeedsMapping,
  type StockHolding,
} from "../api/client";
import { ColumnMapper } from "../components/ColumnMapper";
import { ScreenerImport } from "../components/ScreenerImport";
import { FileDrop } from "../components/FileDrop";
import { Alert, Button, Card, inputClass } from "../components/ui";
import { UnresolvedFixer } from "../components/UnresolvedFixer";
import { formatINR } from "../lib/format";

type Tab = "stocks" | "mf" | "cas" | "manual" | "screener";
const TABS: { key: Tab; label: string }[] = [
  { key: "stocks", label: "Groww stocks" },
  { key: "mf", label: "Groww mutual funds" },
  { key: "cas", label: "CAS PDF" },
  { key: "manual", label: "Add fund manually" },
  { key: "screener", label: "Screener.in data" },
];

export function Import() {
  const [tab, setTab] = useState<Tab>("stocks");
  const [result, setResult] = useState<Imported | null>(null);
  const holdings = useQuery({ queryKey: ["holdings"], queryFn: portfolioApi.holdings });
  const qc = useQueryClient();
  const done = (r: Imported) => {
    setResult(r);
    void qc.invalidateQueries({ queryKey: ["holdings"] });
    void qc.invalidateQueries({ queryKey: ["snapshots"] });
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Import holdings</h1>
      <Card>
        <div role="tablist" className="mb-4 flex flex-wrap gap-1 border-b border-slate-200 dark:border-slate-800">
          {TABS.map((t) => (
            <button
              key={t.key}
              role="tab"
              aria-selected={tab === t.key}
              onClick={() => {
                setTab(t.key);
                setResult(null);
              }}
              className={`-mb-px border-b-2 px-3 py-2 text-sm ${
                tab === t.key ? "border-slate-900 font-medium dark:border-slate-100" : "border-transparent text-slate-500"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
        {tab === "stocks" && <TabularImport key="stocks" kind="stocks" onDone={done} />}
        {tab === "mf" && <TabularImport key="mf" kind="mf" onDone={done} />}
        {tab === "cas" && <CasImport onDone={done} />}
        {tab === "manual" && <ManualFund onDone={done} />}
        {tab === "screener" && <ScreenerImport />}
      </Card>

      {result && <ResultSummary result={result} />}
      {holdings.data && <UnresolvedFixer stocks={holdings.data.stocks} funds={holdings.data.mf} />}
      {holdings.data && <LatestHoldings stocks={holdings.data.stocks} funds={holdings.data.mf} />}
      <SnapshotHistory />
    </div>
  );
}

function TabularImport({ kind, onDone }: { kind: HoldingKind; onDone: (r: Imported) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [need, setNeed] = useState<NeedsMapping | null>(null);
  const run = useMutation({
    mutationFn: (mapping?: ColumnMappingIn) => importApi.tabular(kind, file!, mapping),
    onSuccess: (r) => {
      if (r.status === "needs_mapping") setNeed(r);
      else {
        setNeed(null);
        setFile(null);
        onDone(r);
      }
    },
  });
  return (
    <div className="space-y-3">
      <p className="text-sm text-slate-500">
        {kind === "stocks"
          ? "Groww web → Stocks → Holdings → Download (XLSX or CSV)."
          : "Groww web → Mutual Funds → Dashboard → Download holdings (XLSX or CSV)."}{" "}
        See docs/GROWW_EXPORT_GUIDE.md.
      </p>
      {need ? (
        <ColumnMapper
          key={`${need.header_row}-${need.headers.join("|")}`}
          need={need}
          busy={run.isPending}
          onSubmit={(m) => run.mutate(m)}
          onCancel={() => {
            setNeed(null);
            setFile(null);
          }}
        />
      ) : (
        <>
          <FileDrop accept=".xlsx,.csv" hint=".xlsx or .csv" file={file} onFile={setFile} disabled={run.isPending} />
          <Button disabled={!file || run.isPending} onClick={() => run.mutate(undefined)}>
            {run.isPending ? "Importing…" : "Import"}
          </Button>
        </>
      )}
      {run.isError && <Alert tone="error">{run.error.message}</Alert>}
    </div>
  );
}

function CasImport({ onDone }: { onDone: (r: Imported) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [password, setPassword] = useState("");
  const run = useMutation({
    mutationFn: () => importApi.cas(file!, password),
    onSettled: () => setPassword(""), // never keep the password around
    onSuccess: (r) => {
      setFile(null);
      onDone(r);
    },
  });
  return (
    <form
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        run.mutate();
      }}
    >
      <p className="text-sm text-slate-500">
        Consolidated Account Statement from CAMS or KFintech (or NSDL/CDSL). A detailed CAS includes transactions, which
        later phases use for your own XIRR and holding periods.
      </p>
      <FileDrop accept=".pdf" hint=".pdf" file={file} onFile={setFile} disabled={run.isPending} />
      <label className="block text-sm">
        <span className="mb-1 block font-medium">PDF password</span>
        <input
          type="password"
          autoComplete="off"
          className={`${inputClass} max-w-xs`}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <span className="mt-1 block text-xs text-slate-500">
          Used once to open the file, then discarded. It is never saved.
        </span>
      </label>
      <Button type="submit" disabled={!file || !password || run.isPending}>
        {run.isPending ? "Reading PDF…" : "Import CAS"}
      </Button>
      {run.isError && <Alert tone="error">{run.error.message}</Alert>}
    </form>
  );
}

function ManualFund({ onDone }: { onDone: (r: Imported) => void }) {
  const [scheme, setScheme] = useState("");
  const [units, setUnits] = useState("");
  const [invested, setInvested] = useState("");
  const [folio, setFolio] = useState("");
  const [date, setDate] = useState("");
  const run = useMutation({
    mutationFn: () =>
      importApi.manualMf({
        scheme,
        units: Number(units),
        invested: Number(invested),
        folio: folio || null,
        purchase_date: date || null,
      }),
    onSuccess: (r) => {
      setScheme("");
      setUnits("");
      setInvested("");
      setFolio("");
      setDate("");
      onDone(r);
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    run.mutate();
  };
  const valid = scheme.trim() && Number(units) > 0 && Number(invested) >= 0 && invested !== "";
  return (
    <form className="grid gap-3 sm:grid-cols-2" onSubmit={submit}>
      <label className="text-sm sm:col-span-2">
        <span className="mb-1 block font-medium">AMFI scheme code or scheme name *</span>
        <input className={inputClass} value={scheme} onChange={(e) => setScheme(e.target.value)} placeholder="e.g. 122639" />
        <span className="mt-1 block text-xs text-slate-500">
          A code is exact. A name is matched; if it can't be matched you can pick the scheme afterwards.
        </span>
      </label>
      <label className="text-sm">
        <span className="mb-1 block font-medium">Units *</span>
        <input className={inputClass} inputMode="decimal" value={units} onChange={(e) => setUnits(e.target.value)} />
      </label>
      <label className="text-sm">
        <span className="mb-1 block font-medium">Amount invested (₹) *</span>
        <input className={inputClass} inputMode="decimal" value={invested} onChange={(e) => setInvested(e.target.value)} />
      </label>
      <label className="text-sm">
        <span className="mb-1 block font-medium">Folio (optional)</span>
        <input className={inputClass} value={folio} onChange={(e) => setFolio(e.target.value)} />
      </label>
      <label className="text-sm">
        <span className="mb-1 block font-medium">First purchase date (optional)</span>
        <input type="date" className={inputClass} value={date} onChange={(e) => setDate(e.target.value)} />
      </label>
      <div className="sm:col-span-2">
        <Button type="submit" disabled={!valid || run.isPending}>
          {run.isPending ? "Adding…" : "Add fund"}
        </Button>
      </div>
      {run.isError && (
        <div className="sm:col-span-2">
          <Alert tone="error">{run.error.message}</Alert>
        </div>
      )}
    </form>
  );
}

function ResultSummary({ result }: { result: Imported }) {
  const s = result.snapshot;
  return (
    <Card title="Import complete">
      <div className="space-y-3">
        <Alert tone="success">
          Imported {s.row_count} {s.kind === "stocks" ? "stock" : "fund"} holding(s) as snapshot #{s.id}.
          {s.total_value !== null && <> Value {formatINR(s.total_value)}.</>}
          {result.unresolved > 0 && <> {result.unresolved} need a match below.</>}
        </Alert>
        {result.warnings.map((w, i) => (
          <Alert key={i} tone="warning">
            {w}
          </Alert>
        ))}
        {result.skipped.length > 0 && (
          <details className="text-sm">
            <summary className="cursor-pointer">{result.skipped.length} row(s) skipped</summary>
            <ul className="mt-2 space-y-1">
              {result.skipped.map((r) => (
                <li key={r.row}>
                  Row {r.row}: <span className="font-medium">{r.reason}</span>{" "}
                  <span className="text-slate-500">({r.text})</span>
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </Card>
  );
}

function Resolution({ value }: { value: string }) {
  const unresolved = value === "unresolved";
  return (
    <span
      className={`rounded px-1.5 py-0.5 text-xs ${
        unresolved ? "bg-amber-100 text-amber-900 dark:bg-amber-900 dark:text-amber-100" : "bg-slate-100 dark:bg-slate-800"
      }`}
    >
      {unresolved ? "Unmatched" : `by ${value}`}
    </span>
  );
}

function LatestHoldings({ stocks, funds }: { stocks: StockHolding[]; funds: MFHolding[] }) {
  const qc = useQueryClient();
  const remove = useMutation({
    mutationFn: (id: number) => portfolioApi.deleteMf(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["holdings"] }),
  });
  if (stocks.length === 0 && funds.length === 0) return null;
  const th = "px-2 py-1 font-medium";
  const td = "px-2 py-1";
  return (
    <Card title="Latest imported holdings (raw)">
      <p className="mb-3 text-sm text-slate-500">
        As imported. Live prices, scores and signals come in later phases.
      </p>
      {stocks.length > 0 && (
        <div className="mb-6 overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-slate-200 dark:border-slate-700">
              <tr>
                <th className={th}>Stock</th>
                <th className={th}>Symbol</th>
                <th className={`${th} text-right`}>Qty</th>
                <th className={`${th} text-right`}>Avg price</th>
                <th className={`${th} text-right`}>Invested</th>
                <th className={`${th} text-right`}>Value (file)</th>
              </tr>
            </thead>
            <tbody>
              {stocks.map((h) => (
                <tr key={h.id} className="border-b border-slate-100 dark:border-slate-800">
                  <td className={td}>{h.name}</td>
                  <td className={td}>
                    <span className="font-mono">{h.symbol ?? "—"}</span>
                    {h.exchange === "BSE" && <span className="text-xs"> (BSE)</span>} <Resolution value={h.resolution} />
                  </td>
                  <td className={`${td} text-right`}>{h.quantity}</td>
                  <td className={`${td} text-right`}>{formatINR(h.avg_price)}</td>
                  <td className={`${td} text-right`}>{formatINR(h.invested)}</td>
                  <td className={`${td} text-right`}>{formatINR(h.current_value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {funds.length > 0 && (
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-slate-200 dark:border-slate-700">
              <tr>
                <th className={th}>Fund</th>
                <th className={th}>AMFI code</th>
                <th className={th}>Plan</th>
                <th className={`${th} text-right`}>Units</th>
                <th className={`${th} text-right`}>Invested</th>
                <th className={`${th} text-right`}>Value</th>
                <th className={th}></th>
              </tr>
            </thead>
            <tbody>
              {funds.map((h) => (
                <tr key={h.id} className="border-b border-slate-100 dark:border-slate-800">
                  <td className={td}>
                    {h.scheme_name}
                    {h.origin === "manual" && <span className="ml-1 text-xs text-slate-500">(manual)</span>}
                  </td>
                  <td className={td}>
                    <span className="font-mono">{h.amfi_code ?? "—"}</span> <Resolution value={h.resolution} />
                  </td>
                  <td className={td}>{h.plan ? `${h.plan} · ${h.option ?? "?"}` : "—"}</td>
                  <td className={`${td} text-right`}>{h.units.toFixed(3)}</td>
                  <td className={`${td} text-right`}>{formatINR(h.invested)}</td>
                  <td className={`${td} text-right`}>
                    {formatINR(h.current_value)}
                    {h.nav_date && <div className="text-xs text-slate-500">NAV {h.nav_date}</div>}
                  </td>
                  <td className={td}>
                    {h.origin === "manual" && (
                      <Button variant="danger" disabled={remove.isPending} onClick={() => remove.mutate(h.id)}>
                        Remove
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

function SnapshotHistory() {
  const snaps = useQuery({ queryKey: ["snapshots"], queryFn: portfolioApi.snapshots });
  if (!snaps.data?.length) return null;
  return (
    <Card title="Snapshot history">
      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-slate-200 dark:border-slate-700">
            <tr>
              <th className="px-2 py-1">#</th>
              <th className="px-2 py-1">When</th>
              <th className="px-2 py-1">Type</th>
              <th className="px-2 py-1">Source</th>
              <th className="px-2 py-1 text-right">Rows</th>
              <th className="px-2 py-1 text-right">Value</th>
            </tr>
          </thead>
          <tbody>
            {snaps.data.map((s) => (
              <tr key={s.id} className="border-b border-slate-100 dark:border-slate-800">
                <td className="px-2 py-1">{s.id}</td>
                <td className="px-2 py-1">{new Date(s.created_at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })}</td>
                <td className="px-2 py-1">{s.kind === "stocks" ? "Stocks" : "Mutual funds"}</td>
                <td className="px-2 py-1">
                  {s.source}
                  {s.filename && <span className="text-slate-500"> · {s.filename}</span>}
                  {s.note && <span className="text-slate-500"> · {s.note}</span>}
                </td>
                <td className="px-2 py-1 text-right">{s.row_count}</td>
                <td className="px-2 py-1 text-right">{formatINR(s.total_value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
