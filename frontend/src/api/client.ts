const BASE = "/api";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) throw new ApiError(res.status, await errorMessage(res));
  return (await res.json()) as T;
}

export type StyleKey = "intraday" | "swing" | "positional" | "long_term" | "custom";
export type RiskKey = "low" | "medium" | "high";

export interface Health {
  status: string;
  database: string;
  config_version: number;
  server_time_ist: string;
}

export interface Meta {
  disclaimer: string;
  timezone: string;
  currency: string;
}

export interface Profile {
  style: StyleKey | null;
  risk: RiskKey;
  custom_technical_weight: number;
  gsheet_url: string | null;
  onboarded: boolean;
  updated_at: string;
}

export interface StyleConfig {
  label: string;
  horizon: string;
  timeframes: string[];
  technical_weight: number;
  fundamental_weight: number;
  note: string | null;
}

export interface RiskConfig {
  label: string;
  max_weight_per_stock: number;
  max_weight_per_sector: number;
  stop_loss_atr_multiple: number;
  min_market_cap_cr: number;
  max_debt_to_equity: number | null;
  max_beta: number | null;
  buy_threshold: number;
}

export interface AppConfig {
  version: number;
  styles: Record<StyleKey, StyleConfig>;
  risk_levels: Record<RiskKey, RiskConfig>;
  disclaimer: string;
}

export const api = {
  health: () => request<Health>("/health"),
  meta: () => request<Meta>("/meta"),
  config: () => request<AppConfig>("/config"),
  profile: () => request<Profile>("/settings/profile"),
  saveProfile: (body: Pick<Profile, "style" | "risk"> & Partial<Profile>) =>
    request<Profile>("/settings/profile", { method: "PUT", body: JSON.stringify(body) }),
};

// --------------------------------------------------------------------------- import / portfolio

async function upload<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { method: "POST", body: form });
  if (!res.ok) throw new ApiError(res.status, await errorMessage(res));
  return (await res.json()) as T;
}

async function errorMessage(res: Response): Promise<string> {
  const text = await res.text();
  try {
    const body = JSON.parse(text) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
    if (body.detail) return JSON.stringify(body.detail);
  } catch {
    // not JSON
  }
  return text || res.statusText;
}

export type HoldingKind = "stocks" | "mf";

export interface Snapshot {
  id: number;
  kind: HoldingKind;
  source: string;
  filename: string | null;
  created_at: string;
  row_count: number;
  total_invested: number | null;
  total_value: number | null;
  note: string | null;
}

export interface Suggestion {
  symbol: string | null;
  amfi_code: string | null;
  name: string;
  score: number;
}

export interface StockHolding {
  id: number;
  snapshot_id: number;
  name: string;
  isin: string | null;
  symbol: string | null;
  exchange: "NSE" | "BSE" | null;
  resolution: string;
  resolution_score: number | null;
  suggestions: Suggestion[];
  quantity: number;
  avg_price: number;
  close_price: number | null;
  invested: number;
  current_value: number | null;
  unrealised_pnl: number | null;
  purchase_date: string | null;
}

export interface MFHolding {
  id: number;
  snapshot_id: number;
  scheme_name: string;
  amc: string | null;
  category: string | null;
  folio: string | null;
  isin: string | null;
  amfi_code: string | null;
  plan: "direct" | "regular" | null;
  option: "growth" | "idcw" | null;
  resolution: string;
  resolution_score: number | null;
  suggestions: Suggestion[];
  units: number;
  invested: number | null;
  current_value: number | null;
  nav: number | null;
  nav_date: string | null;
  first_purchase_date: string | null;
  origin: "import" | "manual";
  transaction_count: number;
}

export interface Holdings {
  stocks_snapshot: Snapshot | null;
  stocks: StockHolding[];
  mf_snapshot: Snapshot | null;
  mf: MFHolding[];
}

export interface Imported {
  status: "imported";
  snapshot: Snapshot;
  skipped: { row: number; reason: string; text: string }[];
  warnings: string[];
  unresolved: number;
}

export interface FieldSpec {
  key: string;
  label: string;
  required: boolean;
}

export interface NeedsMapping {
  status: "needs_mapping";
  kind: HoldingKind;
  header_row: number;
  headers: string[];
  detected: Record<string, number>;
  missing_required: string[];
  fields: FieldSpec[];
  preview: string[][];
}

export interface ColumnMappingIn {
  header_row: number;
  columns: Record<string, number>;
  remember: boolean;
}

export interface ManualMFIn {
  scheme: string;
  units: number;
  invested: number;
  folio?: string | null;
  purchase_date?: string | null;
}

export const importApi = {
  tabular: (kind: HoldingKind, file: File, mapping?: ColumnMappingIn) => {
    const form = new FormData();
    form.append("file", file);
    if (mapping) form.append("mapping", JSON.stringify(mapping));
    return upload<Imported | NeedsMapping>(
      kind === "stocks" ? "/import/groww-stocks" : "/import/groww-mf",
      form,
    );
  },
  cas: (file: File, password: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("password", password);
    return upload<Imported>("/import/cas", form);
  },
  manualMf: (body: ManualMFIn) =>
    request<Imported>("/import/mf-manual", { method: "POST", body: JSON.stringify(body) }),
};

export const portfolioApi = {
  holdings: () => request<Holdings>("/portfolio/holdings"),
  snapshots: () => request<Snapshot[]>("/portfolio/snapshots"),
  fixTicker: (id: number, symbol: string, exchange: "NSE" | "BSE") =>
    request<StockHolding>(`/portfolio/stocks/${id}/ticker`, {
      method: "PATCH",
      body: JSON.stringify({ symbol, exchange, remember: true }),
    }),
  fixScheme: (id: number, amfi_code: string) =>
    request<MFHolding>(`/portfolio/mf/${id}/scheme`, {
      method: "PATCH",
      body: JSON.stringify({ amfi_code, remember: true }),
    }),
  deleteMf: (id: number) => request<Imported>(`/portfolio/mf/${id}`, { method: "DELETE" }),
  searchSecurities: (q: string) =>
    request<Suggestion[]>(`/reference/securities?q=${encodeURIComponent(q)}`),
  searchSchemes: (q: string) =>
    request<Suggestion[]>(`/reference/schemes?q=${encodeURIComponent(q)}`),
};
