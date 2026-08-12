export interface TokenBreakdown {
  input: number;
  output: number;
  cache_write: number;
  cache_read: number;
  total: number;
}

export interface RateSet {
  input: number;
  output: number;
  cache_write: number;
  cache_read: number;
}

/** One exact model id (claude-opus-5), not the family bucket. */
export interface ModelUsage {
  model: string;
  family: string;
  tokens: number;
  cost: number;
  events: number;
  tokens_detail: Omit<TokenBreakdown, "total">;
  rates: RateSet;
  /** "model" when pricing.json overrides this id, else the family rate. */
  priced_by: "model" | "family";
  token_share: number;
  cost_share: number;
  avg_cost_per_call: number;
}

export interface SummaryBlock {
  tokens: TokenBreakdown;
  cost: { total: number; by_family: Record<string, number> };
  events: number;
  by_model: ModelUsage[];
}

export interface SubscriptionInfo {
  plan: string | null;
  label: string;
  monthly_usd: number;
  source: "detected" | "manual" | "unknown";
  mode: string;
  detected_plan: string | null;
  detect_reason: string | null;
  evidence: Record<string, unknown>;
  since: string | null;
  fee_overridden: boolean;
  /** False on pay-as-you-go API billing — nothing to compare against. */
  comparable: boolean;
  catalog: { id: string; label: string; monthly_usd: number }[];
}

export interface SavingsCurrent {
  comparable: boolean;
  plan: string | null;
  plan_label: string;
  source: string;
  monthly_fee: number;
  api_cost_mtd: number;
  saved: number;
  multiple: number | null;
  breakeven_reached: boolean;
  remaining_to_breakeven: number;
  projected_api_cost: number;
  projected_saved: number;
  month_progress: { day: number; days_in_month: number; elapsed_days: number; fraction: number };
}

export interface SavingsMonth {
  month: string;
  api_cost: number;
  fee: number;
  saved: number;
  subscribed: boolean;
  partial: boolean;
  data_missing: boolean;
  cumulative_saved: number;
}

export interface SavingsTimeline {
  comparable: boolean;
  plan_label: string;
  monthly_fee: number;
  since: string | null;
  points: SavingsMonth[];
  total_api_cost: number;
  total_fees: number;
  total_saved: number;
  paid_months: number;
  months_missing_data: number;
}

export interface SavingsReport {
  subscription: SubscriptionInfo;
  current: SavingsCurrent;
  timeline: SavingsTimeline;
}

export interface ScopeInfo {
  project: string;
  name: string;
  cwds: string[];
  events: number;
  known: boolean;
}

export interface SummaryCards {
  today: SummaryBlock;
  month: SummaryBlock;
  subscription: SubscriptionInfo;
  /** Always account-wide, even when the cards are scoped to one project. */
  savings: SavingsCurrent;
  scope: ScopeInfo | null;
  last_sync_at: string | null;
}

export interface ProjectShare {
  scope: ScopeInfo | null;
  month_cost: number;
  month_tokens: number;
  events: number;
  account_month_cost: number;
  cost_share: number;
  by_model: ModelUsage[];
  comparable: boolean;
  plan_label: string;
  monthly_fee: number;
  pct_of_fee: number | null;
}

export interface TrendPoint {
  bucket: string;
  input: number;
  output: number;
  cache_write: number;
  cache_read: number;
  cost: number;
}

export interface ModelItem {
  family: string;
  tokens: number;
  events: number;
  cost: number;
  /** How many distinct model ids rolled up into this family. */
  models: number;
  token_share: number;
  cost_share: number;
}

export interface ModelsResponse {
  items: ModelItem[];
  models: ModelUsage[];
  totals: { tokens: number; cost: number; events: number; model_count: number };
}

export interface ProjectTopItem {
  path: string;
  name: string;
  tokens: number;
  cost: number;
}

export interface SparkPoint {
  day: string;
  tokens: number;
}

export interface ProjectItem extends ProjectTopItem {
  events: number;
  sessions: number;
  last_active: string;
  first_seen: string;
  tokens_detail: Omit<TokenBreakdown, "total">;
  by_model: ModelUsage[];
  cwds: string[];
  spark: SparkPoint[];
  /** Always today, regardless of the selected range. */
  today: { tokens: number; cost: number; events: number };
}

export interface ProjectDetail extends Omit<ProjectItem, "spark"> {
  month_tokens: number;
  prev_month_tokens: number;
  tokens_delta_pct: number | null;
  avg_cost_per_event: number;
}

export interface LogItem {
  ts: string;
  model: string;
  model_family: string;
  project_name: string;
  project_path: string;
  session_id: string | null;
  input: number;
  output: number;
  cache_write: number;
  cache_read: number;
  cost: number;
}

export interface LogsResponse {
  total: number;
  page: number;
  page_size: number;
  items: LogItem[];
}

export interface SyncStatus {
  syncing: boolean;
  last_sync_at: string | null;
  files_seen: number;
  files_parsed: number;
  events_total: number;
  parse_errors: number;
  missing_roots: string[];
  last_error: string | null;
}

export type RangeKey = "today" | "7d" | "30d" | "month" | "all";
