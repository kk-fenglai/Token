export function formatTokens(n: number): string {
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
  return String(n);
}

export function formatUSD(n: number, decimals = 2): string {
  return `$${n.toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })}`;
}

/** UTC ISO ("...Z") → local "YYYY-MM-DD HH:mm:ss". */
export function formatLocalTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const pad = (x: number) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "从未";
  const diff = Date.now() - new Date(iso).getTime();
  const min = Math.floor(diff / 60000);
  if (min < 1) return "刚刚";
  if (min < 60) return `${min} 分钟前`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h} 小时前`;
  return `${Math.floor(h / 24)} 天前`;
}

export const FAMILY_LABELS: Record<string, string> = {
  fable: "Fable",
  opus: "Opus",
  sonnet: "Sonnet",
  haiku: "Haiku",
  other: "其他",
};

export const FAMILY_COLORS: Record<string, string> = {
  fable: "#005589",
  opus: "#0F6EAD",
  sonnet: "#7C9CB5",
  haiku: "#C9D8E4",
  other: "#E8833A",
};

export const SERIES_COLORS = {
  input: "#0F6EAD",
  output: "#E8833A",
  cache_write: "#7C9CB5",
  cache_read: "#C9D8E4",
};

export const SERIES_LABELS: Record<string, string> = {
  input: "Input",
  output: "Output",
  cache_write: "Cache Write",
  cache_read: "Cache Read",
};
