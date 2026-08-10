import { NavLink } from "react-router-dom";

const NAV = [
  { to: "/", icon: "dashboard", label: "Dashboard", end: true },
  { to: "/logs", icon: "receipt_long", label: "Usage Logs", end: false },
  { to: "/projects", icon: "paid", label: "Project Costs", end: false },
];

export default function Sidebar() {
  return (
    <aside className="fixed inset-y-0 left-0 flex w-[280px] flex-col border-r border-border-card bg-surface-card">
      <div className="px-6 pb-4 pt-6">
        <h1 className="text-[22px] font-bold text-primary-container">TokenScope</h1>
        <p className="mt-0.5 text-sm text-on-surface-variant">个人 Token 消耗仪表盘</p>
      </div>
      <nav className="mt-2 flex flex-col gap-1 px-4">
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded px-4 py-2.5 text-[15px] font-medium transition-colors ${
                isActive
                  ? "bg-primary-container text-on-primary"
                  : "text-on-surface-variant hover:bg-surface"
              }`
            }
          >
            <span className="material-symbols-outlined">{item.icon}</span>
            {item.label}
          </NavLink>
        ))}
      </nav>
      <div className="mt-auto border-t border-border-card px-6 py-4 text-xs text-outline">
        本地运行 · 数据不出本机
      </div>
    </aside>
  );
}
