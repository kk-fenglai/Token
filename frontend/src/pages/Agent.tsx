import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import type { AgentConversationSummary, AgentUsageSummary } from "../api/types";
import AgentChat, { formatUsd } from "../components/agent/AgentChat";
import { openAgentSettings, useAgentSettings } from "../components/agent/agentStore";
import { useI18n } from "../i18n";
import { formatRelative } from "../lib/format";
import { usePageContext } from "../lib/pageContext";

type Tab = "chat" | "patrol";

export default function Agent() {
  const { t, tag } = useI18n();
  const [sp, setSp] = useSearchParams();
  const conv = sp.get("c");
  const settings = useAgentSettings();
  const ctx = usePageContext(t("nav.agent"));
  const [tab, setTab] = useState<Tab>("chat");
  const [items, setItems] = useState<AgentConversationSummary[]>([]);
  const [usage, setUsage] = useState<AgentUsageSummary | null>(null);
  const [patrolBusy, setPatrolBusy] = useState(false);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [renameText, setRenameText] = useState("");

  const rel = (iso: string | null | undefined) =>
    formatRelative(iso, tag, { never: t("common.never"), justNow: t("common.justNow") });

  const reload = useCallback(async () => {
    const [list, u] = await Promise.all([
      fetch(`/api/agent/conversations?kind=${tab}`).then((r) => (r.ok ? r.json() : { items: [] })).catch(() => ({ items: [] })),
      fetch("/api/agent/usage?range=30d").then((r) => (r.ok ? r.json() : null)).catch(() => null),
    ]);
    setItems(list.items ?? []);
    setUsage(u);
  }, [tab]);

  useEffect(() => { void reload(); }, [reload]);

  // Deep link from a patrol toast lands on the right tab.
  useEffect(() => {
    if (!conv) return;
    fetch(`/api/agent/conversations/${conv}`).then((r) => (r.ok ? r.json() : null)).then((c) => {
      if (c?.kind && c.kind !== tab) setTab(c.kind);
    }).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conv]);

  const select = useCallback((id: string | null) => {
    setSp(id ? { c: id } : {}, { replace: true });
  }, [setSp]);

  async function runPatrol() {
    setPatrolBusy(true);
    try {
      const r = await fetch("/api/agent/patrol/run", { method: "POST" }).then((x) => x.json());
      setTab("patrol");
      if (r.conversation_id) select(r.conversation_id);
    } finally {
      setPatrolBusy(false);
      void reload();
    }
  }

  async function rename(id: string) {
    const title = renameText.trim();
    setRenaming(null);
    if (!title) return;
    await fetch(`/api/agent/conversations/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }) });
    void reload();
  }

  async function remove(id: string) {
    await fetch(`/api/agent/conversations/${id}`, { method: "DELETE" });
    if (conv === id) select(null);
    void reload();
  }

  return (
    <div className="-mx-2 flex h-[calc(100vh-7rem)] min-h-[520px] overflow-hidden rounded border border-border-card bg-surface-card shadow-card">
      <aside className="flex w-72 shrink-0 flex-col border-r border-border-card">
        <div className="flex gap-2 p-3">
          <button onClick={() => { setTab("chat"); select(null); }}
            className="flex flex-1 items-center justify-center gap-1 rounded bg-primary-container px-3 py-1.5 text-sm font-semibold text-on-primary hover:opacity-90">
            <span className="material-symbols-outlined text-[18px]">add_comment</span>{t("agent.newChat")}
          </button>
          <button onClick={() => openAgentSettings(true)} title={t("agent.settings.title")} aria-label={t("agent.settings.title")}
            className="rounded border border-border-card px-2 text-on-surface-variant hover:bg-surface">
            <span className="material-symbols-outlined text-[18px]">tune</span>
          </button>
        </div>
        <div className="flex border-b border-border-card px-3 text-sm" role="tablist">
          {(["chat", "patrol"] as Tab[]).map((k) => (
            <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
              className={`-mb-px flex-1 border-b-2 py-1.5 ${tab === k ? "border-primary-container font-semibold text-primary-container" : "border-transparent text-on-surface-variant"}`}>
              {t(`agent.tabs.${k}`)}
            </button>
          ))}
        </div>
        {tab === "patrol" && (
          <div className="border-b border-border-card p-3 text-xs text-on-surface-variant">
            <button onClick={runPatrol} disabled={patrolBusy}
              className="flex w-full items-center justify-center gap-1 rounded border border-primary-container px-3 py-1.5 text-sm text-primary-container hover:bg-surface disabled:opacity-60">
              <span className={`material-symbols-outlined text-[18px] ${patrolBusy ? "animate-spin" : ""}`}>{patrolBusy ? "progress_activity" : "radar"}</span>
              {patrolBusy ? t("agent.patrolRunning") : t("agent.patrolNow")}
            </button>
            <p className="mt-2">
              {settings?.patrol.enabled
                ? t("agent.patrolScheduled", { when: settings.patrol.schedule === "weekly"
                  ? `${t(`agent.settings.weekdays.${settings.patrol.weekday}`)} ${settings.patrol.time}`
                  : `${t("agent.settings.daily")} ${settings.patrol.time}` })
                : t("agent.patrolOff")}
            </p>
          </div>
        )}
        <ul className="min-h-0 flex-1 overflow-y-auto py-1">
          {items.length === 0 && <li className="px-4 py-6 text-center text-xs text-outline">{t(`agent.emptyList.${tab}`)}</li>}
          {items.map((c) => (
            <li key={c.id} className={`group relative mx-2 rounded ${conv === c.id ? "bg-primary-container/10" : "hover:bg-surface"}`}>
              {renaming === c.id ? (
                <input autoFocus value={renameText} onChange={(e) => setRenameText(e.target.value)}
                  onBlur={() => void rename(c.id)} onKeyDown={(e) => { if (e.key === "Enter" && !e.nativeEvent.isComposing) void rename(c.id); if (e.key === "Escape") setRenaming(null); }}
                  className="w-full rounded border border-primary-container bg-surface px-2 py-1.5 text-sm" />
              ) : (
                <button onClick={() => select(c.id)} className="block w-full px-3 py-2 text-left">
                  <span className="flex items-center gap-1 text-sm">
                    {c.running && <span className="material-symbols-outlined animate-spin text-[14px] text-primary-container">progress_activity</span>}
                    <span className="truncate">{c.title || t("agent.untitled")}</span>
                  </span>
                  <span className="mt-0.5 flex justify-between text-[11px] text-outline">
                    <span>{rel(c.updated_at)}</span>
                    {c.cost_usd > 0 && <span>{formatUsd(c.cost_usd)}</span>}
                  </span>
                </button>
              )}
              {renaming !== c.id && (
                <span className="absolute right-1 top-1.5 hidden gap-0.5 group-hover:flex">
                  <button onClick={() => { setRenaming(c.id); setRenameText(c.title); }} title={t("agent.rename")} aria-label={t("agent.rename")}
                    className="rounded bg-surface-card p-0.5 text-on-surface-variant hover:text-primary-container">
                    <span className="material-symbols-outlined text-[16px]">edit</span>
                  </button>
                  <button onClick={() => void remove(c.id)} title={t("agent.delete")} aria-label={t("agent.delete")}
                    className="rounded bg-surface-card p-0.5 text-on-surface-variant hover:text-error">
                    <span className="material-symbols-outlined text-[16px]">delete</span>
                  </button>
                </span>
              )}
            </li>
          ))}
        </ul>
        {usage && (
          <div className="border-t border-border-card px-4 py-2.5 text-[11px] text-on-surface-variant">
            <div className="flex justify-between">
              <span>{t("agent.spend30d")}</span>
              <span className="font-mono font-semibold text-on-surface">{formatUsd(usage.cost_usd)}</span>
            </div>
            <div className="mt-0.5 flex justify-between text-outline">
              <span>{t("agent.requests", { n: usage.requests })}</span>
              {usage.cache_hit_rate != null && <span>{t("agent.cacheHit", { pct: Math.round(usage.cache_hit_rate * 100) })}</span>}
            </div>
            <div className="mt-0.5 text-outline">{t("agent.estimated")}</div>
          </div>
        )}
      </aside>
      <section className="min-w-0 flex-1">
        <AgentChat conversationId={conv} onConversationChange={select} pageContext={ctx}
          keyConfigured={!!settings?.key.configured} onOpenSettings={() => openAgentSettings(true)}
          onActivity={() => void reload()} />
      </section>
    </div>
  );
}
