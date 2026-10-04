import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Link, useLocation } from "react-router-dom";
import { useI18n } from "../../i18n";
import { usePageContext } from "../../lib/pageContext";
import AgentChat from "./AgentChat";
import AgentSettingsDialog from "./AgentSettingsDialog";
import { openAgentSettings, useAgentSettings, useAgentSettingsOpen } from "./agentStore";

const CONV_KEY = "tokenscope.agent.drawerConversation";

function readConv(): string | null {
  try { return localStorage.getItem(CONV_KEY); } catch { return null; }
}
function writeConv(id: string | null) {
  try { if (id) localStorage.setItem(CONV_KEY, id); else localStorage.removeItem(CONV_KEY); } catch { /* storage blocked */ }
}

// Suggestions that use what the user is looking at.
function contextualPrompts(route: string, t: (k: string) => string): string[] | undefined {
  if (route === "/dev-projects/detail") return [t("agent.suggest.devThis"), t("agent.suggest.devDescribe"), t("agent.suggest.devUpload")];
  if (route === "/dev-projects") return [t("agent.suggest.push"), t("agent.suggest.devStale")];
  if (route === "/sessions/detail") return [t("agent.suggest.sessionWhy"), t("agent.suggest.sessionClear")];
  if (route === "/projects/detail") return [t("agent.suggest.projectMonth"), t("agent.suggest.projectSave")];
  return undefined;
}

// Floating button + right-hand drawer on every page except /agent, plus the
// settings dialog (mounted once for the whole app).
export default function AgentDock({ title }: { title?: string }) {
  const { t } = useI18n();
  const location = useLocation();
  const settings = useAgentSettings();
  const settingsOpen = useAgentSettingsOpen();
  const ctx = usePageContext(title);
  const [open, setOpen] = useState(false);
  const [conv, setConv] = useState<string | null>(readConv);
  const onAgentPage = location.pathname === "/agent";

  useEffect(() => { writeConv(conv); }, [conv]);
  useEffect(() => { if (onAgentPage) setOpen(false); }, [onAgentPage]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape" && !settingsOpen) setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, settingsOpen]);

  return (
    <>
      {!onAgentPage && !open && (
        <button onClick={() => setOpen(true)} title={t("agent.open")} aria-label={t("agent.open")}
          className="fixed bottom-6 right-6 z-40 flex h-14 w-14 items-center justify-center rounded-full bg-primary-container text-on-primary shadow-lg transition-transform hover:scale-105">
          <span className="material-symbols-outlined text-[28px]">smart_toy</span>
        </button>
      )}
      {open && !onAgentPage && createPortal(
        <aside role="dialog" aria-label={t("agent.title")}
          className="fixed inset-y-0 right-0 z-50 flex w-[440px] max-w-full flex-col border-l border-border-card bg-surface-card shadow-2xl">
          <div className="flex items-center gap-1 border-b border-border-card px-4 py-2.5">
            <span className="material-symbols-outlined text-[20px] text-primary-container">smart_toy</span>
            <h3 className="mr-auto text-sm font-semibold">{t("agent.title")}</h3>
            <IconBtn icon="add_comment" label={t("agent.newChat")} onClick={() => setConv(null)} />
            <Link to={conv ? `/agent?c=${conv}` : "/agent"} title={t("agent.openFull")} aria-label={t("agent.openFull")}
              className="rounded p-1.5 text-on-surface-variant hover:bg-surface">
              <span className="material-symbols-outlined text-[18px]">open_in_full</span>
            </Link>
            <IconBtn icon="tune" label={t("agent.settings.title")} onClick={() => openAgentSettings(true)} />
            <IconBtn icon="close" label={t("devProjects.publish.close")} onClick={() => setOpen(false)} />
          </div>
          {ctx.query.path || ctx.query.id ? (
            <div className="truncate border-b border-border-card bg-surface px-4 py-1 text-[11px] text-outline" title={ctx.query.path || ctx.query.id}>
              {t("agent.contextHint", { page: title ?? ctx.route })} · <span className="font-mono">{ctx.query.path || ctx.query.id}</span>
            </div>
          ) : null}
          <div className="min-h-0 flex-1">
            <AgentChat compact conversationId={conv} onConversationChange={setConv} pageContext={ctx}
              keyConfigured={!!settings?.key.configured} onOpenSettings={() => openAgentSettings(true)}
              suggestions={contextualPrompts(ctx.route, t)} />
          </div>
        </aside>,
        document.body,
      )}
      {settingsOpen && <AgentSettingsDialog />}
    </>
  );
}

function IconBtn({ icon, label, onClick }: { icon: string; label: string; onClick: () => void }) {
  return (
    <button onClick={onClick} title={label} aria-label={label} className="rounded p-1.5 text-on-surface-variant hover:bg-surface">
      <span className="material-symbols-outlined text-[18px]">{icon}</span>
    </button>
  );
}
