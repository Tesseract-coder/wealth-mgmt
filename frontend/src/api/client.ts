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
  kind: HoldingKind | "screener" | "fund_portfolio";
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
  fundPortfolio: (file: File, amfiCode: string, opts: { asOf?: string; sheet?: string; mapping?: ColumnMappingIn }) => {
    const form = new FormData();
    form.append("file", file);
    form.append("amfi_code", amfiCode);
    if (opts.asOf) form.append("as_of", opts.asOf);
    if (opts.sheet) form.append("sheet", opts.sheet);
    if (opts.mapping) form.append("mapping", JSON.stringify(opts.mapping));
    return upload<FundPortfolioImported | NeedsMapping>("/import/fund-portfolio", form);
  },
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

// ---------------------------------------------------------------- scores & signals

export type SignalKey = "strong_buy" | "buy" | "hold" | "reduce" | "sell" | "no_signal";
export type ConfidenceLevel = "high" | "medium" | "low";

export interface Reading {
  source: "technical" | "fundamental";
  key: string;
  category: string;
  direction: Direction;
  text: string;
  minor: boolean;
  weight: number;
  points: number;
  timeframes: string[];
}

export interface SubScore {
  category: string;
  score: number | null;
  weight: number;
  bullish: number;
  bearish: number;
  neutral: number;
}

export interface TimeframeScore {
  interval: string;
  score: number | null;
  coverage: number;
  weight: number;
  subscores: SubScore[];
}

export interface SideScore {
  score: number | null;
  coverage: number;
  applicable: boolean;
  subscores: SubScore[];
  timeframes: TimeframeScore[];
  notes: string[];
}

export interface Scores {
  composite: number | null;
  technical: SideScore;
  fundamental: SideScore;
  technical_weight: number;
  fundamental_weight: number;
  coverage: number;
  confidence: ConfidenceLevel | null;
  confidence_reason: string;
}

export interface Flag {
  key: string;
  severe: boolean;
  text: string;
}

export interface PriceLevels {
  interval: string;
  close: number;
  as_of: string;
  atr: number;
  multiple: number;
  trailing_stop: number;
  entry_stop: number;
  stop_breached: boolean;
  risk_per_share: number;
  targets: { label: string; price: number; pct: number }[];
  basis: string;
}

export interface Rebalance {
  action: "add" | "trim" | "exit" | "none";
  quantity: number;
  value: number | null;
  target_weight: number | null;
  text: string;
}

export interface TaxNote {
  holding_days: number | null;
  term: "short" | "long" | "mixed" | "unknown";
  long_term_from: string | null;
  text: string[];
  verify_note: string;
}

export interface Position {
  quantity: number;
  avg_price: number;
  invested: number;
  price: number | null;
  price_source: string;
  value: number | null;
  pnl: number | null;
  pnl_pct: number | null;
  lots: { quantity: number; avg_price: number; purchase_date: string | null }[];
}

export interface StockSignal {
  ticker: string;
  label: string;
  style: StyleKey;
  style_label: string;
  risk: RiskKey;
  risk_label: string;
  signal: SignalKey;
  signal_label: string;
  rule: string;
  scores: Scores;
  bullish: Reading[];
  bearish: Reading[];
  readings: Reading[];
  flags: Flag[];
  levels: PriceLevels | null;
  beta: number | null;
  beta_basis: string;
  position: Position | null;
  weight: number | null;
  max_weight: number;
  sector: string | null;
  sector_weight: number | null;
  max_sector_weight: number;
  rebalance: Rebalance;
  tax: TaxNote | null;
  price_freshness: Freshness;
  fundamental_freshness: Freshness;
  notes: string[];
  disclaimer: string;
}

export interface HoldingSignal {
  ticker: string;
  label: string;
  signal: SignalKey;
  signal_label: string;
  rule: string;
  composite: number | null;
  technical: number | null;
  fundamental: number | null;
  confidence: ConfidenceLevel | null;
  weight: number | null;
  max_weight: number;
  value: number | null;
  pnl: number | null;
  sector: string | null;
  flags: Flag[];
  top_bullish: string[];
  top_bearish: string[];
  rebalance: Rebalance;
  stop: number | null;
  stop_breached: boolean;
  price_freshness: Freshness;
}

export interface HoldingSignals {
  style: StyleKey;
  style_label: string;
  risk: RiskKey;
  risk_label: string;
  technical_weight: number;
  weight_base: "portfolio" | "stocks";
  total_value: number;
  stock_value: number;
  fund_value: number;
  sectors: { sector: string; weight: number; limit: number; over: boolean }[];
  holdings: HoldingSignal[];
  notes: string[];
  disclaimer: string;
}

export interface SignalHistoryRow {
  day: string;
  style: string;
  risk: string;
  signal: SignalKey;
  signal_label: string;
  composite: number | null;
  technical: number | null;
  fundamental: number | null;
  confidence: ConfidenceLevel | null;
}

function styleQuery(style?: StyleKey | null, risk?: RiskKey | null): string {
  const p = new URLSearchParams();
  if (style) p.set("style", style);
  if (risk) p.set("risk", risk);
  const s = p.toString();
  return s ? `?${s}` : "";
}

export const signalApi = {
  holdings: (style?: StyleKey | null, risk?: RiskKey | null) =>
    request<HoldingSignals>(`/analysis/signals/holdings${styleQuery(style, risk)}`),
  stock: (ticker: string, style?: StyleKey | null, risk?: RiskKey | null) =>
    request<StockSignal>(`/analysis/stock/${encodeURIComponent(ticker)}${styleQuery(style, risk)}`),
  history: (ticker: string) => request<SignalHistoryRow[]>(`/analysis/stock/${encodeURIComponent(ticker)}/history`),
};

// ---------------------------------------------------------------- mutual funds & portfolio

export type FundSignalKey = "continue" | "review" | "switch" | "no_signal";

export interface RiskStats {
  start: string;
  end: string;
  years: number;
  cagr: number | null;
  volatility: number;
  sharpe: number | null;
  sortino: number | null;
  max_drawdown: number;
  drawdown_peak: string;
  drawdown_trough: string;
}

export interface RollingReturns {
  years: number;
  windows: number;
  fund_avg: number;
  bench_avg: number;
  avg_excess: number;
  beat_share: number;
  worst_excess: number;
  best_excess: number;
  first_start: string;
  last_start: string;
}

export interface FundReport {
  code: string;
  name: string;
  amc: string | null;
  category: string | null;
  asset_class: "equity" | "debt" | "hybrid" | "other";
  plan: string | null;
  option: string | null;
  nav: number | null;
  nav_date: string | null;
  previous_nav: number | null;
  nav_freshness: Freshness;
  history_start: string | null;
  holding: {
    units: number;
    invested: number | null;
    value: number | null;
    pnl: number | null;
    folios: string[];
    first_purchase: string | null;
    xirr: number | null;
    xirr_basis: string;
    xirr_approximate: boolean;
  } | null;
  returns: { years: number; fund: number | null; benchmark: number | null }[];
  benchmark: { ticker: string; label: string } | null;
  risk: RiskStats | null;
  benchmark_risk: RiskStats | null;
  rolling: RollingReturns[];
  direct_twin: { code: string; name: string } | null;
  direct_gap_pp: number | null;
  direct_gap_basis: string;
  expense_ratio_pct: number | null;
  overlaps: { code: string; name: string; pct: number; common: number; approximate: boolean; note: string }[];
  segment_peers: string[];
  signal: FundSignalKey;
  signal_label: string;
  rule: string;
  reasons: { direction: Direction; text: string }[];
  notes: string[];
  unavailable: string[];
  fetch_errors: string[];
  disclaimer: string;
}

export interface MFHoldingsAnalysis {
  funds: FundReport[];
  overlap: { codes: string[]; names: string[]; pct: (number | null)[][]; approximate: boolean };
  warnings: string[];
  disclaimer: string;
}

export interface FundPortfolioImported {
  status: "imported";
  upload_id: number;
  amfi_code: string;
  scheme_name: string;
  rows: number;
  total_weight_pct: number;
  warnings: string[];
}

export interface Slice {
  key: string;
  label: string;
  value: number;
  weight: number;
}

export interface PortfolioSummary {
  as_of: string | null;
  total_value: number;
  stock_value: number;
  fund_value: number;
  invested: number | null;
  invested_note: string | null;
  pnl: number | null;
  pnl_pct: number | null;
  day_change: number | null;
  day_change_pct: number | null;
  day_change_note: string | null;
  xirr: number | null;
  xirr_coverage: number;
  xirr_basis: string;
  by_holding: Slice[];
  by_sector: Slice[];
  by_mcap: Slice[];
  by_asset_class: Slice[];
  warnings: string[];
  beta: number | null;
  beta_coverage: number;
  beta_basis: string;
  correlation_labels: string[];
  correlation: (number | null)[][];
  correlation_basis: string;
  performance_dates: string[];
  performance_portfolio: number[];
  performance_nifty: number[];
  performance_basis: string;
  snapshots: { created_at: string; kind: string; total_value: number | null }[];
  notes: string[];
  disclaimer: string;
}

export const fundApi = {
  holdings: () => request<MFHoldingsAnalysis>("/analysis/mf/holdings"),
  report: (code: string) => request<FundReport>(`/analysis/mf/${encodeURIComponent(code)}`),
  setExpenseRatio: (code: string, pct: number | null) =>
    request<FundReport>(`/analysis/mf/${encodeURIComponent(code)}/expense-ratio`, {
      method: "PUT",
      body: JSON.stringify({ expense_ratio_pct: pct }),
    }),
};

export const summaryApi = {
  get: () => request<PortfolioSummary>("/portfolio/summary"),
};
