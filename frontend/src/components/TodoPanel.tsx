import { useEffect, useState } from "react";
import type { DevPriority, DevProjectTodo } from "../api/types";
import { useI18n } from "../i18n";
import { PRIORITY_BADGE, sendJson } from "../lib/devProjects";

const PRIORITIES: DevPriority[] = ["P0", "P1", "P2", "P3"];

/** Per-project next steps. Seeded from the detail payload, then kept in sync
 *  by re-reading just the todo list after each change. */
export default function TodoPanel({ path, initial, compact }: { path: string; initial: DevProjectTodo[]; compact?: boolean }) {
  const { t } = useI18n();
  const [todos, setTodos] = useState(initial);
  const [text, setText] = useState("");
  const [priority, setPriority] = useState<DevPriority>("P2");
  const [showDone, setShowDone] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editText, setEditText] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setTodos(initial), [initial]);

  async function call(url: string, method: string, body?: unknown) {
    setError(null);
    const res = await sendJson(url, method, body).catch(() => null);
    if (!res?.ok) { setError(t("devTodos.failed")); return; }
    const list = await fetch(`/api/dev-projects/todos?path=${encodeURIComponent(path)}`).then((r) => r.json()).catch(() => null);
    if (Array.isArray(list)) setTodos(list);
  }

  async function add() {
    const v = text.trim();
    if (!v) return;
    await call("/api/dev-projects/todos", "POST", { path, text: v, priority });
    setText("");
  }

  const patch = (id: number, body: Partial<Pick<DevProjectTodo, "text" | "priority" | "done">>) =>
    call(`/api/dev-projects/todos/${id}`, "PATCH", body);

  async function commitEdit(td: DevProjectTodo) {
    const v = editText.trim();
    setEditingId(null);
    if (v && v !== td.text) await patch(td.id, { text: v });
  }

  const open = todos.filter((x) => !x.done);
  const done = todos.filter((x) => x.done);

  const row = (td: DevProjectTodo) => (
    <li key={td.id} className="group flex items-center gap-2 py-1.5">
      <input type="checkbox" checked={td.done} onChange={() => patch(td.id, { done: !td.done })}
        className="h-4 w-4 shrink-0 accent-primary-container" aria-label={td.text} />
      <select value={td.priority} onChange={(e) => patch(td.id, { priority: e.target.value as DevPriority })}
        aria-label={t("devTodos.priority")}
        className={`shrink-0 cursor-pointer appearance-none rounded px-1.5 py-0.5 text-center text-[11px] font-semibold ${PRIORITY_BADGE[td.priority]} ${td.done ? "opacity-50" : ""}`}>
        {PRIORITIES.map((p) => <option key={p} value={p}>{t(`devTodos.priorities.${p}`)}</option>)}
      </select>
      {editingId === td.id ? (
        <input autoFocus value={editText} maxLength={500} onChange={(e) => setEditText(e.target.value)}
          onBlur={() => commitEdit(td)}
          onKeyDown={(e) => { if (e.key === "Enter") commitEdit(td); else if (e.key === "Escape") setEditingId(null); }}
          className="min-w-0 flex-1 rounded border border-primary-container bg-surface px-2 py-0.5 text-sm" />
      ) : (
        <span title={t("devTodos.edit")} onDoubleClick={() => { setEditingId(td.id); setEditText(td.text); }}
          className={`min-w-0 flex-1 break-words text-sm ${td.done ? "text-outline line-through" : ""}`}>{td.text}</span>
      )}
      <button onClick={() => call(`/api/dev-projects/todos/${td.id}`, "DELETE")} title={t("devTodos.remove")} aria-label={t("devTodos.remove")}
        className="material-symbols-outlined shrink-0 rounded p-0.5 text-[18px] text-outline opacity-0 hover:text-error focus:opacity-100 group-hover:opacity-100">
        delete
      </button>
    </li>
  );

  const doneToggle = done.length > 0 && (
    <button onClick={() => setShowDone((s) => !s)} className="text-xs text-primary-container hover:underline">
      {showDone ? t("devTodos.hideDone") : `${t("devTodos.showDone")} (${done.length})`}
    </button>
  );

  if (compact) {
    return (
      <div>
        {(open.length > 0 || showDone) && (
          <ul className="mb-1.5 divide-y divide-border-card/60">
            {open.map(row)}
            {showDone && done.map(row)}
          </ul>
        )}
        <div className="flex gap-1.5">
          <select value={priority} onChange={(e) => setPriority(e.target.value as DevPriority)} aria-label={t("devTodos.priority")}
            className="rounded border border-border-card bg-surface px-1 py-1 text-xs">
            {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
          <input value={text} maxLength={500} onChange={(e) => setText(e.target.value)} placeholder={t("devTodos.placeholder")}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.nativeEvent.isComposing) add(); }}
            className="min-w-0 flex-1 rounded border border-border-card bg-surface px-2 py-1 text-sm" />
        </div>
        {(error || doneToggle) && (
          <div className="mt-1 flex items-center gap-3">
            {error && <span className="text-xs text-error">{error}</span>}
            <span className="ml-auto">{doneToggle}</span>
          </div>
        )}
      </div>
    );
  }

  return (
    <section className="rounded border border-border-card bg-surface-card p-4 shadow-card">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h4 className="flex items-center gap-1.5 text-sm font-semibold">
          <span className="material-symbols-outlined text-[18px] text-outline">checklist</span>{t("devTodos.title")}
          {open.length > 0 && <span className="rounded-full bg-surface px-1.5 text-[11px] font-normal text-on-surface-variant">{open.length}</span>}
        </h4>
        {doneToggle}
      </div>

      <div className="flex gap-2">
        <select value={priority} onChange={(e) => setPriority(e.target.value as DevPriority)} aria-label={t("devTodos.priority")}
          className="rounded border border-border-card bg-surface px-2 py-1.5 text-sm">
          {PRIORITIES.map((p) => <option key={p} value={p}>{t(`devTodos.priorities.${p}`)}</option>)}
        </select>
        <input value={text} maxLength={500} onChange={(e) => setText(e.target.value)} placeholder={t("devTodos.placeholder")}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.nativeEvent.isComposing) add(); }}
          className="min-w-0 flex-1 rounded border border-border-card bg-surface px-3 py-1.5 text-sm" />
        <button onClick={add} disabled={!text.trim()}
          className="rounded bg-primary-container px-3 py-1.5 text-sm font-semibold text-on-primary hover:opacity-90 disabled:opacity-50">
          {t("devTodos.add")}
        </button>
      </div>
      {error && <p className="mt-2 text-xs text-error">{error}</p>}

      {open.length === 0 && !showDone ? (
        <p className="mt-3 text-sm text-on-surface-variant">
          {t("devTodos.empty")}{done.length > 0 && ` ${t("devTodos.doneCount", { n: done.length })}`}
        </p>
      ) : (
        <ul className="mt-2 divide-y divide-border-card/60">
          {open.map(row)}
          {showDone && done.map(row)}
        </ul>
      )}
    </section>
  );
}
