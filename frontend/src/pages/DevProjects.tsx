import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import type { DevProjectItem, DevProjectLevel, DevProjectsConfig, DevProjectsResponse } from "../api/types";
import { useApi } from "../api/useApi";
import StatCard from "../components/StatCard";
import { useI18n, type TFunc } from "../i18n";
import { formatRelative } from "../lib/format";

const LEVEL_BADGE: Record<DevProjectLevel, { cls: string; icon: string }> = {
  danger: { cls: "bg-error-container text-on-error-container", icon: "error" },
  warn: { cls: "bg-secondary-container/25 text-secondary", icon: "warning" },
  info: { cls: "bg-surface text-on-surface-variant", icon: "info" },
  ok: { cls: "bg-success-container text-on-success-container", icon: "check_circle" },
};

const ROW_ACCENT: Record<DevProjectLevel, string> = {
  danger: "border-l-error",
  warn: "border-l-secondary-container",
  info: "border-l-outline-variant",
  ok: "border-l-success",
};

function reasonText(t: TFunc, p: DevProjectItem, r: string): string {
  const h = r.startsWith("unpushed") ? p.unpushed_age_hours : p.dirty_age_hours;
  return t(`devProjects.reasons.${r}`, { h: Math.round(h ?? 0) });
}

async function putConfig(partial: Partial<DevProjectsConfig>): Promise<void> {
  const res = await fetch("/api/dev-projects/config", {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(partial),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
}

export default function DevProjects() {
  const { t, tag } = useI18n();
  const location = useLocation();
  const focus = new URLSearchParams(location.search).get("focus");
  const snap = useApi<DevProjectsResponse>("/api/dev-projects");
  const [busy, setBusy] = useState(false);
  const [copiedPath, setCopiedPath] = useState<string | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [showIgnored, setShowIgnored] = useState(false);
  const [newPath, setNewPath] = useState("");
  const [toastState, setToastState] = useState<"idle" | "sent" | "failed">("idle");
  const [form, setForm] = useState<Pick<DevProjectsConfig, "active_days" | "unpushed_danger_hours" | "dirty_warn_hours" | "desktop_notify"> | null>(null);
  const [saved, setSaved] = useState(false);

  const rel = (iso: string | null | undefined) =>
    formatRelative(iso, tag, { never: t("common.never"), justNow: t("common.justNow") });

  useEffect(() => {
    if (snap.data && !form) {
      const c = snap.data.config;
      setForm({ active_days: c.active_days, unpushed_danger_hours: c.unpushed_danger_hours,
        dirty_warn_hours: c.dirty_warn_hours, desktop_notify: c.desktop_notify });
    }
  }, [snap.data, form]);

  // Scroll the row an alert linked to into view once data is there.
  useEffect(() => {
    if (focus && snap.data) {
      document.getElementById(`dp-${focus}`)?.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }, [focus, snap.data]);

  async function run(fn: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    try { await fn(); snap.retry(); } catch { /* the panel re-fetches and shows the error state */ } finally { setBusy(false); }
  }

  const refresh = () => run(async () => { await fetch("/api/dev-projects/refresh", { method: "POST" }); });
  const cfg = snap.data?.config;

  const pin = (p: DevProjectItem) => run(() => putConfig({
    pinned: p.pinned ? (cfg?.pinned ?? []).filter((x) => x !== p.path) : [...(cfg?.pinned ?? []), p.path],
  }));
  const ignore = (p: DevProjectItem) => run(() => putConfig({ ignored: [...(cfg?.ignored ?? []), p.path] }));
  const unignore = (path: string) => run(() => putConfig({ ignored: (cfg?.ignored ?? []).filter((x) => x !== path) }));
  const addPath = () => {
    const v = newPath.trim();
    if (!v) return;
    run(async () => { await putConfig({ extra: [...(cfg?.extra ?? []), v] }); setNewPath(""); });
  };
  const openFolder = (p: DevProjectItem) =>
    fetch("/api/dev-projects/open", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: p.path }) });

  async function copyPush(p: DevProjectItem) {
    try {
      await navigator.clipboard.writeText(`git -C "${p.path}" push`);
      setCopiedPath(p.path);
      setTimeout(() => setCopiedPath(null), 1500);
    } catch { /* clipboard blocked */ }
  }

  async function saveSettings() {
    if (!form) return;
    await run(() => putConfig(form));
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  }

  async function testToast() {
    try {
      const res = await fetch("/api/dev-projects/notify-test", { method: "POST" });
      const json = await res.json();
      setToastState(json.sent ? "sent" : "failed");
    } catch { setToastState("failed"); }
    setTimeout(() => setToastState("idle"), 3000);
  }

  const data = snap.data;
  const items = data?.items ?? [];
  const num = (v: number) => (data ? String(v) : "…");

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold">{t("devProjects.title")}</h3>
          <p className="mt-0.5 max-w-3xl text-xs text-on-surface-variant">
            {t("devProjects.subtitle", { days: cfg?.active_days ?? 14 })}
          </p>
        </div>
        <div className="flex items-center gap-3 text-xs text-on-surface-variant">
          {data && <span>{t("devProjects.lastChecked", { time: rel(data.checked_at) })}</span>}
          <button onClick={() => setShowSettings((s) => !s)}
            className="flex items-center gap-1 rounded border border-border-card px-3 py-1.5 text-sm text-on-surface-variant hover:bg-surface">
            <span className="material-symbols-outlined text-[18px]">settings</span>{t("devProjects.settings")}
          </button>
          <button onClick={refresh} disabled={busy}
            className="flex items-center gap-1 rounded bg-primary-container px-3 py-1.5 text-sm font-semibold text-on-primary hover:opacity-90 disabled:opacity-60">
            <span className={`material-symbols-outlined text-[18px] ${busy ? "animate-spin" : ""}`}>refresh</span>
            {busy ? t("devProjects.refreshing") : t("devProjects.refresh")}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <StatCard label={t("devProjects.tracked")} icon="folder_code" value={num(data?.summary.tracked ?? 0)} />
        <StatCard label={t("devProjects.needsPush")} icon="cloud_upload" value={num(data?.summary.needs_push ?? 0)}
          note={data && data.summary.needs_push === 0 ? t("devProjects.allClean") : undefined}
          accent={data && data.summary.needs_push > 0 ? "text-error" : "text-success"} />
        <StatCard label={t("devProjects.dirty")} icon="edit_note" value={num(data?.summary.dirty ?? 0)} />
        <StatCard label={t("devProjects.noRemote")} icon="cloud_off" value={num(data?.summary.no_remote ?? 0)} />
      </div>

      {showSettings && form && (
        <section className="rounded border border-border-card bg-surface-card p-4 shadow-card">
          <div className="grid gap-4 md:grid-cols-3">
            {(["active_days", "unpushed_danger_hours", "dirty_warn_hours"] as const).map((k) => (
              <label key={k} className="text-sm">
                <span className="block text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
                  {t(`devProjects.${k === "active_days" ? "activeDays" : k === "unpushed_danger_hours" ? "unpushedDangerHours" : "dirtyWarnHours"}`)}
                </span>
                <input type="number" min={1} value={form[k]}
                  onChange={(e) => setForm({ ...form, [k]: Math.max(1, parseInt(e.target.value || "1", 10)) })}
                  className="mt-1 w-full rounded border border-border-card bg-surface px-3 py-1.5 font-mono text-sm" />
              </label>
            ))}
          </div>
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <label className="flex items-start gap-2 text-sm">
              <input type="checkbox" checked={form.desktop_notify}
                onChange={(e) => setForm({ ...form, desktop_notify: e.target.checked })} className="mt-1" />
              <span>
                <span className="font-medium">{t("devProjects.desktopNotify")}</span>
                <span className="block text-xs text-on-surface-variant">{t("devProjects.desktopNotifyHint")}</span>
                {data?.notify.last_sent && (
                  <span className="block text-xs text-outline">{t("devProjects.notifyLast", { time: rel(data.notify.last_sent) })}</span>
                )}
              </span>
            </label>
            <div className="flex items-center gap-2">
              <button onClick={testToast} className="rounded border border-border-card px-3 py-1.5 text-sm hover:bg-surface">
                {toastState === "sent" ? t("devProjects.toastSent") : toastState === "failed" ? t("devProjects.toastFailed") : t("devProjects.testToast")}
              </button>
              <button onClick={saveSettings} disabled={busy}
                className="rounded bg-primary-container px-4 py-1.5 text-sm font-semibold text-on-primary hover:opacity-90 disabled:opacity-60">
                {saved ? t("devProjects.saved") : t("devProjects.save")}
              </button>
            </div>
          </div>
        </section>
      )}

      <section className="rounded border border-border-card bg-surface-card p-4 shadow-card">
        {snap.error ? (
          <div className="flex h-48 flex-col items-center justify-center gap-3 text-sm text-on-surface-variant">
            <span>{t("common.loadFailed", { error: snap.error })}</span>
            <button onClick={snap.retry} className="rounded border border-primary-container px-3 py-1.5 text-primary-container hover:bg-surface">{t("common.retry")}</button>
          </div>
        ) : snap.loading && !data ? (
          <div className="flex h-48 items-center justify-center text-sm text-on-surface-variant">{t("common.loading")}</div>
        ) : data && !data.git_available ? (
          <div className="flex items-center gap-3 rounded border border-l-4 border-border-card border-l-error bg-surface px-4 py-3 text-sm">
            <span className="material-symbols-outlined text-error">error</span>{t("devProjects.gitMissing")}
          </div>
        ) : !items.length ? (
          <div className="flex h-48 items-center justify-center text-sm text-on-surface-variant">{t("devProjects.empty")}</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[960px] text-sm">
              <thead>
                <tr className="border-b border-border-card text-left text-xs font-semibold uppercase tracking-wide text-on-surface-variant [&>th]:whitespace-nowrap">
                  <th className="py-2 pr-3">{t("devProjects.colStatus")}</th>
                  <th className="px-3 py-2">{t("devProjects.colProject")}</th>
                  <th className="px-3 py-2">{t("devProjects.colBranch")}</th>
                  <th className="px-3 py-2">{t("devProjects.colSync")}</th>
                  <th className="px-3 py-2 text-right">{t("devProjects.colChanges")}</th>
                  <th className="px-3 py-2">{t("devProjects.colLastCommit")}</th>
                  <th className="px-3 py-2">{t("devProjects.colLastActive")}</th>
                  <th className="py-2 pl-3 text-right">{t("devProjects.colActions")}</th>
                </tr>
              </thead>
              <tbody>
                {items.map((p) => {
                  const b = LEVEL_BADGE[p.level];
                  const focused = focus === p.path;
                  return (
                    <tr key={p.path} id={`dp-${p.path}`}
                      className={`border-b border-l-4 border-border-card/60 ${ROW_ACCENT[p.level]} last:border-b-0 hover:bg-surface/60 ${focused ? "bg-primary-container/5" : ""}`}>
                      <td className="py-2.5 pl-2 pr-3 align-top">
                        <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${b.cls}`}>
                          <span className="material-symbols-outlined text-[14px]">{b.icon}</span>
                          {t(`devProjects.status.${p.level}`)}
                        </span>
                        {p.reasons.length > 0 && (
                          <div className="mt-1 flex max-w-[220px] flex-wrap gap-1">
                            {p.reasons.map((r) => (
                              <span key={r} className="rounded bg-surface px-1.5 py-0.5 text-[10px] text-on-surface-variant">{reasonText(t, p, r)}</span>
                            ))}
                          </div>
                        )}
                      </td>
                      <td className="px-3 py-2.5 align-top">
                        <div className="flex items-center gap-1.5 font-medium">
                          {p.pinned && <span className="material-symbols-outlined text-[16px] text-primary-container">push_pin</span>}
                          {p.name}
                        </div>
                        <div className="font-mono text-[11px] text-outline" title={p.path}>{p.path}</div>
                        <div className="mt-0.5 flex gap-1">
                          {p.sources.map((s) => (
                            <span key={s} className="rounded bg-surface px-1.5 py-0.5 text-[10px] text-outline">{t(`devProjects.sources.${s}`)}</span>
                          ))}
                        </div>
                      </td>
                      <td className="px-3 py-2.5 align-top font-mono text-xs">
                        {p.branch ?? (p.detached ? "HEAD" : "—")}
                      </td>
                      <td className="px-3 py-2.5 align-top font-mono text-xs">
                        {!p.is_repo || p.error ? "—" : !p.has_upstream ? (
                          <span className="text-on-surface-variant">{t("devProjects.noUpstream")}</span>
                        ) : (
                          <span>
                            <span className={p.ahead > 0 ? "font-semibold text-error" : "text-on-surface-variant"}>↑{p.ahead}</span>
                            {" "}
                            <span className="text-on-surface-variant">↓{p.behind}</span>
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2.5 text-right align-top font-mono text-xs"
                        title={t("devProjects.changesDetail", { m: p.modified, u: p.untracked, s: p.staged })}>
                        {p.changes > 0 ? <span className={p.reasons.includes("dirty_stale") ? "font-semibold text-secondary" : ""}>{p.changes}</span> : <span className="text-on-surface-variant">0</span>}
                      </td>
                      <td className="px-3 py-2.5 align-top text-xs text-on-surface-variant">{rel(p.last_commit_at)}</td>
                      <td className="px-3 py-2.5 align-top text-xs text-on-surface-variant">{p.last_active ? rel(p.last_active) : "—"}</td>
                      <td className="py-2.5 pl-3 text-right align-top">
                        <div className="flex justify-end gap-0.5">
                          {p.ahead > 0 && (
                            <button onClick={() => copyPush(p)} title={t("devProjects.copyPush")}
                              className="rounded p-1 text-primary-container hover:bg-surface">
                              <span className="material-symbols-outlined text-[18px]">{copiedPath === p.path ? "check" : "content_copy"}</span>
                            </button>
                          )}
                          {p.github_url && (
                            <a href={p.github_url} target="_blank" rel="noreferrer" title={t("devProjects.openGithub")}
                              className="rounded p-1 text-on-surface-variant hover:bg-surface">
                              <span className="material-symbols-outlined text-[18px]">open_in_new</span>
                            </a>
                          )}
                          <button onClick={() => openFolder(p)} title={t("devProjects.openFolder")}
                            className="rounded p-1 text-on-surface-variant hover:bg-surface">
                            <span className="material-symbols-outlined text-[18px]">folder_open</span>
                          </button>
                          <button onClick={() => pin(p)} title={p.pinned ? t("devProjects.unpin") : t("devProjects.pin")}
                            className={`rounded p-1 hover:bg-surface ${p.pinned ? "text-primary-container" : "text-on-surface-variant"}`}>
                            <span className="material-symbols-outlined text-[18px]">{p.pinned ? "keep_off" : "push_pin"}</span>
                          </button>
                          <button onClick={() => ignore(p)} title={t("devProjects.ignore")}
                            className="rounded p-1 text-on-surface-variant hover:bg-surface hover:text-error">
                            <span className="material-symbols-outlined text-[18px]">visibility_off</span>
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-border-card pt-4">
          <label className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">{t("devProjects.addPath")}</label>
          <input value={newPath} onChange={(e) => setNewPath(e.target.value)} placeholder={t("devProjects.addPlaceholder")}
            onKeyDown={(e) => { if (e.key === "Enter") addPath(); }}
            className="min-w-[320px] flex-1 rounded border border-border-card bg-surface px-3 py-1.5 font-mono text-xs" />
          <button onClick={addPath} disabled={busy || !newPath.trim()}
            className="rounded border border-primary-container px-3 py-1.5 text-sm text-primary-container hover:bg-surface disabled:opacity-50">
            {t("devProjects.add")}
          </button>
        </div>
      </section>

      {cfg && cfg.ignored.length > 0 && (
        <section className="rounded border border-border-card bg-surface-card p-4 shadow-card">
          <button onClick={() => setShowIgnored((s) => !s)} className="flex items-center gap-1 text-sm font-semibold">
            <span className="material-symbols-outlined text-[18px]">{showIgnored ? "expand_less" : "expand_more"}</span>
            {t("devProjects.ignoredTitle", { n: cfg.ignored.length })}
          </button>
          {showIgnored && (
            <ul className="mt-3 space-y-1">
              {cfg.ignored.map((path) => (
                <li key={path} className="flex items-center justify-between rounded px-2 py-1 font-mono text-xs hover:bg-surface">
                  <span className="text-on-surface-variant">{path}</span>
                  <button onClick={() => unignore(path)} className="ml-3 font-sans text-primary-container hover:underline">{t("devProjects.unignore")}</button>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}
