import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { portfolioApi, type MFHolding, type StockHolding, type Suggestion } from "../api/client";
import { useDebounced } from "../hooks/useDebounced";
import { Alert, Button, Card, inputClass } from "./ui";

/** Lists holdings that couldn't be matched to an NSE symbol / AMFI scheme and lets the user pick one. */
export function UnresolvedFixer({ stocks, funds }: { stocks: StockHolding[]; funds: MFHolding[] }) {
  const s = stocks.filter((h) => h.resolution === "unresolved");
  const f = funds.filter((h) => h.resolution === "unresolved");
  if (s.length === 0 && f.length === 0) return null;
  return (
    <Card title={`Needs your help: ${s.length + f.length} unmatched holding(s)`}>
      <p className="mb-3 text-sm text-slate-500">
        Pick the right match. Your choice is remembered for future imports.
      </p>
      <ul className="space-y-4">
        {s.map((h) => (
          <li key={`s${h.id}`}>
            <FixRow kind="stock" id={h.id} title={h.name} subtitle={h.isin ?? "No ISIN"} initial={h.suggestions} />
          </li>
        ))}
        {f.map((h) => (
          <li key={`m${h.id}`}>
            <FixRow kind="mf" id={h.id} title={h.scheme_name} subtitle={h.folio ? `Folio ${h.folio}` : ""} initial={h.suggestions} />
          </li>
        ))}
      </ul>
    </Card>
  );
}

function FixRow(props: {
  kind: "stock" | "mf";
  id: number;
  title: string;
  subtitle: string;
  initial: Suggestion[];
}) {
  const { kind, id, title, subtitle, initial } = props;
  const qc = useQueryClient();
  const [query, setQuery] = useState("");
  const [bse, setBse] = useState("");
  const q = useDebounced(query.trim());
  const search = useQuery({
    queryKey: ["ref", kind, q],
    queryFn: () => (kind === "stock" ? portfolioApi.searchSecurities(q) : portfolioApi.searchSchemes(q)),
    enabled: q.length >= 2,
  });
  const fix = useMutation({
    mutationFn: (args: { code: string; exchange?: "NSE" | "BSE" }): Promise<StockHolding | MFHolding> =>
      kind === "stock"
        ? portfolioApi.fixTicker(id, args.code, args.exchange ?? "NSE")
        : portfolioApi.fixScheme(id, args.code),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["holdings"] }),
  });

  const options = q.length >= 2 ? (search.data ?? []) : initial;
  return (
    <div className="rounded border border-slate-200 p-3 dark:border-slate-800">
      <div className="font-medium">{title}</div>
      {subtitle && <div className="text-xs text-slate-500">{subtitle}</div>}
      <label className="mt-2 block text-sm">
        <span className="sr-only">Search</span>
        <input
          className={inputClass}
          placeholder={kind === "stock" ? "Search NSE symbol or company…" : "Search scheme name or AMFI code…"}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </label>
      <div className="mt-2 flex flex-wrap gap-2">
        {options.length === 0 && (
          <span className="text-sm text-slate-500">{q.length >= 2 ? "No matches." : "No suggestions; search above."}</span>
        )}
        {options.map((o) => {
          const code = (kind === "stock" ? o.symbol : o.amfi_code) ?? "";
          return (
            <Button key={code} variant="secondary" disabled={fix.isPending} onClick={() => fix.mutate({ code })}>
              <span className="font-mono">{code}</span> · {o.name}{" "}
              <span className="text-xs text-slate-500">({Math.round(o.score)}% match)</span>
            </Button>
          );
        })}
      </div>
      {kind === "stock" && (
        <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
          <span className="text-slate-500">Only on BSE?</span>
          <input
            className={`${inputClass} w-40`}
            placeholder="BSE symbol, e.g. TCS"
            value={bse}
            onChange={(e) => setBse(e.target.value)}
            aria-label="BSE symbol"
          />
          <Button variant="secondary" disabled={!bse.trim() || fix.isPending} onClick={() => fix.mutate({ code: bse.trim().toUpperCase(), exchange: "BSE" })}>
            Use BSE
          </Button>
        </div>
      )}
      {fix.isError && (
        <div className="mt-2">
          <Alert tone="error">{fix.error.message}</Alert>
        </div>
      )}
    </div>
  );
}
