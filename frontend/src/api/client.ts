const BASE = "/api";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export const OFFLINE_MESSAGE =
  "Can't reach the backend. Is it running? Start everything with `make dev` (or `docker compose up`), then try again.";

/** fetch that turns a network failure (backend stopped, wrong port) into a clear ApiError. */
async function call(url: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init);
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ApiError(0, OFFLINE_MESSAGE);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await call(`${BASE}${path}`, {
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
  technical?: { thresholds: { rsi_overbought: number; rsi_oversold: number } };
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
  const res = await call(`${BASE}${path}`, { method: "POST", body: form });
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
  // The dev proxy answers 502/503/504 (or 500 with an empty or HTML body) when the backend is down.
  if ([502, 503, 504].includes(res.status) || (res.status >= 500 && (!text || text.trimStart().startsWith("<")))) {
    return res.status === 500 && !text ? OFFLINE_MESSAGE : `The backend didn't answer properly (HTTP ${res.status}). ${OFFLINE_MESSAGE}`;
  }
  return text || res.statusText || `HTTP ${res.status}`;
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

export interface Cleared {
  kind: HoldingKind;
  snapshots: number;
  holdings: number;
}

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
  /** Remove all imported stocks or funds and their snapshot history (ticker/scheme fixes stay). */
  clear: (kind: HoldingKind) => request<Cleared>(`/portfolio/${kind}`, { method: "DELETE" }),
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

export type JobStatus = "queued" | "running" | "done" | "failed" | "cancelled";

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

export interface ScheduledJob {
  id: string;
  name: string;
  next_run: string | null;
}

export interface Schedule {
  enabled: boolean;
  prices: string;
  navs: string;
  fundamentals: string;
  jobs: ScheduledJob[];
  sheets_auto_export: boolean;
  note: string;
}

export interface MarketStatus {
  generated_at: string;
  summary: Record<FreshnessStatus, number>;
  references: ReferenceStatus[];
  quotes: Quote[];
  schedule: Schedule;
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
  cancel: (id: number) => request<Job>(`/jobs/${id}/cancel`, { method: "POST" }),
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

export interface BacktestPoint {
  date: string;
  close: number;
  score: number | null;
  signal: SignalKey;
  in_market: boolean;
  strategy: number;
  buy_hold: number;
}

export interface BacktestStats {
  group: "buy" | "hold" | "exit" | "no_signal" | "all";
  label: string;
  count: number;
  measured: number;
  hit_rate: number | null;
  rise_rate: number | null;
  avg_forward_return: number | null;
}

export interface BacktestPerformance {
  total_return: number;
  max_drawdown: number;
  exposure: number;
}

export interface Backtest {
  ticker: string;
  label: string;
  style: StyleKey;
  style_label: string;
  risk: RiskKey;
  risk_label: string;
  status: "ok" | "insufficient_data";
  message: string;
  start: string | null;
  end: string | null;
  sessions: number;
  evaluations: number;
  step_sessions: number;
  horizon_sessions: number;
  timeframes: string[];
  stats: BacktestStats[];
  strategy: BacktestPerformance | null;
  buy_hold: BacktestPerformance | null;
  trades: number;
  points: BacktestPoint[];
  notes: string[];
  caveat: string;
}

/** The portfolio report (HTML; print it to PDF from the browser). */
export const REPORT_URL = `${BASE}/export/report`;

export const analysisApi = {
  backtest: (ticker: string, style?: StyleKey | null) =>
    request<Backtest>(`/analysis/backtest/${encodeURIComponent(ticker)}${style ? `?style=${style}` : ""}`),
  technical: (ticker: string, style?: StyleKey | null) =>
    request<TechnicalReport>(
      `/analysis/technical/${encodeURIComponent(ticker)}${style ? `?style=${style}` : ""}`,
    ),
  holdings: (style?: StyleKey | null) =>
    request<TechnicalSummary[]>(`/analysis/technical/holdings${style ? `?style=${style}` : ""}`),
};

// --------------------------------------------------------------------------- chart patterns

export type PatternInterval = "15m" | "1h" | "1d" | "1wk" | "1mo";
export type Suitability = "good" | "ok" | "poor";

/** One entry of the pattern guide: what the pattern means and how it's traded. */
export interface PatternInfo {
  key: string;
  family: string;
  family_label: string;
  name: string;
  kind: "reversal" | "continuation" | "either";
  bias: Direction;
  action: "buy" | "sell" | "wait";
  verdict: string;
  meaning: string;
  trade: string;
  confirm: string;
  fails: string;
  target_rule: string;
  reliability: "high" | "medium" | "low";
  duration: string;
  intraday: Suitability;
  swing: Suitability;
  positional: Suitability;
}

export interface PatternPoint {
  t: string;
  price: number;
  label: string;
}

export interface PatternLine {
  label: string;
  kind: "neckline" | "trend" | "rim" | "curve";
  points: PatternPoint[];
}

export interface PatternMatch {
  key: string;
  name: string;
  family: string;
  direction: Direction;
  status: "forming" | "confirmed";
  confidence: number;
  strength: "strong" | "moderate" | "weak";
  start: string;
  end: string;
  bars: number;
  breakout: number | null;
  target: number | null;
  invalidation: number | null;
  target_pct: number | null;
  invalidation_pct: number | null;
  bars_since_breakout: number | null;
  volume_confirmed: boolean | null;
  text: string;
  points: PatternPoint[];
  lines: PatternLine[];
}

export interface PatternReport {
  ticker: string;
  interval: PatternInterval;
  unit: string;
  bars: number;
  as_of: string | null;
  last_close: number | null;
  patterns: PatternMatch[];
  window: { t: string[]; open: number[]; high: number[]; low: number[]; close: number[] };
  notes: string[];
}

export interface PatternHolding {
  ticker: string;
  label: string;
  interval: PatternInterval;
  as_of: string | null;
  bars: number;
  patterns: PatternMatch[];
}

export const patternApi = {
  library: () => request<PatternInfo[]>("/analysis/patterns/library"),
  stock: (ticker: string, interval: PatternInterval = "1d") =>
    request<PatternReport>(`/analysis/technical/${encodeURIComponent(ticker)}/patterns?interval=${interval}`),
  holdings: (style?: StyleKey | null) =>
    request<PatternHolding[]>(`/analysis/patterns/holdings${style ? `?style=${style}` : ""}`),
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

/** The expected yearly growth behind the PEG: yours when entered, else the analyst consensus. */
export interface GrowthGuidance {
  ticker: string;
  growth_pct: number | null;
  analyst_pct: number | null;
  analyst_basis: string;
}

export const fundamentalApi = {
  report: (ticker: string) => request<FundamentalReport>(`/analysis/fundamental/${encodeURIComponent(ticker)}`),
  holdings: () => request<FundamentalSummary[]>("/analysis/fundamental/holdings"),
  guidance: (ticker: string) => request<GrowthGuidance>(`/analysis/growth-guidance/${encodeURIComponent(ticker)}`),
  saveGuidance: (ticker: string, growth_pct: number | null) =>
    request<GrowthGuidance>(`/analysis/growth-guidance/${encodeURIComponent(ticker)}`, { method: "PUT", body: JSON.stringify({ growth_pct }) }),
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
  targets: Target[];
  basis: string;
}

export interface Target {
  label: string;
  price: number;
  pct: number;
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
  quantity: number | null;
  avg_price: number | null;
  price: number | null;
  invested: number | null;
  value: number | null;
  pnl: number | null;
  pnl_pct: number | null;
  /** ₹ since the previous close. */
  day_change: number | null;
  day_change_pct: number | null;
  peg: number | null;
  peg_basis: string | null;
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
  /** false for groups that aren't a sector (funds, ETFs): no sector limit */
  limited?: boolean;
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

// --------------------------------------------------------------------------- charts & dashboard

export type ChartInterval = "1d" | "1wk" | "1mo";

export interface Bar {
  t: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
  adj_close?: number | null;
  volume: number | null;
}

export interface PriceSeries {
  ticker: string;
  interval: string;
  source: string;
  delayed: boolean;
  last_complete: boolean;
  freshness: Freshness;
  fetch_error: string | null;
  bars: Bar[];
}

export interface IndicatorSeries {
  ticker: string;
  interval: string;
  t: string[];
  columns: Record<string, (number | null)[]>;
}

export interface FundChart {
  code: string;
  benchmark: { ticker: string; label: string } | null;
  dates: string[];
  fund: number[];
  bench: (number | null)[];
  rolling: { years: number; starts: string[]; fund: number[]; benchmark: number[] }[];
  notes: string[];
}

export type Severity = "high" | "medium" | "low";

export interface ActionItem {
  severity: Severity;
  kind: "stock" | "fund" | "portfolio" | "data";
  subject: string;
  title: string;
  detail: string;
  link: string | null;
}

export interface Actions {
  style_label: string;
  risk_label: string;
  actions: ActionItem[];
  disclaimer: string;
}

export interface Threshold {
  path: string;
  group: string;
  label: string;
  unit: "fraction" | "score" | "x" | "cr" | "ratio";
  nullable: boolean;
  value: number | null;
  default: number | null;
  edited: boolean;
}

export interface Thresholds {
  items: Threshold[];
  override_file: string;
  edited: number;
  note: string;
}

export const chartApi = {
  prices: (ticker: string, interval: ChartInterval, start?: string) =>
    request<PriceSeries>(
      `/market/prices/${encodeURIComponent(ticker)}?interval=${interval}${start ? `&start=${start}` : ""}`,
    ),
  indicators: (ticker: string, interval: ChartInterval, start?: string) =>
    request<IndicatorSeries>(
      `/analysis/technical/${encodeURIComponent(ticker)}/series?interval=${interval}${start ? `&start=${start}` : ""}`,
    ),
  fund: (code: string, years = 5) => request<FundChart>(`/analysis/mf/${encodeURIComponent(code)}/chart?years=${years}`),
};

export const dashboardApi = {
  actions: () => request<Actions>("/portfolio/actions"),
  thresholds: () => request<Thresholds>("/settings/thresholds"),
  saveThresholds: (values: Record<string, number | null>) =>
    request<Thresholds>("/settings/thresholds", { method: "PUT", body: JSON.stringify({ values }) }),
  resetThresholds: () => request<Thresholds>("/settings/thresholds", { method: "DELETE" }),
};

/** Plain links: the browser downloads the file. */
/** Export URLs without the extension: add `.csv` or `.pdf` (see DownloadMenu). */
export const EXPORTS = [
  { href: `${BASE}/export/stocks`, label: "Stock signals" },
  { href: `${BASE}/export/funds`, label: "Fund signals" },
] as const;

// ---------------------------------------------------------------- screener & watchlist

export type FilterOp = "gt" | "gte" | "lt" | "lte" | "between";
export type UniverseKey = "nifty50" | "nifty100" | "nifty200" | "nifty500" | "custom";

export interface ScreenFilter {
  field: string;
  op: FilterOp;
  value: number | [number, number];
}

export interface ScreenField {
  key: string;
  label: string;
  group: "Technical" | "Fundamental" | "Score";
  unit: string;
  help: string;
  financial_exempt: boolean;
}

export interface Preset {
  key: string;
  label: string;
  description: string;
  filters: ScreenFilter[];
}

export interface SavedScreen {
  id: number;
  name: string;
  filters: ScreenFilter[];
  updated_at: string;
}

export interface Scan {
  id: number;
  job_id: number | null;
  universe: string;
  universe_label: string;
  style: StyleKey;
  style_label: string;
  risk: RiskKey;
  risk_label: string;
  fetch: "missing" | "cached";
  status: "running" | "complete" | "partial" | "failed";
  created_at: string;
  finished_at: string | null;
  total: number;
  scored: number;
  notes: string[];
}

export interface ScreenerConfig {
  universes: { key: UniverseKey; label: string; size: number | null }[];
  default_universe: UniverseKey;
  custom_universe_max: number;
  seconds_per_stock: number;
  presets: Preset[];
  fields: ScreenField[];
  ops: Record<FilterOp, string>;
  screens: SavedScreen[];
  top_n: number;
  latest_scan: Scan | null;
  disclaimer: string;
}

export interface ScanRequest {
  universe: UniverseKey;
  symbols?: string;
  fetch: "missing" | "cached";
}

export interface ScreenerJob {
  job: Job;
  scan: Scan | null;
}

export interface ScreenRequest {
  scan_id?: number;
  preset?: string;
  screen_id?: number;
  filters?: ScreenFilter[];
  include_held?: boolean;
}

export interface EntryLevels {
  interval: string;
  close: number;
  atr: number;
  entry_low: number;
  entry_high: number;
  entry_basis: string;
  stop: number;
  stop_pct: number;
  targets: Target[];
  basis: string;
}

export interface SectorImpact {
  sector: string | null;
  amount: number | null;
  quantity: number | null;
  before: number | null;
  after: number | null;
  over_limit: boolean;
  text: string;
}

export interface Candidate {
  rank: number;
  ticker: string;
  symbol: string;
  label: string;
  sector: string | null;
  held: boolean;
  watched: boolean;
  signal: SignalKey;
  signal_label: string;
  rule: string;
  confidence: ConfidenceLevel | null;
  composite: number | null;
  technical: number | null;
  fundamental: number | null;
  bullish: string[];
  bearish: string[];
  flags: Flag[];
  passed: string[];
  levels: EntryLevels | null;
  impact: SectorImpact;
  facts: Record<string, number | null>;
  price_as_of: string | null;
}

export interface ScreenResult {
  scan: Scan;
  title: string;
  filters: string[];
  prefilters: string[];
  counts: Record<"universe" | "not_scored" | "held" | "prefilter" | "signal" | "filters" | "missing_data" | "passed", number>;
  candidates: Candidate[];
  near_misses: { ticker: string; label: string; composite: number | null; failed: string[] }[];
  stale_note: string | null;
  disclaimer: string;
}

export interface WatchItem {
  ticker: string;
  label: string;
  note: string | null;
  source: string | null;
  added_at: string;
  added_price: number | null;
  added_signal: SignalKey | null;
  added_signal_label: string | null;
  added_score: number | null;
  held: boolean;
  status: "ok" | "no_data";
  signal: SignalKey | null;
  signal_label: string | null;
  rule: string | null;
  confidence: ConfidenceLevel | null;
  composite: number | null;
  score_change: number | null;
  price: number | null;
  price_as_of: string | null;
  price_change_pct: number | null;
  signal_changed_since_added: boolean;
  last_change: { previous: SignalKey; previous_label: string; current: SignalKey; current_label: string; day: string } | null;
  stop: number | null;
  stop_breached: boolean;
  bullish: string[];
  bearish: string[];
  flags: Flag[];
  sector: string | null;
  price_freshness: Freshness | null;
  /** Score Shape; null until the stock has prices. */
  axes?: Record<string, number | null> | null;
  shape_total?: number | null;
  shape_max?: number | null;
  shape_step?: number | null;
  week_change?: WeekChange | null;
}

export interface Watchlist {
  style_label: string;
  risk_label: string;
  items: WatchItem[];
  fetching_job_id: number | null;
  disclaimer: string;
}

export const screenerApi = {
  config: () => request<ScreenerConfig>("/screener/config"),
  run: (body: ScanRequest) => request<ScreenerJob>("/screener/run", { method: "POST", body: JSON.stringify(body) }),
  job: (id: number) => request<ScreenerJob>(`/screener/jobs/${id}`),
  active: () => request<ScreenerJob | null>("/screener/active"),
  screen: (body: ScreenRequest) => request<ScreenResult>("/screener/screen", { method: "POST", body: JSON.stringify(body) }),
  saveScreen: (name: string, filters: ScreenFilter[], id?: number) =>
    request<SavedScreen>(id ? `/screener/screens/${id}` : "/screener/screens", {
      method: id ? "PUT" : "POST",
      body: JSON.stringify({ name, filters }),
    }),
  deleteScreen: async (id: number) => {
    const res = await call(`${BASE}/screener/screens/${id}`, { method: "DELETE" });
    if (!res.ok) throw new ApiError(res.status, await errorMessage(res));
  },
  /** The screen's export URL without the extension (DownloadMenu adds `.csv` or `.pdf`). */
  exportHref: (sel: { preset?: string; screen_id?: number; include_held?: boolean }) => {
    const p = new URLSearchParams();
    if (sel.preset) p.set("preset", sel.preset);
    if (sel.screen_id) p.set("screen_id", String(sel.screen_id));
    if (sel.include_held) p.set("include_held", "true");
    return `${BASE}/export/screener?${p.toString()}`;
  },
};

export const watchlistApi = {
  list: () => request<Watchlist>("/watchlist"),
  tickers: () => request<string[]>("/watchlist/tickers"),
  add: (ticker: string, source?: string, note?: string) =>
    request<WatchItem>("/watchlist", { method: "POST", body: JSON.stringify({ ticker, source, note }) }),
  note: (ticker: string, note: string) =>
    request<WatchItem>(`/watchlist/${encodeURIComponent(ticker)}`, { method: "PATCH", body: JSON.stringify({ note }) }),
  remove: async (ticker: string) => {
    const res = await call(`${BASE}/watchlist/${encodeURIComponent(ticker)}`, { method: "DELETE" });
    if (!res.ok) throw new ApiError(res.status, await errorMessage(res));
  },
};

// ---------------------------------------------------------------------------- Google Sheets

export interface ServiceAccount {
  configured: boolean;
  path: string;
  client_email: string | null;
  project_id: string | null;
  error: string | null;
}

export interface SheetSync {
  at: string;
  direction: "export" | "import" | "test";
  detail: string | null;
  ok: boolean;
  message: string;
}

export interface SheetSettings {
  stocks_tab: string;
  mf_tab: string;
  stocks_csv_url: string | null;
  mf_csv_url: string | null;
  screener_screen: string | null;
  auto_export: boolean;
}

export interface SheetsStatus {
  service_account: ServiceAccount;
  sheet_url: string | null;
  spreadsheet_url: string | null;
  link_error: string | null;
  settings: SheetSettings;
  export_tabs: Record<"stocks" | "mf" | "screener" | "summary", string>;
  default_import_tabs: Record<HoldingKind, string>;
  history: SheetSync[];
  refresh_time_ist: string;
}

export type SheetSettingsIn = Partial<Omit<SheetSettings, "auto_export">> & { sheet_url?: string | null; auto_export: boolean };

export interface SheetCheck {
  name: string;
  ok: boolean | null;
  detail: string;
}

export interface SheetExport {
  url: string;
  title: string;
  tabs: { name: string; rows: number }[];
  at: string;
}

export interface SheetImportIn {
  kind: HoldingKind;
  source: "tab" | "csv";
  tab?: string;
  url?: string;
  mapping?: ColumnMappingIn;
}

/** Export refused: these tabs hold content the app didn't write. Resend with `overwrite`. */
export class ForeignTabsError extends ApiError {
  constructor(
    message: string,
    public tabs: string[],
  ) {
    super(409, message);
  }
}

export const sheetsApi = {
  status: () => request<SheetsStatus>("/sheets/status"),
  save: (body: SheetSettingsIn) => request<SheetsStatus>("/sheets/settings", { method: "PUT", body: JSON.stringify(body) }),
  uploadKey: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return upload<ServiceAccount>("/sheets/service-account", form);
  },
  test: () => request<{ ok: boolean; checks: SheetCheck[] }>("/sheets/test", { method: "POST" }),
  export: async (overwrite: string[] = []) => {
    const res = await call(`${BASE}/sheets/export`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ overwrite }),
    });
    if (res.status === 409) {
      const body = (await res.json()) as { detail: { message: string; tabs: string[] } };
      throw new ForeignTabsError(body.detail.message, body.detail.tabs);
    }
    if (!res.ok) throw new ApiError(res.status, await errorMessage(res));
    return (await res.json()) as SheetExport;
  },
  import: (body: SheetImportIn) =>
    request<Imported | NeedsMapping>("/sheets/import", { method: "POST", body: JSON.stringify(body) }),
};

// ---------------------------------------------------------------------------- Score Shape

export type CheckStatus = "pass" | "fail" | "no_data";

export interface CheckResult {
  section: string;
  check_id: string;
  label: string;
  status: CheckStatus;
  value: number | null;
  threshold: number | null;
  unit: string;
  display_value: string;
  display_threshold: string;
  /** One plain-English sentence: what the result means. */
  explanation: string;
  /** What the metric is, in one sentence (for a tooltip). */
  help: string | null;
  highlight: ("reward" | "risk")[];
}

export interface SectionResult {
  key: string;
  label: string;
  question: string;
  caption: string | null;
  checks: CheckResult[];
  passed: number;
  with_data: number;
  /** 0 … axis_max; null = not enough data */
  score: number | null;
  note: string | null;
}

export interface Shape {
  sections: SectionResult[];
  axes: Record<string, number | null>;
  total: number;
  max_total: number;
  axis_max: number;
  /** Colour step 1 (weak) … 5 (strong) */
  step: number | null;
  checks_total: number;
  checks_with_data: number;
  confidence: ConfidenceLevel;
  confidence_reason: string;
  rewards: string[];
  risks: string[];
  summary: string;
}

export interface FairValue {
  label: "Estimate";
  value: number;
  price: number;
  /** Price vs fair value: negative = below (cheaper) */
  gap_pct: number;
  methods: { name: string; value: number; basis: string }[];
  caveat: string;
}

export interface WeekChange {
  since: string;
  axes: Record<string, number | null>;
  total: number;
  previous_signal: SignalKey | null;
  previous_signal_label: string | null;
  signal_changed: boolean;
}

export interface StockChecks extends Shape {
  ticker: string;
  label: string;
  sector: string | null;
  is_financial: boolean;
  style: StyleKey;
  style_label: string;
  risk: RiskKey;
  risk_label: string;
  signal: SignalKey;
  signal_label: string;
  fair_value: FairValue | null;
  pe_history: { fy: string; year_end: string; price: number; pe: number }[];
  week_change: WeekChange | null;
  disclaimer: string;
}

export interface HoldingShape {
  ticker: string;
  label: string;
  sector: string | null;
  value: number | null;
  weight: number | null;
  signal: SignalKey;
  signal_label: string;
  axes: Record<string, number | null>;
  total: number;
  max_total: number;
  step: number | null;
  confidence: ConfidenceLevel;
  /** "Strongest: …" / "Weakest: …" */
  top: string[];
}

export interface PortfolioShape {
  axes: { key: string; label: string; score: number | null; coverage: number }[];
  total: number;
  max_total: number;
  axis_max: number;
  step: number | null;
  stock_value: number;
  holdings: number;
}

export interface HoldingsChecks {
  style: StyleKey;
  style_label: string;
  risk: RiskKey;
  risk_label: string;
  portfolio: PortfolioShape;
  holdings: HoldingShape[];
  rewards: string[];
  risks: string[];
  notes: string[];
  disclaimer: string;
}

export interface FundChecks extends Shape {
  code: string;
  name: string;
  category: string | null;
  signal: FundSignalKey;
  signal_label: string;
  disclaimer: string;
}

export interface AxisDef {
  key: string;
  label: string;
  question: string;
  caption: string | null;
}

export interface ChecksConfig {
  axis_max: number;
  score_steps: number[];
  stock: AxisDef[];
  fund: AxisDef[];
}

export interface FinancialYear {
  fy: string;
  year_end: string;
  revenue: number | null;
  net_income: number | null;
  op_margin: number | null;
  net_margin: number | null;
  roe: number | null;
  total_debt: number | null;
  equity: number | null;
  cash: number | null;
  debt_equity: number | null;
  fcf: number | null;
  dividends_paid: number | null;
  payout_pct: number | null;
  pe: number | null;
  price: number | null;
}

export interface FinancialHistory {
  ticker: string;
  label: string;
  sector: string | null;
  is_financial: boolean;
  source: string | null;
  /** "₹ Cr", or e.g. "USD Cr" */
  unit: string;
  years: FinancialYear[];
  quarters: { label: string; period_end: string; revenue: number | null; net_income: number | null }[];
  fair_value: FairValue | null;
  notes: string[];
  disclaimer: string;
}

export const checksApi = {
  config: () => request<ChecksConfig>("/analysis/checks/config"),
  stock: (ticker: string, style?: StyleKey | null, risk?: RiskKey | null) =>
    request<StockChecks>(`/analysis/stock/${encodeURIComponent(ticker)}/checks${styleQuery(style, risk)}`),
  holdings: (style?: StyleKey | null, risk?: RiskKey | null) =>
    request<HoldingsChecks>(`/analysis/checks/holdings${styleQuery(style, risk)}`),
  history: (ticker: string) =>
    request<FinancialHistory>(`/analysis/fundamental/${encodeURIComponent(ticker)}/history`),
  fund: (code: string) => request<FundChecks>(`/analysis/mf/${encodeURIComponent(code)}/checks`),
  funds: () => request<{ funds: FundChecks[]; disclaimer: string }>("/analysis/mf/holdings/checks"),
};
