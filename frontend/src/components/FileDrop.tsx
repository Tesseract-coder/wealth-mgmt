import { FileCheck2, LoaderCircle, UploadCloud } from "lucide-react";
import { useId, useState } from "react";

interface Props {
  accept: string;
  hint: string;
  file: File | null;
  onFile: (file: File) => void;
  disabled?: boolean;
  /** Shown while the chosen file uploads, e.g. "Uploading and matching tickers…". */
  busyLabel?: string;
}

const size = (n: number) => (n >= 1_048_576 ? `${(n / 1_048_576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);

/**
 * A drag-and-drop zone that's also a file button (keyboard: Tab to it, Enter or Space to choose).
 * It shows each state in words: waiting, dragging over, file chosen, uploading.
 */
export function FileDrop({ accept, hint, file, onFile, disabled, busyLabel }: Props) {
  const [over, setOver] = useState(false);
  const id = useId();
  const busy = !!busyLabel && disabled;
  const Icon = busy ? LoaderCircle : file ? FileCheck2 : UploadCloud;
  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        const f = e.dataTransfer.files[0];
        if (f && !disabled) onFile(f);
      }}
      className={`flex flex-col items-center justify-center gap-2 rounded-card border-2 border-dashed p-6 text-center text-sm transition-colors ${
        over ? "border-accent bg-accent-soft" : file ? "border-good-border bg-good-soft/40" : "border-border-strong bg-surface"
      } ${disabled ? "opacity-80" : ""}`}
    >
      <Icon aria-hidden className={`size-8 ${busy ? "animate-spin text-accent-text" : file ? "text-good" : "text-fg-subtle"}`} />
      <p aria-live="polite" className="text-fg">
        {busy ? (
          <span className="font-medium">{busyLabel}</span>
        ) : over ? (
          <span className="font-medium">Drop the file to choose it</span>
        ) : file ? (
          <>
            <span className="font-medium">{file.name}</span> <span className="text-fg-subtle">({size(file.size)})</span>
          </>
        ) : (
          <span className="font-medium">Drag and drop your file here</span>
        )}
      </p>
      {!busy && (
        <p className="text-fg-muted">
          <label
            htmlFor={id}
            className={`cursor-pointer rounded font-medium text-accent-text underline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-[var(--focus)] ${disabled ? "pointer-events-none" : ""}`}
          >
            {file ? "Choose a different file" : "or choose a file"}
            <input
              id={id}
              type="file"
              accept={accept}
              disabled={disabled}
              className="sr-only"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) onFile(f);
                e.target.value = "";
              }}
            />
          </label>{" "}
          · {hint}
        </p>
      )}
    </div>
  );
}

/** Where an import has got to: File → Upload → Columns → Match tickers → Done. */
export type ImportStage = "file" | "upload" | "columns" | "match" | "done";
const STAGES: { key: ImportStage; label: string }[] = [
  { key: "file", label: "Choose file" },
  { key: "upload", label: "Upload" },
  { key: "columns", label: "Check columns" },
  { key: "match", label: "Match tickers" },
  { key: "done", label: "Done" },
];

export function ImportSteps({ stage, needsAction = false }: { stage: ImportStage; needsAction?: boolean }) {
  const at = STAGES.findIndex((s) => s.key === stage);
  return (
    <ol aria-label="Import progress" className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
      {STAGES.map((s, i) => {
        const done = i < at || (stage === "done" && i === at);
        const current = i === at && stage !== "done";
        return (
          <li key={s.key} aria-current={current ? "step" : undefined} className="flex items-center gap-2">
            <span
              className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-medium ${
                done ? "border-good-border bg-good-soft text-good" : current ? (needsAction ? "border-caution-border bg-caution-soft text-caution" : "border-accent bg-accent-soft text-accent-text") : "border-border text-fg-subtle"
              }`}
            >
              {done ? "✓" : i + 1} {s.label}
              <span className="sr-only">{done ? " (done)" : current ? (needsAction ? " (needs you)" : " (in progress)") : ""}</span>
            </span>
            {i < STAGES.length - 1 && <span aria-hidden className="h-px w-3 bg-border" />}
          </li>
        );
      })}
    </ol>
  );
}
