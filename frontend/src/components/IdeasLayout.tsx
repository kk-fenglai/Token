import { Suspense, useState, type FormEvent } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useI18n } from "../i18n";

/** F30 — the inspiration board's tabs. One sidebar entry; each tab keeps its
 *  own route, and the detail pages (signal, card, search) render inside the
 *  same frame with no tab highlighted. */
export const IDEAS_TABS = [
  { to: "/ideas", icon: "today", label: "本周" },
  { to: "/ideas/signals", icon: "trending_up", label: "付费信号" },
  { to: "/ideas/needs", icon: "lightbulb", label: "需求看板" },
  { to: "/ideas/inbox", icon: "edit_note", label: "生活观察" },
  { to: "/ideas/compare", icon: "compare_arrows", label: "对比" },
  { to: "/ideas/settings", icon: "tune", label: "数据源" },
];

export default function IdeasLayout() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const [q, setQ] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    if (q.trim()) navigate(`/ideas/search?q=${encodeURIComponent(q.trim())}`);
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3 border-b border-border-card">
        <nav className="flex flex-wrap gap-1">
          {IDEAS_TABS.map((tab) => (
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
              {tab.label}
            </NavLink>
          ))}
        </nav>
        <form onSubmit={submit} className="mb-2 flex items-center gap-1 rounded border border-border-card bg-surface-card px-2">
          <span className="material-symbols-outlined text-[18px] text-outline">search</span>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="搜产品、卡片、观察"
            className="w-56 bg-transparent py-1.5 text-sm outline-none" />
        </form>
      </div>
      <Suspense fallback={<div className="flex h-48 items-center justify-center text-sm text-on-surface-variant">{t("common.loading")}</div>}>
        <Outlet />
      </Suspense>
    </div>
  );
}
