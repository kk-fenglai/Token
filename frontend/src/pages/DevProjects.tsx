import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import type { DevPriority, DevProjectItem, DevProjectsConfig, DevProjectsResponse } from "../api/types";
import { useApi } from "../api/useApi";
import PublishDialog from "../components/PublishDialog";
import TodoPanel from "../components/TodoPanel";
import { useI18n } from "../i18n";
import { PRIORITY_BADGE, canPublish, detailHref, putConfig, sendJson } from "../lib/devProjects";
import { formatRelative } from "../lib/format";

/** Dev projects as a plain, hand-ordered list: name, description, priority
 *  and next steps. Git sync details live on each project's detail page. */
export default function DevProjects() {
  const { t, tag } = useI18n();
  const location = useLocation();
  const focus = new URLSearchParams(location.search).get("focus");
  const snap = useApi<DevProjectsResponse>("/api/dev-projects");
  const [busy, setBusy] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showIgnored, setShowIgnored] = useState(false);
  const [newPath, setNewPath] = useState("");
  const [toastState, setToastState] = useState<"idle" | "sent" | "failed">("idle");
  const [form, setForm] = useState<Pick<DevProjectsConfig, "active_days" | "unpushed_danger_hours" | "dirty_warn_hours" | "desktop_notify"> | null>(null);
  const [saved, setSaved] = useState(false);
  const [publishing, setPublishing] = useState<DevProjectItem | null>(null);

  // Local copy so a drag can reorder instantly; re-seeded on each fetch
  // (the saved order comes back from the server), never mid-drag.
  const [list, setList] = useState<DevProjectItem[]>([]);
  const [dragging, setDragging] = useState<string | null>(null);
  const [armed, setArmed] = useState<string | null>(null);
  const dragStart = useRef<string[]>([]);

  const rel = (iso: string | null | undefined) =>
    formatRelative(iso, tag, { never: t("common.never"), justNow: t("common.justNow") });

  const draggingRef = useRef(false);
  draggingRef.current = dragging !== null;
  useEffect(() => {
    if (snap.data && !draggingRef.current) setList(snap.data.items);
  }, [snap.data]);

  useEffect(() => {
    if (snap.data && !form) {
      const c = snap.data.config;
      setForm({ active_days: c.active_days, unpushed_danger_hours: c.unpushed_danger_hours,
        dirty_warn_hours: c.dirty_warn_hours, desktop_notify: c.desktop_notify });
    }
  }, [snap.data, form]);

  useEffect(() => {
    if (focus && snap.data) {
      document.getElementById(`dp-${focus}`)?.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }, [focus, snap.data]);

  async function run(fn: () => Promise<unknown>) {
    if (busy) return;
    setBusy(true);
    try { await fn(); snap.retry(); } catch { /* the panel re-fetches and shows the error state */ } finally { setBusy(false); }
  }

  const refresh = () => run(() => fetch("/api/dev-projects/refresh", { method: "POST" }));
  const cfg = snap.data?.config;

  const saveMeta = (p: DevProjectItem, fields: { alias?: string; description?: string; priority?: DevPriority | "" }) =>
    run(() => sendJson("/api/dev-projects/meta", "PUT", { path: p.path, ...fields }));
  const ignore = (p: DevProjectItem) => run(() => putConfig({ ignored: [...(cfg?.ignored ?? []), p.path] }));
  const unignore = (path: string) => run(() => putConfig({ ignored: (cfg?.ignored ?? []).filter((x) => x !== path) }));
  const addPath = () => {
    const v = newPath.trim();
    if (!v) return;
    run(async () => { await putConfig({ extra: [...(cfg?.extra ?? []), v] }); setNewPath(""); });
  };
  const openFolder = (p: DevProjectItem) => sendJson("/api/dev-projects/open", "POST", { path: p.path });

  function onDragStart(e: React.DragEvent, path: string) {
    dragStart.current = list.map((x) => x.path);
    setDragging(path);
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", path);
  }

  function onDragOver(e: React.DragEvent, overPath: string) {
    if (!dragging) return;
    e.preventDefault();
    if (overPath === dragging) return;
    setList((cur) => {
      const from = cur.findIndex((x) => x.path === dragging);
      const to = cur.findIndex((x) => x.path === overPath);
      if (from < 0 || to < 0) return cur;
      const next = [...cur];
      next.splice(to, 0, next.splice(from, 1)[0]);
      return next;
    });
  }

  async function onDragEnd() {
    const paths = list.map((x) => x.path);
    setArmed(null);
    if (paths.join("\n") !== dragStart.current.join("\n")) {
      await sendJson("/api/dev-projects/order", "PUT", { paths }).catch(() => null);
    }
    setDragging(null);
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

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold">{t("devProjects.title")}</h3>
          <p className="mt-0.5 max-w-3xl text-xs text-on-surface-variant">{t("devTodos.listSubtitle")}</p>
        </div>
        <div className="flex items-center gap-3 text-xs text-on-surface-variant">
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

      {snap.error ? (
        <Box>
          <span>{t("common.loadFailed", { error: snap.error })}</span>
          <button onClick={snap.retry} className="rounded border border-primary-container px-3 py-1.5 text-primary-container hover:bg-surface">{t("common.retry")}</button>
        </Box>
      ) : snap.loading && !data ? (
        <Box>{t("common.loading")}</Box>
      ) : !list.length ? (
        <Box>{t("devProjects.empty")}</Box>
      ) : (
        <ul className="space-y-3">
          {list.map((p) => (
            <li key={p.path} id={`dp-${p.path}`}
              draggable={armed === p.path}
              onDragStart={(e) => onDragStart(e, p.path)}
              onDragOver={(e) => onDragOver(e, p.path)}
              onDrop={(e) => e.preventDefault()}
              onDragEnd={onDragEnd}
              className={`flex gap-2 rounded border bg-surface-card p-4 shadow-card transition-opacity ${
                dragging === p.path ? "border-primary-container opacity-50" : focus === p.path ? "border-primary-container" : "border-border-card"}`}>
              <button
                onMouseDown={() => setArmed(p.path)} onMouseUp={() => setArmed(null)}
                title={t("devTodos.drag")} aria-label={t("devTodos.drag")}
                className="material-symbols-outlined -ml-1 shrink-0 cursor-grab self-start rounded p-0.5 text-[20px] text-outline hover:bg-surface hover:text-on-surface active:cursor-grabbing">
                drag_indicator
              </button>
              <div className="grid min-w-0 flex-1 gap-4 lg:grid-cols-5">
                <div className="min-w-0 lg:col-span-2">
                  <div className="flex items-center gap-2">
                    <select value={p.meta?.priority ?? ""} onChange={(e) => saveMeta(p, { priority: e.target.value as DevPriority | "" })}
                      aria-label={t("devTodos.priority")}
                      className={`shrink-0 cursor-pointer rounded px-1 py-0.5 text-[11px] font-semibold ${p.meta?.priority ? PRIORITY_BADGE[p.meta.priority] : "border border-dashed border-border-card bg-transparent text-outline"}`}>
                      <option value="">{t("devTodos.priorityNone")}</option>
                      {(["P0", "P1", "P2", "P3"] as const).map((x) => <option key={x} value={x}>{t(`devTodos.priorities.${x}`)}</option>)}
                    </select>
                    <InlineText value={p.meta?.alias || p.name} title={t("devTodos.rename")} maxLength={80}
                      onSave={(v) => saveMeta(p, { alias: v === p.name ? "" : v })}
                      className="min-w-0 truncate text-base font-semibold" />
                    <div className="ml-auto flex shrink-0 items-center gap-0.5">
                      {canPublish(p) ? (
                        <button onClick={() => setPublishing(p)} title={t("devProjects.publish.button")}
                          className="mr-1 flex items-center gap-1 whitespace-nowrap rounded bg-primary-container px-2 py-1 text-xs font-semibold text-on-primary hover:opacity-90">
                          <span className="material-symbols-outlined text-[16px]">cloud_upload</span>{t("devProjects.publish.button")}
                        </button>
                      ) : p.is_repo && !p.error && (
                        <span className="mr-1 flex items-center gap-0.5 whitespace-nowrap text-xs text-success" title={t("devProjects.status.ok")}>
                          <span className="material-symbols-outlined text-[16px]">cloud_done</span>{t("devProjects.status.ok")}
                        </span>
                      )}
                      <Link to={detailHref(p.path)} title={t("devTodos.details")}
                        className="flex items-center gap-0.5 rounded px-1.5 py-1 text-xs text-primary-container hover:bg-surface">
                        {t("devTodos.details")}<span className="material-symbols-outlined text-[16px]">chevron_right</span>
                      </Link>
                      <button onClick={() => openFolder(p)} title={t("devProjects.openFolder")} aria-label={t("devProjects.openFolder")}
                        className="material-symbols-outlined rounded p-1 text-[18px] text-on-surface-variant hover:bg-surface">folder_open</button>
                      <button onClick={() => ignore(p)} title={t("devProjects.ignore")} aria-label={t("devProjects.ignore")}
                        className="material-symbols-outlined rounded p-1 text-[18px] text-on-surface-variant hover:bg-surface hover:text-error">visibility_off</button>
                    </div>
                  </div>
                  {p.meta?.alias && <div className="mt-0.5 truncate text-xs text-outline">{p.name}</div>}
                  <InlineText multiline value={p.meta?.description ?? ""} placeholder={t("devTodos.descPlaceholder")} maxLength={2000}
                    onSave={(v) => saveMeta(p, { description: v })}
                    className="mt-1.5 whitespace-pre-wrap text-sm text-on-surface-variant" />
                </div>
                <div className="min-w-0 lg:col-span-3">
                  <TodoPanel compact path={p.path} initial={p.todo_items ?? []} />
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}

      {publishing && (
        <PublishDialog path={publishing.path} name={publishing.meta?.alias || publishing.name}
          onClose={(changed) => { setPublishing(null); if (changed) refresh(); }} />
      )}

      <section className="rounded border border-border-card bg-surface-card p-4 shadow-card">
        <div className="flex flex-wrap items-center gap-2">
          <label className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">{t("devProjects.addPath")}</label>
          <input value={newPath} onChange={(e) => setNewPath(e.target.value)} placeholder={t("devProjects.addPlaceholder")}
            onKeyDown={(e) => { if (e.key === "Enter") addPath(); }}
            className="min-w-[240px] flex-1 rounded border border-border-card bg-surface px-3 py-1.5 font-mono text-xs" />
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

function Box({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-48 flex-col items-center justify-center gap-3 rounded border border-border-card bg-surface-card text-sm text-on-surface-variant">
      {children}
    </div>
  );
}

/** Text that turns into an input on click; Enter / blur saves, Esc cancels. */
function InlineText({ value, onSave, placeholder, title, maxLength, multiline, className }: {
  value: string; onSave: (v: string) => void; placeholder?: string; title?: string; maxLength: number;
  multiline?: boolean; className?: string;
}) {
  const { t } = useI18n();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);

  function start() { setDraft(value); setEditing(true); }
  function commit() {
    setEditing(false);
    const v = draft.trim();
    if (v !== value.trim() && (v || multiline)) onSave(v);
  }
  const keys = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") setEditing(false);
    else if (e.key === "Enter" && !e.nativeEvent.isComposing && (!multiline || !e.shiftKey)) { e.preventDefault(); commit(); }
  };

  if (editing) {
    const cls = "w-full rounded border border-primary-container bg-surface px-2 py-1 text-sm text-on-surface";
    return multiline ? (
      <textarea autoFocus rows={3} value={draft} maxLength={maxLength} title={t("devTodos.renameHint")}
        onChange={(e) => setDraft(e.target.value)} onBlur={commit} onKeyDown={keys} className={`mt-1.5 ${cls}`} />
    ) : (
      <input autoFocus value={draft} maxLength={maxLength} title={t("devTodos.renameHint")}
        onChange={(e) => setDraft(e.target.value)} onBlur={commit} onKeyDown={keys} className={`min-w-0 flex-1 ${cls}`} />
    );
  }
  return (
    <button onClick={start} title={title}
      className={`block max-w-full rounded text-left hover:bg-surface ${className ?? ""} ${!value ? "italic text-outline" : ""}`}>
      {value || placeholder}
    </button>
  );
}
