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
  kind: HoldingKind | "screener";
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

export interface ScreenerImported {
  status: "imported";
  kind: "screen" | "company";
  upload_id: number;
  matched: { symbol: string; name: string }[];
  unmatched: string[];
  warnings: string[];
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
  screener: (file: File, mapping?: ColumnMappingIn, symbol?: string) => {
    const form = new FormData();
    form.append("file", file);
    if (mapping) form.append("mapping", JSON.stringify(mapping));
    if (symbol) form.append("symbol", symbol);
    return upload<ScreenerImported | NeedsMapping>("/import/screener", form);
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

// --------------------------------------------------------------------------- market data

export type FreshnessStatus = "fresh" | "stale" | "unavailable";

export interface Freshness {
  status: FreshnessStatus;
  reason: string;
}

export interface ReferenceStatus {
  key: string;
  label: string;
  source: string;
  origin: "refreshed" | "bundled";
  as_of: string | null;
  rows: number | null;
  freshness: Freshness;
}

export interface Quote {
  kind: "stock" | "benchmark" | "mf";
  code: string;
  label: string;
  price: number | null;
  previous: number | null;
  change_pct: number | null;
  as_of: string | null;
  source: string | null;
  freshness: Freshness;
}

export type JobStatus = "queued" | "running" | "done" | "failed";

export interface Job {
  id: number;
  kind: string;
  status: JobStatus;
  trigger: string;
  params: Record<string, unknown>;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  done: number;
  total: number;
  message: string | null;
  errors: string[];
}

export interface MarketStatus {
  generated_at: string;
  summary: Record<FreshnessStatus, number>;
  references: ReferenceStatus[];
  quotes: Quote[];
  schedule: { enabled: boolean; prices: string; navs: string; fundamentals: string };
  last_job: Job | null;
  last_fundamentals_job: Job | null;
  notes: string[];
}

export type RefreshScope = "all" | "reference" | "prices" | "navs" | "fundamentals";

export const marketApi = {
  status: () => request<MarketStatus>("/market/status"),
  refresh: (scope: RefreshScope = "all", force = false) =>
    request<Job>("/market/refresh", { method: "POST", body: JSON.stringify({ scope, force }) }),
  job: (id: number) => request<Job>(`/jobs/${id}`),
};

export const isActive = (job: Job | null | undefined): boolean =>
  job?.status === "queued" || job?.status === "running";

// --------------------------------------------------------------------------- technical analysis

export type Direction = "bullish" | "bearish" | "neutral";

export interface Observation {
  key: string;
  category: string;
  direction: Direction;
  text: string;
  value: number | null;
  minor: boolean;
}

export interface FrameAnalysis {
  values: Record<string, number | null>;
  observations: Observation[];
  unavailable: string[];
  levels: { price: number; touches: number; kind: "support" | "resistance" }[];
}

export interface TimeframeReport {
  interval: string;
  bars: number;
  as_of: string | null;
  last_close: number | null;
  last_complete: boolean;
  freshness: Freshness;
  analysis: FrameAnalysis;
  notes: string[];
}

export interface TechnicalReport {
  ticker: string;
  label: string;
  style: StyleKey | null;
  timeframes: TimeframeReport[];
  context: FrameAnalysis;
  fetch_errors: string[];
  notes: string[];
  disclaimer: string;
}

export interface TechnicalSummary {
  ticker: string;
  label: string;
  interval: string;
  as_of: string | null;
  freshness: Freshness;
  bullish: number;
  bearish: number;
  neutral: number;
  top_bullish: string[];
  top_bearish: string[];
}

export const analysisApi = {
  technical: (ticker: string, style?: StyleKey | null) =>
    request<TechnicalReport>(
      `/analysis/technical/${encodeURIComponent(ticker)}${style ? `?style=${style}` : ""}`,
    ),
  holdings: (style?: StyleKey | null) =>
    request<TechnicalSummary[]>(`/analysis/technical/holdings${style ? `?style=${style}` : ""}`),
};

// --------------------------------------------------------------------------- fundamentals

export interface Metric {
  key: string;
  label: string;
  value: number | null;
  unit: string;
  basis: string;
  sector_median: number | null;
  peers: number;
}

export interface FundamentalReport {
  ticker: string;
  label: string;
  sector: string | null;
  is_financial: boolean;
  source: "yahoo" | "screener" | null;
  latest_year: string | null;
  freshness: Freshness;
  metrics: Metric[];
  fscore: { score: number | null; computable: number; tests: { name: string; passed: boolean | null; detail: string }[] } | null;
  observations: Observation[];
  unavailable: string[];
  notes: string[];
  fetch_errors: string[];
  disclaimer: string;
}

export interface FundamentalSummary {
  ticker: string;
  label: string;
  sector: string | null;
  source: string | null;
  freshness: Freshness;
  pe: number | null;
  roe: number | null;
  debt_equity: number | null;
  fscore: number | null;
  bullish: number;
  bearish: number;
  top_bullish: string[];
  top_bearish: string[];
}

export const fundamentalApi = {
  report: (ticker: string) => request<FundamentalReport>(`/analysis/fundamental/${encodeURIComponent(ticker)}`),
  holdings: () => request<FundamentalSummary[]>("/analysis/fundamental/holdings"),
};
