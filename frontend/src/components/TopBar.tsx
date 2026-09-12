import { useContext, useState } from "react";
import { SyncContext } from "../api/useApi";
import { useI18n } from "../i18n";
import { formatRelative } from "../lib/format";
import CurrencySwitcher from "./CurrencySwitcher";
import LocaleSwitcher from "./LocaleSwitcher";
import ScopeSelector from "./ScopeSelector";

export default function TopBar({ title }: { title: string }) {
  const { bump } = useContext(SyncContext);
  const { t, tag } = useI18n();
  const [syncing, setSyncing] = useState(false);
  const [lastSync, setLastSync] = useState<string | null>(null);

  async function syncNow() {
    if (syncing) return;
    setSyncing(true);
    try {
      const res = await fetch("/api/sync", { method: "POST" });
      const json = await res.json();
      if (json.last_sync_at) setLastSync(json.last_sync_at);
      bump();
    } catch {
      /* surfaced by panels re-fetching */
    } finally {
      setSyncing(false);
    }
  }

  return (
    <header className="sticky top-0 z-10 flex h-16 items-center justify-between border-b border-border-card bg-surface-card px-8">
      <h2 className="text-xl font-semibold">{title}</h2>
      <div className="flex items-center gap-4">
        {lastSync && (
          <span className="text-xs text-on-surface-variant">
            {t("common.lastSync", {
              time: formatRelative(lastSync, tag, {
                never: t("common.never"), justNow: t("common.justNow"),
              }),
            })}
          </span>
        )}
        <ScopeSelector />
        <CurrencySwitcher />
        <LocaleSwitcher />
        <button
          onClick={syncNow}
          disabled={syncing}
          className="flex items-center gap-2 rounded bg-primary-container px-4 py-2 text-sm font-semibold text-on-primary transition-opacity hover:opacity-90 disabled:opacity-60"
        >
          <span className={`material-symbols-outlined ${syncing ? "animate-spin" : ""}`}>
            sync
          </span>
          {syncing ? t("common.syncing") : t("common.syncNow")}
        </button>
      </div>
    </header>
  );
}
