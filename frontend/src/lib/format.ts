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

/** Locale-aware via Intl.RelativeTimeFormat — no per-language strings needed. */
export function formatRelative(
  iso: string | null | undefined,
  tag = "en-US",
  labels: { never: string; justNow: string } = { never: "never", justNow: "just now" },
): string {
  if (!iso) return labels.never;
  const diff = Date.now() - new Date(iso).getTime();
  const min = Math.floor(diff / 60000);
  if (min < 1) return labels.justNow;
  const rtf = new Intl.RelativeTimeFormat(tag, { numeric: "always", style: "short" });
  if (min < 60) return rtf.format(-min, "minute");
  const h = Math.floor(min / 60);
  if (h < 24) return rtf.format(-h, "hour");
  return rtf.format(-Math.floor(h / 24), "day");
}

/** Model families are product names — only "other" is a real word. */
export const FAMILY_KEYS = ["fable", "opus", "sonnet", "haiku", "other"] as const;

export const FAMILY_COLORS: Record<string, string> = {
  fable: "#005589",
  opus: "#0F6EAD",
  sonnet: "#7C9CB5",
  haiku: "#C9D8E4",
  other: "#E8833A",
};

/** "claude-opus-4-8" → "Opus 4.8"; unknown ids fall back to the raw string.
 *  Product names, so identical in every locale. */
export function modelLabel(model: string): string {
  if (!model || model.startsWith("<")) return model || "—";
  const m = model.replace(/^claude-/, "").replace(/-\d{8}$/, "");
  const parts = m.split("-");
  const family = parts.shift() ?? m;
  const name = family.charAt(0).toUpperCase() + family.slice(1);
  return parts.length ? `${name} ${parts.join(".")}` : name;
}

/** Distinct shades within a family so sibling models stay visually related. */
export function modelColor(family: string, indexInFamily = 0): string {
  const base = FAMILY_COLORS[family] ?? "#E8833A";
  if (indexInFamily === 0) return base;
  const n = parseInt(base.slice(1), 16);
  const mix = (c: number) => Math.round(c + (255 - c) * Math.min(0.22 * indexInFamily, 0.66));
  const [r, g, b] = [mix((n >> 16) & 255), mix((n >> 8) & 255), mix(n & 255)];
  return `#${((r << 16) | (g << 8) | b).toString(16).padStart(6, "0")}`;
}

/** Assigns each model a shade, ordered so same-family models get 0,1,2… */
export function modelColorMap<T extends { model: string; family: string }>(items: T[]): Record<string, string> {
  const seen: Record<string, number> = {};
  const out: Record<string, string> = {};
  for (const it of items) {
    const i = seen[it.family] ?? 0;
    seen[it.family] = i + 1;
    out[it.model] = modelColor(it.family, i);
  }
  return out;
}

/** Rate table is $/Mtok; a single call's cost needs more precision than $0.00. */
export function formatRate(n: number): string {
  return `$${n % 1 === 0 ? n.toFixed(0) : n.toFixed(2)}`;
}

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
