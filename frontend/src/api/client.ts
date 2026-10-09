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
  if (!res.ok) {
    const text = await res.text();
    throw new ApiError(res.status, text || res.statusText);
  }
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
