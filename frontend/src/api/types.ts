export interface TokenBreakdown {
  input: number;
  output: number;
  cache_write: number;
  cache_read: number;
  total: number;
}

export interface SummaryBlock {
  tokens: TokenBreakdown;
  cost: { total: number; by_family: Record<string, number> };
  events: number;
}

export interface SummaryCards {
  today: SummaryBlock;
  month: SummaryBlock;
  last_sync_at: string | null;
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
  token_share: number;
  cost_share: number;
}

export interface ModelsResponse {
  items: ModelItem[];
  totals: { tokens: number; cost: number };
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
  spark: SparkPoint[];
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
