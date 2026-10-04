import { NavLink, useLocation } from "react-router-dom";
import { useI18n } from "../i18n";
import { useAgentSettings } from "./agent/agentStore";

const NAV = [
  { to: "/", icon: "dashboard", labelKey: "nav.dashboard", end: true },
  // One entry for the three tabs in AnalysisLayout; it opens the first tab and
  // stays highlighted on any of them (and on a session's detail page).
  { to: "/logs", icon: "query_stats", labelKey: "nav.analysis", end: false, also: ["/sessions", "/insights"] },
  { to: "/billing", icon: "calendar_month", labelKey: "nav.billing", end: false },
  { to: "/projects", icon: "paid", labelKey: "nav.projects", end: false },
  { to: "/dev-projects", icon: "folder_code", labelKey: "nav.devProjects", end: false },
  { to: "/agent", icon: "smart_toy", labelKey: "nav.agent", end: false },
  { to: "/guide", icon: "school", labelKey: "nav.guide", end: false },
];

export default function Sidebar() {
  const { t } = useI18n();
  const { pathname } = useLocation();
  // With the assistant configured, questions and tool results go to DeepSeek,
  // so "data never leaves this machine" would no longer be true.
  const agentOn = !!useAgentSettings()?.key.configured;
  return (
    <aside className="fixed inset-y-0 left-0 flex w-[280px] flex-col border-r border-border-card bg-surface-card">
      <div className="px-6 pb-4 pt-6">
        <h1 className="text-[22px] font-bold text-primary-container">TokenScope</h1>
        <p className="mt-0.5 text-sm text-on-surface-variant">{t("nav.tagline")}</p>
      </div>
      <nav className="mt-2 flex flex-col gap-1 px-4">
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded px-4 py-2.5 text-[15px] font-medium transition-colors ${
                isActive || item.also?.some((p) => pathname === p || pathname.startsWith(`${p}/`))
                  ? "bg-primary-container text-on-primary"
                  : "text-on-surface-variant hover:bg-surface"
              }`
            }
          >
            <span className="material-symbols-outlined">{item.icon}</span>
            {t(item.labelKey)}
          </NavLink>
        ))}
      </nav>
      <div className="mt-auto border-t border-border-card px-6 py-4 text-xs text-outline">
        {agentOn ? t("nav.footerAgent") : t("nav.footer")}
      </div>
    </aside>
  );
}
