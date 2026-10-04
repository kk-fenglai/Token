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

/** Cache hit rate over prompt tokens, what caching saved at the input rate,
 *  and cost per 1K output tokens — the F8 figures. */
export interface Efficiency {
  cache_hit_rate: number | null;
  cache_saved: number;
  cost_per_1k_output: number | null;
  prompt_tokens: number;
}

export interface SummaryBlock {
  tokens: TokenBreakdown;
  cost: { total: number; by_family: Record<string, number> };
  events: number;
  by_model: ModelUsage[];
  efficiency: Efficiency;
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

export interface BillingMonth extends SavingsMonth {
  tokens: number;
  events: number;
}

export interface MonthlyBilling {
  subscription: SubscriptionInfo;
  current: SavingsCurrent;
  timeline: Omit<SavingsTimeline, "points"> & {
    points: BillingMonth[];
    /** Subscribed months only, same window as total_api_cost. */
    total_tokens: number;
    total_events: number;
  };
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
  efficiency: Efficiency;
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

// ---- v1.2: sessions, tools, heatmap, alerts, weekly report ----

export interface SessionItem {
  session_id: string;
  project_path: string;
  /** Folded project key (links to /projects/detail). */
  project: string;
  name: string;
  first_ts: string;
  last_ts: string;
  /** Local date of first_ts, YYYY-MM-DD. */
  day: string;
  duration_s: number;
  messages: number;
  tokens: Omit<TokenBreakdown, "total">;
  tokens_total: number;
  cost: number;
  models: string[];
  tool_calls: number;
  subagent_events: number;
  subagent_cost: number;
  /** Largest prompt (input + cache write + cache read) of any turn. */
  ctx_max: number;
}

export interface SessionsResponse {
  total: number;
  page: number;
  page_size: number;
  items: SessionItem[];
  totals: { sessions: number; cost: number; messages: number; tokens: number };
}

export interface SessionMessage {
  i: number;
  ts: string;
  model: string;
  input: number;
  output: number;
  cache_write: number;
  cache_read: number;
  context: number;
  cost: number;
  cumulative_cost: number;
  tools: string[];
  sidechain: boolean;
  agent: string | null;
}

export interface ToolItem {
  name: string;
  calls: number;
  messages: number;
  output_tokens: number;
  cost: number;
  cost_share: number;
}

export interface ToolsBreakdown {
  range?: string;
  tools: ToolItem[];
  text_only: { messages: number; cost: number; output_tokens: number };
  subagents: {
    events: number; cost: number; tokens: number; cost_share: number;
    by_agent: { agent: string; events: number; cost: number }[];
  };
  totals: { cost: number; events: number; tool_calls: number };
}

export interface SessionDetailResponse {
  session: SessionItem;
  messages: SessionMessage[];
  tools: ToolsBreakdown;
  peak_context: { i: number; context: number; ts: string } | null;
  truncated: boolean;
}

export interface HeatCell { dow: number; hour: number; tokens: number; cost: number; events: number }

export interface Heatmap {
  range: string;
  cells: HeatCell[];
  max_tokens: number;
  max_cost: number;
  by_hour: number[];
  by_dow: number[];
  peak: { dow: number; hour: number; cost: number } | null;
  total_cost: number;
}

export interface AlertItem {
  kind: string;
  level: "info" | "warn" | "danger";
  params: Record<string, string | number>;
}

export interface AlertsResponse {
  generated_at: string;
  items: AlertItem[];
  today_cost: number;
  scope: ScopeInfo | null;
}

export interface WeeklyReport {
  week: { from: string; to: string; weeks_ago: number; is_current: boolean; generated_at: string };
  scope: ScopeInfo | null;
  totals: { cost: number; tokens: TokenBreakdown; events: number; sessions: number; efficiency: Efficiency | null };
  previous: { cost: number; tokens: number; events: number; sessions: number };
  delta_pct: { cost: number | null; tokens: number | null; events: number | null; sessions: number | null };
  days: { day: string; cost: number }[];
  busiest_day: { day: string; cost: number } | null;
  top_projects: { path: string; name: string; tokens: number; cost: number; events: number }[];
  top_models: ModelUsage[];
  top_sessions: SessionItem[];
  tools: ToolItem[];
  subagents: ToolsBreakdown["subagents"];
  peak_slot: { dow: number; hour: number; cost: number } | null;
  savings: SavingsCurrent | null;
  markdown: string;
}

export interface PricingStatus {
  last_verified: string | null;
  age_days: number | null;
  stale: boolean;
  stale_after_days: number;
  unit: string | null;
}

export interface RetentionInfo {
  cleanup_days: number;
  configured: boolean;
  settings_path: string;
  last_sync_at: string | null;
  days_since_sync: number | null;
  recommended_days: number;
  pricing: PricingStatus;
}

// ---- v1.3 F26: dev projects tracker ----

export type DevProjectLevel = "ok" | "info" | "warn" | "danger";

export interface DevProjectItem {
  path: string;
  name: string;
  sources: ("sessions" | "workspace" | "manual")[];
  pinned: boolean;
  is_repo: boolean;
  error: string | null;
  branch: string | null;
  detached: boolean;
  remote_url: string | null;
  is_github: boolean;
  github_url: string | null;
  has_upstream: boolean;
  ahead: number;
  behind: number;
  modified: number;
  untracked: number;
  staged: number;
  changes: number;
  oldest_unpushed_at: string | null;
  unpushed_age_hours: number | null;
  last_commit_at: string | null;
  newest_change_at: string | null;
  dirty_age_hours: number | null;
  last_active: string | null;
  level: DevProjectLevel;
  reasons: string[];
  /** F28 user notes; absent on responses that bypass the list route. */
  meta?: DevProjectMeta;
}

export interface DevProjectsSummary {
  tracked: number;
  needs_push: number;
  dirty: number;
  no_remote: number;
  ok: number;
}

export interface DevProjectsConfig {
  extra: string[];
  ignored: string[];
  pinned: string[];
  active_days: number;
  unpushed_danger_hours: number;
  dirty_warn_hours: number;
  desktop_notify: boolean;
}

export interface DevProjectsResponse {
  items: DevProjectItem[];
  summary: DevProjectsSummary;
  checked_at: string;
  git_available: boolean;
  config: DevProjectsConfig;
  notify: { last_run: string | null; last_sent: string | null; last_error: string | null };
}

export type PublishAction = "push" | "push_upstream" | "create_repo" | "nothing" | "blocked";
export interface PublishPlan {
  path: string;
  name: string;
  branch: string | null;
  detached: boolean;
  remote: string | null;
  remote_url: string | null;
  is_github: boolean;
  github_url: string | null;
  has_upstream: boolean;
  ahead: number;
  behind: number;
  files: { path: string; status: string }[];
  file_count: number;
  sensitive: string[];
  large: string[];
  commits: { sha: string; subject: string }[];
  has_commits: boolean;
  action: PublishAction;
  blocked_reason: string | null;
  gh: { available: boolean; user: string | null } | null;
  default_message: string;
  default_repo_name: string;
}
export interface PublishResult {
  ok: boolean;
  error: string | null;
  steps: { step: string; cmd: string; ok: boolean; output: string }[];
  github_url: string | null;
  ahead: number;
  changes: number;
}

export type DevProjectStage = "idea" | "active" | "maintenance" | "paused" | "archived";
export interface DevProjectMeta {
  alias: string;
  description: string;
  tags: string[];
  stage: DevProjectStage | "";
  notes: string;
  updated_at: string | null;
}
export interface DevProjectDetail {
  item: DevProjectItem;
  meta: DevProjectMeta;
  readme: { file: string; content: string; truncated: boolean; markdown: boolean; title: string | null; summary: string | null } | null;
  languages: { name: string; bytes: number; pct: number }[];
  stack: string[];
  manifest: { kind: string; name?: string | null; description?: string | null; version?: string | null } | null;
  git: {
    commit_count: number | null;
    first_commit_at: string | null;
    file_count: number;
    recent_commits: { sha: string; at: string; author: string; subject: string }[];
    branches: { name: string; upstream: string | null; current: boolean; ahead: number; behind: number; gone: boolean; last_commit_at: string | null }[];
    contributors: { name: string; commits: number }[];
  };
  tokens: { key: string; name: string; tokens: number; cost: number; sessions: number; month_tokens: number; last_active: string | null; same_path: boolean } | null;
  editor: boolean;
  stages: DevProjectStage[];
}

// ------------------------------------------------------------- F29 agent ----
export type AgentToolKind = "read" | "write" | "external";
export type AgentToolStatus = "pending" | "running" | "ok" | "error" | "blocked" | "denied" | "awaiting";
export interface AgentToolCall {
  id: string;
  name: string;
  args: string | null;
  kind: AgentToolKind | null;
  status: AgentToolStatus;
  result: string | null;
  chars: number | null;
  ms: number | null;
  runId?: string;
}
export interface AgentUserMessage { role: "user"; content: string; seq?: number; at?: string }
export interface AgentAssistantMessage {
  role: "assistant";
  content: string;
  reasoning: string;
  tool_calls: AgentToolCall[];
  seq?: number;
  at?: string;
}
export type AgentMessage = AgentUserMessage | AgentAssistantMessage;
export interface AgentConversationSummary {
  id: string;
  kind: "chat" | "patrol";
  title: string;
  created_at: string;
  updated_at: string;
  model: string | null;
  cost_usd: number;
  running: boolean;
}
export interface AgentUsage { hit: number; miss: number; completion: number; cost_usd: number; requests: number }
export interface AgentConversation extends Omit<AgentConversationSummary, "cost_usd"> {
  messages: AgentMessage[];
  usage: AgentUsage;
}
export interface AgentPatrolConfig {
  enabled: boolean;
  schedule: "daily" | "weekly";
  time: string;
  weekday: number;
  use_llm: boolean;
  notify: boolean;
  thinking: boolean;
}
export interface AgentSettings {
  base_url: string;
  model: string;
  models: string[];
  thinking: boolean;
  confirm_side_effects: boolean;
  max_iterations: number;
  max_context_tokens: number;
  max_external_calls: number;
  pricing: Record<string, { input_miss: number; input_hit: number; output: number }>;
  patrol: AgentPatrolConfig;
  key: { configured: boolean; source: "env" | "stored" | "none"; masked: string | null };
  patrol_status: { last_run: string | null; last_conversation: string | null; last_error: string | null; running: boolean };
}
export interface AgentUsageSummary {
  range: string;
  requests: number;
  cost_usd: number;
  cache_hit_rate: number | null;
  tokens: { input_cache_hit: number; input_cache_miss: number; output: number; reasoning: number };
  by_model: { model: string; cost_usd: number; requests: number; tokens: number }[];
  daily: { date: string; cost_usd: number }[];
}
