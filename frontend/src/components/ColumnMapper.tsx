import { useState } from "react";
import type { ColumnMappingIn, NeedsMapping } from "../api/client";
import { Alert, Button, inputClass } from "./ui";

interface Props {
  need: NeedsMapping;
  busy: boolean;
  onSubmit: (mapping: ColumnMappingIn) => void;
  onCancel: () => void;
}

/** Shown when the importer can't find every required column on its own. */
export function ColumnMapper({ need, busy, onSubmit, onCancel }: Props) {
  const [columns, setColumns] = useState<Record<string, number>>(need.detected);
  const [headerRow, setHeaderRow] = useState(need.header_row);
  const [remember, setRemember] = useState(true);

  const used = new Map<number, string>();
  Object.entries(columns).forEach(([k, c]) => used.set(c, k));
  const missing = need.fields.filter((f) => f.required && columns[f.key] === undefined);
  const mfNeedsValue =
    need.kind === "mf" && columns.units === undefined && columns.current_value === undefined;
  const headerChanged = headerRow !== need.header_row;

  const set = (key: string, value: string) =>
    setColumns((prev) => {
      const next = { ...prev };
      if (value === "") delete next[key];
      else next[key] = Number(value);
      return next;
    });

  return (
    <div className="space-y-4">
      <Alert tone="warning">
        Some columns could not be recognised. Match each field to a column in your file. Fields marked * are
        required{need.kind === "mf" ? ", plus either Units or Current value" : ""}.
      </Alert>

      <div className="flex flex-wrap items-end gap-3">
        <label className="text-sm">
          <span className="mb-1 block font-medium">Header row in the file</span>
          <input
            type="number"
            min={1}
            className={`${inputClass} w-24`}
            value={headerRow + 1}
            onChange={(e) => setHeaderRow(Math.max(0, Number(e.target.value) - 1))}
          />
        </label>
        {headerChanged && (
          <span className="text-sm text-fg-subtle">
            Submit to reload the column names from row {headerRow + 1}.
          </span>
        )}
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        {need.fields.map((f) => (
          <label key={f.key} className="text-sm">
            <span className="mb-1 block font-medium">
              {f.label}
              {f.required && <span aria-label="required"> *</span>}
            </span>
            <select
              className={inputClass}
              value={columns[f.key] ?? ""}
              onChange={(e) => set(f.key, e.target.value)}
            >
              <option value="">— not in this file —</option>
              {need.headers.map((h, i) =>
                h ? (
                  <option key={i} value={i} disabled={used.has(i) && used.get(i) !== f.key}>
                    {h}
                  </option>
                ) : null,
              )}
            </select>
          </label>
        ))}
      </div>

      {need.preview.length > 0 && (
        <div className="overflow-x-auto">
          <p className="mb-1 text-sm font-medium">First rows of your file</p>
          <table className="min-w-full text-left text-xs">
            <thead>
              <tr>
                {need.headers.map((h, i) => (
                  <th key={i} className="border-b border-border px-2 py-1">
                    {h || `(column ${i + 1})`}
                    {used.has(i) && <div className="font-normal text-good">→ {used.get(i)}</div>}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {need.preview.map((row, r) => (
                <tr key={r}>
                  {need.headers.map((_, c) => (
                    <td key={c} className="border-b border-border px-2 py-1">
                      {row[c] ?? ""}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
        Remember this mapping for files with the same columns
      </label>

      <div className="flex gap-2">
        <Button
          disabled={busy || (!headerChanged && (missing.length > 0 || mfNeedsValue))}
          onClick={() =>
            onSubmit({ header_row: headerRow, columns: headerChanged ? {} : columns, remember })
          }
        >
          {busy ? "Importing…" : headerChanged ? "Reload columns" : "Import with this mapping"}
        </Button>
        <Button variant="secondary" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
