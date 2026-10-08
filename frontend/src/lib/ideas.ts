// F30 inspiration board — types, labels and API helpers shared by the pages.
// The board is a private, Chinese-language research tool, so its labels live
// here rather than in the three i18n dictionaries.

export interface ProductDetail {
  description?: string | null;
  value_proposition?: string | null;
  problem_solved?: string | null;
  pricing_model?: string | null;
  target_persona?: string | null;
  business_type?: string | null;
  team_size?: string | null;
  funding_status?: string | null;
  estimated_users?: number | null;
  tech_stack?: { slug: string; category: string | null }[];
  marketing_channels?: { slug: string; category: string | null }[];
  founded?: string | null;
  x_followers?: number | null;
  domain_rating?: number | null;
}

export interface Product {
  slug: string;
  source: string;
  name: string;
  description: string | null;
  website: string | null;
  url: string | null;
  icon: string | null;
  category: string | null;
  target_audience: string | null;
  payment_provider: string | null;
  country: string | null;
  mrr: number | null;
  revenue_30d: number | null;
  revenue_total: number | null;
  customers: number | null;
  active_subs: number | null;
  growth_30d: number | null;
  growth_mrr_30d: number | null;
  visitors_30d: number | null;
  on_sale: boolean;
  first_seen: string;
  updated_at: string;
  detail_at: string | null;
  detail: ProductDetail;
  mark?: "interested" | "ignored" | null;
  clusters?: number[] | { id: number; name: string }[];
  public_md?: string | null;
  public_md_at?: string | null;
  snapshots?: { day: string; mrr: number | null; revenue_30d: number | null; customers: number | null; growth_30d: number | null }[];
}

export interface ProductList {
  items: Product[];
  total: number;
  page: number;
  limit: number;
  categories: string[];
}

export interface ClusterStats {
  count: number;
  paying_count: number;
  mrr_median: number | null;
  mrr_min: number | null;
  mrr_max: number | null;
  customers: number;
  arpu_median: number | null;
  growing_share: number | null;
  top_share: number | null;
}

export interface ClusterSummary {
  id: number;
  name: string;
  note: string;
  created_at: string;
  updated_at: string;
  stats: ClusterStats;
  observations: number;
  products: { slug: string; name: string; mrr: number | null }[];
  card: { id: number; status: Status } | null;
}

export type Status = "draft" | "validating" | "doing" | "watching" | "dropped";
export type Verdict = "gates" | "validate" | "watch" | "drop";

export interface Observation {
  id: number;
  text: string;
  tags: string[];
  cluster_id: number | null;
  cluster_name?: string | null;
  created_at: string;
}

export interface Validation {
  id: number;
  card_id: number;
  action: string;
  day: string;
  result: string;
  created_at: string;
}

export interface Evaluation {
  total: number;
  scored: number;
  base_tier: number;
  tier: number;
  gates_passed: number;
  gates_ok: boolean;
  verdict: Verdict;
}

export interface Card {
  id: number;
  cluster_id: number | null;
  need: string;
  payer: string;
  job: string;
  alternative: string;
  life_mapping: string;
  validation_action: string;
  conclusion: string;
  status: Status;
  gates: Partial<Record<GateKey, boolean>>;
  scores: Partial<Record<ScoreKey, number>>;
  red_flags: FlagKey[];
  created_at: string;
  updated_at: string;
  cluster: { id: number; name: string; note: string } | null;
  products: Product[];
  cluster_stats: ClusterStats;
  validations: Validation[];
  observations: Observation[];
  suggested: { gates: Partial<Record<GateKey, boolean>>; scores: Partial<Record<ScoreKey, number>>; red_flags: FlagKey[] };
  evaluation: Evaluation;
  last_activity: string;
  stale: boolean;
}

export interface SyncRun {
  id: number;
  started_at: string;
  finished_at: string | null;
  mode: string;
  requests: number;
  products: number;
  details: number;
  status: string;
  error: string | null;
}

export interface SyncConfig {
  auto_sync: boolean;
  sync_hours: number;
  min_mrr: number;
  max_mrr: number;
  max_requests: number;
  max_details: number;
  rate_per_minute: number;
}

export interface SyncStatus {
  running: boolean;
  phase?: string | null;
  page?: number;
  total?: number;
  slug?: string;
  started_at?: string;
  last_result?: { status: string; error: string | null };
  runs: SyncRun[];
  key: { configured: boolean; source: string; masked: string | null };
  config: SyncConfig;
  cursor_page: number;
  last_full_sweep: string | null;
}

export interface WeekData {
  new_signals: number;
  products: number;
  unmarked: number;
  interested: number;
  clusters: number;
  observations_week: number;
  validated_month: number;
  marked_week: number;
  cards_by_status: Record<Status, number>;
  validating: { id: number; need: string; status: Status; last_activity: string; evaluation: Evaluation; stale: boolean }[];
  ready_clusters: { id: number; name: string; n: number }[];
  recent_observations: Observation[];
  sync: SyncStatus;
}

// ------------------------------------------------------------- labels ----

export const STATUSES: Status[] = ["draft", "validating", "watching", "doing", "dropped"];

export const STATUS_LABEL: Record<Status, string> = {
  draft: "草稿",
  validating: "待验证",
  watching: "观察",
  doing: "做",
  dropped: "放弃",
};

export const STATUS_STYLE: Record<Status, string> = {
  draft: "bg-surface text-on-surface-variant border-border-card",
  validating: "bg-[#fff4e5] text-secondary border-[#f5c99b]",
  watching: "bg-[#e8f1f8] text-primary border-[#b9d3e8]",
  doing: "bg-success-container text-on-success-container border-[#a8dcbf]",
  dropped: "bg-surface text-outline border-border-card line-through",
};

export const VERDICT_LABEL: Record<Verdict, string> = {
  gates: "门槛未全过",
  validate: "本周就做验证",
  watch: "标记为观察",
  drop: "放弃",
};

export const VERDICT_STYLE: Record<Verdict, string> = {
  gates: "text-on-surface-variant",
  validate: "text-success",
  watch: "text-primary",
  drop: "text-error",
};

export type GateKey = "paying" | "recurring" | "who" | "reach" | "doable";
export const GATES: { key: GateKey; label: string; hint: string }[] = [
  { key: "paying", label: "有人付钱", hint: "至少 3 个互不相关的产品在解决它,每个 MRR ≥ $1k" },
  { key: "recurring", label: "付钱是持续的", hint: "订阅或复购型收入,不是一次性买断" },
  { key: "who", label: "说得清是谁", hint: "能写出“谁在什么场景想完成什么”,句子里不出现产品名" },
  { key: "reach", label: "我接触得到", hint: "一周内能找到 3 个有这个问题的人聊" },
  { key: "doable", label: "我做得动", hint: "单人 4–6 周能做出最小版本,不需要牌照、大笔资金或双边网络" },
];

export type ScoreKey = "strength" | "breadth" | "frequency" | "alternative_gap" | "reach" | "trend";
export const SCORES: { key: ScoreKey; label: string; levels: [string, string, string]; source: string }[] = [
  { key: "strength", label: "付费强度", levels: ["刚过门槛", "3–5 个产品", "6 个以上,或 MRR 中位数 ≥ $5k"], source: "MRR、需求簇产品数" },
  { key: "breadth", label: "普遍性", levels: ["靠少数大客户", "介于两者之间", "客户多、客单价低"], source: "客户数、MRR ÷ 客户数" },
  { key: "frequency", label: "发生频率", levels: ["一年几次", "每月", "每周或每天"], source: "我的判断" },
  { key: "alternative_gap", label: "现有办法有多差", levels: ["身边已有好用的产品", "有产品但不顺手", "还在用手工、微信、表格凑合"], source: "生活观察" },
  { key: "reach", label: "可触达性", levels: ["要从零找人", "能通过朋友找到", "就是我现有的客户或熟人"], source: "我自己" },
  { key: "trend", label: "趋势", levels: ["簇内产品多数在下滑", "持平", "不断有新产品出现且在增长"], source: "30 天增长、新增项目" },
];

export type FlagKey = "peer_loop" | "founder_audience" | "head_monopoly" | "overseas_only" | "hype_churn" | "nobody_cares";
export const RED_FLAGS: { key: FlagKey; label: string; hint: string }[] = [
  { key: "peer_loop", label: "圈内自循环", hint: "产品卖给独立开发者或创业者自己,是同行的需求,不是生活需求" },
  { key: "founder_audience", label: "靠创始人影响力获客", hint: "主要渠道是创始人的个人账号,换个人做不成立" },
  { key: "head_monopoly", label: "头部独占", hint: "簇内收入集中在一个产品,其余都很小" },
  { key: "overseas_only", label: "依赖海外特有环境", hint: "当地税务、法规、支付或平台生态,搬到我身边不存在" },
  { key: "hype_churn", label: "热点套壳", hint: "增长很快但流失率也高,付费的是新鲜感" },
  { key: "nobody_cares", label: "身边没人觉得是问题", hint: "聊过 3 个人都不认为麻烦,即使数据再好也放弃" },
];

export const CARD_FIELDS: { key: "need" | "payer" | "job" | "alternative" | "life_mapping" | "validation_action" | "conclusion"; label: string; question: string; rows: number }[] = [
  { key: "need", label: "需求一句话", question: "谁在什么场景下想完成什么", rows: 2 },
  { key: "payer", label: "付费的人", question: "付钱的是什么角色、什么行业", rows: 2 },
  { key: "job", label: "要完成的事", question: "他们花钱是为了省什么、得到什么", rows: 2 },
  { key: "alternative", label: "现有替代", question: "我身边的人现在怎么解决", rows: 2 },
  { key: "life_mapping", label: "生活映射", question: "我认识的谁有这个问题,能不能直接问到", rows: 3 },
  { key: "validation_action", label: "验证动作", question: "一周内能做的最小验证", rows: 2 },
  { key: "conclusion", label: "结论", question: "做、观察或放弃,以及理由", rows: 3 },
];

export const AUDIENCE_LABEL: Record<string, string> = { b2b: "B2B", b2c: "B2C", both: "B2B + B2C" };

// ------------------------------------------------------------ formatting ----

export function usd(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  if (Math.abs(v) >= 1000) return `$${(v / 1000).toFixed(v >= 10000 ? 0 : 1)}k`;
  return `$${Math.round(v)}`;
}

export function pct(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  if (Math.abs(v) >= 1000) return `${v > 0 ? "+" : ""}${Math.round(v / 100) / 10}k%`;
  return `${v > 0 ? "+" : ""}${Math.round(v)}%`;
}

export function num(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return v.toLocaleString("zh-CN");
}

export function day(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" });
}

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

// ------------------------------------------------------------------ API ----

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(`HTTP ${status}`);
  }
}

export async function api<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const res = await fetch(`/api/ideas${path}`, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail: unknown = null;
    try { detail = (await res.json()).detail; } catch { /* not JSON */ }
    throw new ApiError(res.status, detail);
  }
  const type = res.headers.get("content-type") ?? "";
  return (type.includes("json") ? await res.json() : await res.text()) as T;
}

export function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    const d = e.detail as { reasons?: string[] } | string | string[] | null;
    if (d && typeof d === "object" && !Array.isArray(d) && d.reasons) {
      const map: Record<string, string> = { signals: "需求簇里至少要有 3 个产品信号", life_mapping: "还没填“生活映射”" };
      return `不能离开草稿:${d.reasons.map((r) => map[r] ?? r).join(";")}`;
    }
    if (Array.isArray(d)) return d.join(";");
    if (typeof d === "string") return d;
    return e.message;
  }
  return e instanceof Error ? e.message : String(e);
}

export const productHref = (slug: string) => `/ideas/signal?slug=${encodeURIComponent(slug)}`;
export const cardHref = (id: number) => `/ideas/card?id=${id}`;
