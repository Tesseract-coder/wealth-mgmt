import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { importApi, portfolioApi, type ColumnMappingIn, type FundPortfolioImported, type NeedsMapping } from "../api/client";
import { ColumnMapper } from "./ColumnMapper";
import { FileDrop } from "./FileDrop";
import { Alert, Button, inputClass } from "./ui";

/** Upload a fund's holdings from the AMC's monthly portfolio file, for fund overlap. */
export function FundPortfolioImport() {
  const qc = useQueryClient();
  const holdings = useQuery({ queryKey: ["holdings"], queryFn: portfolioApi.holdings });
  const funds = (holdings.data?.mf ?? []).filter((m) => m.amfi_code);
  const [code, setCode] = useState("");
  const [asOf, setAsOf] = useState("");
  const [sheet, setSheet] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [need, setNeed] = useState<NeedsMapping | null>(null);
  const [result, setResult] = useState<FundPortfolioImported | null>(null);
  const run = useMutation({
    mutationFn: (mapping?: ColumnMappingIn) =>
      importApi.fundPortfolio(file!, code, { asOf: asOf || undefined, sheet: sheet.trim() || undefined, mapping }),
    onSuccess: (r) => {
      if (r.status === "needs_mapping") {
        setNeed(r);
        return;
      }
      setNeed(null);
      setFile(null);
      setResult(r);
      void qc.invalidateQueries({ queryKey: ["mf-holdings"] });
      void qc.invalidateQueries({ queryKey: ["mf"] });
    },
  });
  return (
    <div className="space-y-3">
      <p className="text-sm text-slate-500">
        To measure how much your funds overlap, upload each fund&apos;s holdings. Every AMC publishes a monthly portfolio file (Excel) on its website,
        often with one sheet per scheme: enter that sheet&apos;s name. Columns like <i>Name of the Instrument, ISIN, % to Net Assets</i> are found
        automatically.
      </p>
      {funds.length === 0 ? (
        <Alert tone="info">Import your mutual funds first.</Alert>
      ) : need ? (
        <ColumnMapper key={need.headers.join("|")} need={need} busy={run.isPending} onSubmit={(m) => run.mutate(m)} onCancel={() => setNeed(null)} />
      ) : (
        <>
          <label className="block max-w-lg text-sm">
            <span className="text-slate-500">Fund</span>
            <select className={inputClass} value={code} onChange={(e) => setCode(e.target.value)}>
              <option value="">Choose one of your funds…</option>
              {funds.map((m) => (
                <option key={m.id} value={m.amfi_code ?? ""}>
                  {m.scheme_name}
                </option>
              ))}
            </select>
          </label>
          <div className="flex flex-wrap gap-3">
            <label className="text-sm">
              <span className="block text-slate-500">Portfolio date</span>
              <input type="date" className={inputClass} value={asOf} onChange={(e) => setAsOf(e.target.value)} />
            </label>
            <label className="text-sm">
              <span className="block text-slate-500">Sheet name (if several schemes)</span>
              <input className={inputClass} value={sheet} onChange={(e) => setSheet(e.target.value)} placeholder="optional" />
            </label>
          </div>
          <FileDrop accept=".xlsx,.csv" hint=".xlsx or .csv from the AMC website" file={file} onFile={setFile} disabled={run.isPending} />
          <Button disabled={!file || !code || run.isPending} onClick={() => run.mutate(undefined)}>
            {run.isPending ? "Uploading…" : "Upload"}
          </Button>
        </>
      )}
      {run.isError && <Alert tone="error">{run.error.message}</Alert>}
      {result && (
        <Alert tone="success">
          Saved {result.rows} holdings for {result.scheme_name} (weights add up to {result.total_weight_pct}%).
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
