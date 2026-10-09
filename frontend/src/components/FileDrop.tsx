import { useId, useRef, useState } from "react";

interface Props {
  accept: string;
  hint: string;
  file: File | null;
  onFile: (file: File) => void;
  disabled?: boolean;
}

export function FileDrop({ accept, hint, file, onFile, disabled }: Props) {
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const id = useId();
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
      className={`flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-6 text-center text-sm ${
        over ? "border-slate-900 bg-slate-100 dark:border-slate-100 dark:bg-slate-800" : "border-slate-300 dark:border-slate-700"
      }`}
    >
      <label htmlFor={id} className="cursor-pointer font-medium underline">
        {file ? file.name : "Choose a file"}
      </label>
      <span className="text-slate-500">or drag and drop it here · {hint}</span>
      <input
        id={id}
        ref={input}
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
    </div>
  );
}
