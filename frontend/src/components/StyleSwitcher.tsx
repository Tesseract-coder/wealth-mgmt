import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { api, type Profile, type StyleKey } from "../api/client";
import { inputClass } from "./ui";

/**
 * The investing style, on every page. Changing it saves your profile, so every page (and the next
 * visit) uses it; a ?style= link on the current page shows here and is replaced by the choice.
 */
export function StyleSwitcher({ className = "" }: { className?: string }) {
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const config = useQuery({ queryKey: ["config"], queryFn: api.config });
  const profile = useQuery({ queryKey: ["profile"], queryFn: api.profile });
  const save = useMutation({
    mutationFn: (style: StyleKey) => api.saveProfile({ style, risk: profile.data!.risk }),
    onSuccess: (p: Profile) => {
      qc.setQueryData(["profile"], p);
      void qc.invalidateQueries({ predicate: (x) => !["profile", "config", "health", "meta"].includes(String(x.queryKey[0])) });
    },
  });
  if (!config.data || !profile.data?.style) return null;
  const value = (params.get("style") as StyleKey | null) ?? profile.data.style;
  return (
    <label className={`items-center gap-2 text-sm ${className}`}>
      {/* Visually hidden below 2xl so the header fits on one line; still the field's label. */}
      <span className="sr-only text-xs font-medium text-fg-muted 2xl:not-sr-only">Style</span>
      <select
        className={`${inputClass} h-9 py-1`}
        value={value}
        disabled={save.isPending}
        onChange={(e) => {
          const style = e.target.value as StyleKey;
          if (params.has("style")) {
            const p = new URLSearchParams(params);
            p.delete("style");
            setParams(p, { replace: true });
          }
          save.mutate(style);
        }}
      >
        {Object.entries(config.data.styles).map(([k, s]) => (
          <option key={k} value={k}>
            {s.label}
          </option>
        ))}
      </select>
      {save.isError && <span className="text-xs text-bad">Couldn't save</span>}
    </label>
  );
}
