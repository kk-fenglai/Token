import type { DevPriority, DevProjectItem, DevProjectLevel, DevProjectsConfig } from "../api/types";
import type { TFunc } from "../i18n";

export const LEVEL_BADGE: Record<DevProjectLevel, { cls: string; icon: string }> = {
  danger: { cls: "bg-error-container text-on-error-container", icon: "error" },
  warn: { cls: "bg-secondary-container/25 text-secondary", icon: "warning" },
  info: { cls: "bg-surface text-on-surface-variant", icon: "info" },
  ok: { cls: "bg-success-container text-on-success-container", icon: "check_circle" },
};

export const ROW_ACCENT: Record<DevProjectLevel, string> = {
  danger: "border-l-error",
  warn: "border-l-secondary-container",
  info: "border-l-outline-variant",
  ok: "border-l-success",
};

export function reasonText(t: TFunc, p: DevProjectItem, r: string): string {
  const h = r.startsWith("unpushed") ? p.unpushed_age_hours : p.dirty_age_hours;
  return t(`devProjects.reasons.${r}`, { h: Math.round(h ?? 0) });
}

// Anything that is not already fully on its remote: commits to push, changes
// to commit, a branch without upstream, or no remote at all.
export function canPublish(p: DevProjectItem): boolean {
  if (!p.is_repo || p.error || p.detached) return false;
  return p.ahead > 0 || p.changes > 0 || !p.has_upstream || !p.remote_url;
}

export async function putConfig(partial: Partial<DevProjectsConfig>): Promise<void> {
  const res = await fetch("/api/dev-projects/config", {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(partial),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
}

export async function postJson(url: string, body: unknown): Promise<Response> {
  return fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}

export const PRIORITY_BADGE: Record<DevPriority, string> = {
  P0: "bg-error-container text-on-error-container",
  P1: "bg-secondary-container/25 text-secondary",
  P2: "bg-primary-container/10 text-primary-container",
  P3: "bg-surface text-on-surface-variant",
};

/** Sort rank of a project / todo priority; unset sorts last. */
export const priorityRank = (p: DevPriority | "" | undefined) => (p ? Number(p[1]) : 9);

export async function sendJson(url: string, method: string, body?: unknown): Promise<Response> {
  return fetch(url, {
    method, headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export const detailHref = (path: string) => `/dev-projects/detail?path=${encodeURIComponent(path)}`;
