import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { importApi, type ColumnMappingIn, type NeedsMapping, type ScreenerImported } from "../api/client";
import { ColumnMapper } from "./ColumnMapper";
import { FileDrop } from "./FileDrop";
import { Alert, Button, inputClass } from "./ui";

/** Upload a file exported from Screener.in by the user (the app never visits Screener.in). */
export function ScreenerImport() {
  const qc = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [symbol, setSymbol] = useState("");
  const [need, setNeed] = useState<NeedsMapping | null>(null);
  const [result, setResult] = useState<ScreenerImported | null>(null);
  const run = useMutation({
    mutationFn: (mapping?: ColumnMappingIn) => importApi.screener(file!, mapping, symbol.trim() || undefined),
    onSuccess: (r) => {
      if (r.status === "needs_mapping") {
        setNeed(r);
        return;
      }
      setNeed(null);
      setFile(null);
      setResult(r);
      void qc.invalidateQueries({ queryKey: ["fundamental"] });
      void qc.invalidateQueries({ queryKey: ["fund-holdings"] });
    },
  });
  return (
    <div className="space-y-3">
      <div className="text-sm text-fg-subtle">
        <p>Two kinds of Screener.in export are understood. Download them yourself while logged in to screener.in:</p>
        <ul className="mt-1 list-disc pl-5">
          <li>
            <b>A screen&apos;s results</b> (Export button above a screen&apos;s table): add the columns <i>NSE Code, Promoter holding,
            Change in promoter holding, Pledged percentage, FII holding, Change in FII holding, DII holding, Change in DII holding</i>{" "}
            for ownership readings.
          </li>
          <li>
            <b>A company&apos;s Excel file</b> (&quot;Export to Excel&quot; on a company page): about 10 years of results, so 5-year growth
            can be measured.
          </li>
        </ul>
      </div>
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
          <FileDrop accept=".xlsx,.csv" hint=".csv or .xlsx from Screener.in" file={file} onFile={setFile} disabled={run.isPending} />
          <label className="block max-w-xs text-sm">
            <span className="text-fg-subtle">NSE symbol (only if a company file isn&apos;t matched automatically)</span>
            <input className={inputClass} value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="e.g. ITC" />
          </label>
          <Button disabled={!file || run.isPending} onClick={() => run.mutate(undefined)}>
            {run.isPending ? "Uploading…" : "Upload"}
          </Button>
        </>
      )}
      {run.isError && <Alert tone="error">{run.error.message}</Alert>}
      {result && (
        <Alert tone="success">
          {result.kind === "company" ? "Company results" : "Screen data"} saved for {result.matched.length} stock(s):{" "}
          {result.matched.map((m) => m.symbol).join(", ") || "none"}.
          {result.unmatched.length > 0 && (
            <div className="mt-1">Not matched to an NSE symbol: {result.unmatched.join(", ")}.</div>
          )}
          {result.warnings.map((w) => (
            <div key={w} className="mt-1">
              {w}
            </div>
          ))}
        </Alert>
      )}
    </div>
  );
}
