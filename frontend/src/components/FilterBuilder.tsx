import { useState } from "react";
import type { FilterOp, ScreenField, ScreenFilter } from "../api/client";
import { Button, inputClass } from "./ui";

/** A builder row keeps what you typed as text; it becomes a number when valid. */
export interface Draft {
  field: string;
  op: FilterOp;
  a: string;
  b: string;
}

export const toDraft = (f: ScreenFilter): Draft =>
  Array.isArray(f.value)
    ? { field: f.field, op: f.op, a: String(f.value[0]), b: String(f.value[1]) }
    : { field: f.field, op: f.op, a: String(f.value), b: "" };

const num = (s: string): number | null => {
  if (s.trim() === "") return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
};

/** Filters from drafts, or the first problem in words. */
export function fromDrafts(drafts: Draft[], fields: ScreenField[]): { filters: ScreenFilter[]; error: string | null } {
  const filters: ScreenFilter[] = [];
  for (const d of drafts) {
    const label = fields.find((f) => f.key === d.field)?.label ?? d.field;
    const a = num(d.a);
    if (a === null) return { filters, error: `${label}: enter a number` };
    if (d.op === "between") {
      const b = num(d.b);
      if (b === null) return { filters, error: `${label}: enter both ends of the range` };
      if (a > b) return { filters, error: `${label}: the low end is above the high end` };
      filters.push({ field: d.field, op: d.op, value: [a, b] });
    } else filters.push({ field: d.field, op: d.op, value: a });
  }
  if (filters.length === 0) return { filters, error: "Add at least one condition" };
  return { filters, error: null };
}

const GROUPS = ["Technical", "Fundamental", "Score"] as const;

/** Rows of "field  op  value"; every row must hold. */
export function FilterBuilder({
  fields,
  ops,
  drafts,
  onChange,
}: {
  fields: ScreenField[];
  ops: Record<FilterOp, string>;
  drafts: Draft[];
  onChange: (d: Draft[]) => void;
}) {
  const set = (i: number, patch: Partial<Draft>) => onChange(drafts.map((d, j) => (j === i ? { ...d, ...patch } : d)));
  return (
    <div className="space-y-2">
      {drafts.length === 0 && <p className="text-sm text-slate-500">No conditions yet.</p>}
      {drafts.map((d, i) => {
        const meta = fields.find((f) => f.key === d.field);
        const unit = meta?.unit && meta.unit !== "₹" ? meta.unit : "";
        return (
          <div key={i} className="flex flex-wrap items-center gap-2 text-sm" role="group" aria-label={`Condition ${i + 1}`}>
            <select aria-label="Field" className={`${inputClass} !w-60`} value={d.field} onChange={(e) => set(i, { field: e.target.value })}>
              {GROUPS.map((g) => (
                <optgroup key={g} label={g}>
                  {fields
                    .filter((f) => f.group === g)
                    .map((f) => (
                      <option key={f.key} value={f.key}>
                        {f.label}
                      </option>
                    ))}
                </optgroup>
              ))}
            </select>
            <select aria-label="Condition" className={`${inputClass} !w-28`} value={d.op} onChange={(e) => set(i, { op: e.target.value as FilterOp })}>
              {(Object.keys(ops) as FilterOp[]).map((o) => (
                <option key={o} value={o}>
                  {ops[o]}
                </option>
              ))}
            </select>
            <input aria-label={d.op === "between" ? "From" : "Value"} inputMode="decimal" className={`${inputClass} !w-24`} value={d.a} onChange={(e) => set(i, { a: e.target.value })} />
            {d.op === "between" && (
              <>
                <span>and</span>
                <input aria-label="To" inputMode="decimal" className={`${inputClass} !w-24`} value={d.b} onChange={(e) => set(i, { b: e.target.value })} />
              </>
            )}
            {unit && <span className="text-slate-500">{unit}</span>}
            <Button variant="secondary" className="!px-2 !py-1" aria-label={`Remove condition ${i + 1}`} onClick={() => onChange(drafts.filter((_, j) => j !== i))}>
              Remove
            </Button>
            {meta && <span className="basis-full text-xs text-slate-500 sm:basis-auto">{meta.help}</span>}
          </div>
        );
      })}
      <Button variant="secondary" onClick={() => onChange([...drafts, { field: fields[0]?.key ?? "rsi", op: "gte", a: "", b: "" }])}>
        + Add condition
      </Button>
    </div>
  );
}

/** Name box + Save; used for new and existing screens. */
export function SaveScreen({ initial, onSave, busy }: { initial: string; onSave: (name: string) => void; busy: boolean }) {
  const [name, setName] = useState(initial);
  return (
    <form
      className="flex flex-wrap items-end gap-2 text-sm"
      onSubmit={(e) => {
        e.preventDefault();
        if (name.trim()) onSave(name.trim());
      }}
    >
      <label>
        <span className="mb-1 block text-slate-500">Screen name</span>
        <input className={`${inputClass} !w-56`} value={name} maxLength={80} onChange={(e) => setName(e.target.value)} placeholder="e.g. Cheap quality" />
      </label>
      <Button type="submit" variant="secondary" disabled={busy || !name.trim()}>
        Save screen
      </Button>
    </form>
  );
}
