import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { fundamentalApi, type GrowthGuidance } from "../../api/client";
import { formatPct } from "../../lib/format";
import { Button, inputClass } from "../ui";

/**
 * The expected yearly growth behind the PEG (current P/E ÷ expected growth). Analyst consensus by
 * default; your own figure (say, management's 3-year guidance) replaces it once saved.
 */
export function GrowthGuidanceEditor({ ticker, pe, peg }: { ticker: string; pe: number | null; peg: number | null }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["growth-guidance", ticker], queryFn: () => fundamentalApi.guidance(ticker) });
  const save = useMutation({
    mutationFn: (v: number | null) => fundamentalApi.saveGuidance(ticker, v),
    onSuccess: (g: GrowthGuidance) => {
      qc.setQueryData(["growth-guidance", ticker], g);
      // The PEG feeds the checks, scores and signals: everything shown needs working out again.
      void qc.invalidateQueries({ predicate: (x) => x.queryKey[0] !== "growth-guidance" });
    },
  });
  const [draft, setDraft] = useState<string | null>(null);
  const g = q.data;
  const value = draft ?? (g?.growth_pct != null ? String(g.growth_pct) : "");
  const n = value.trim() === "" ? null : Number(value);
  const invalid = n !== null && (!Number.isFinite(n) || n < -100 || n > 500);
  const preview = pe != null && n !== null && !invalid && n > 0 ? pe / n : null;

  return (
    <section aria-labelledby="growth-guidance" className="rounded-card border border-border bg-surface-2 p-3 text-sm">
      <h3 id="growth-guidance" className="font-semibold text-fg">
        PEG {peg != null ? peg.toFixed(2) : "—"}
        <span className="font-normal text-fg-muted"> = current P/E {pe != null ? pe.toFixed(1) : "—"} ÷ expected yearly profit growth</span>
      </h3>
      <p className="mt-1 text-xs text-fg-subtle">
        {g?.growth_pct != null
          ? `Using your guidance of ${formatPct(g.growth_pct)} a year.`
          : g?.analyst_pct != null
            ? `Using the ${g.analyst_basis}: ${formatPct(g.analyst_pct)} a year.`
            : "No analyst estimate for this stock: enter your own growth to get a PEG."}
        {g?.growth_pct != null && g.analyst_pct != null && ` Analysts expect ${formatPct(g.analyst_pct)}.`}
      </p>
      <form
        className="mt-2 flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (!invalid) save.mutate(n, { onSuccess: () => setDraft(null) });
        }}
      >
        <label>
          <span className="mb-1 block text-xs font-medium text-fg-muted">Your 3-year growth guidance (% a year)</span>
          <input
            className={`${inputClass} w-32`}
            inputMode="decimal"
            placeholder={g?.analyst_pct != null ? g.analyst_pct.toFixed(1) : "e.g. 20"}
            value={value}
            onChange={(e) => setDraft(e.target.value)}
            aria-invalid={invalid}
          />
        </label>
        <Button type="submit" size="md" disabled={invalid || save.isPending || draft === null}>
          {save.isPending ? "Saving…" : "Save"}
        </Button>
        {g?.growth_pct != null && (
          <Button type="button" variant="secondary" size="md" disabled={save.isPending} onClick={() => save.mutate(null, { onSuccess: () => setDraft(null) })}>
            Use analysts
          </Button>
        )}
        {preview !== null && draft !== null && <span className="text-xs text-fg-muted">PEG would be {preview.toFixed(2)}</span>}
      </form>
      {invalid && <p className="mt-1 text-xs text-bad">Enter a number between −100 and 500.</p>}
      {save.isError && <p className="mt-1 text-xs text-bad">Couldn't save: {save.error.message}</p>}
    </section>
  );
}
