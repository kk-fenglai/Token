import { Suspense } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useI18n } from "../i18n";

/** The three usage-analysis views share one sidebar entry; this tab bar
 *  switches between them. Each keeps its own route so existing deep links
 *  (`/logs?model=…`, alert links, the guide) still land on the right tab. */
export const ANALYSIS_TABS = [
  { to: "/logs", icon: "receipt_long", labelKey: "nav.logs" },
  { to: "/sessions", icon: "forum", labelKey: "nav.sessions" },
  { to: "/insights", icon: "insights", labelKey: "nav.insights" },
];

export default function AnalysisLayout() {
  const { t } = useI18n();
  return (
    <div className="space-y-6">
      <nav className="flex gap-1 border-b border-border-card">
        {ANALYSIS_TABS.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            end
            className={({ isActive }) =>
              `-mb-px flex items-center gap-2 border-b-2 px-4 py-2.5 text-[15px] font-medium transition-colors ${
                isActive
                  ? "border-primary-container text-primary-container"
                  : "border-transparent text-on-surface-variant hover:text-on-surface"
              }`
            }
          >
            <span className="material-symbols-outlined text-[20px]">{tab.icon}</span>
            {t(tab.labelKey)}
          </NavLink>
        ))}
      </nav>
      {/* Own boundary so the tab bar stays put while a lazy tab loads. */}
      <Suspense fallback={<div className="flex h-48 items-center justify-center text-sm text-on-surface-variant">{t("common.loading")}</div>}>
        <Outlet />
      </Suspense>
    </div>
  );
}
