import { useMemo, useState } from "react";
import { HashRouter, Route, Routes, useLocation } from "react-router-dom";
import { SyncContext } from "./api/useApi";
import Sidebar from "./components/Sidebar";
import TopBar from "./components/TopBar";
import { useI18n } from "./i18n";
import Dashboard from "./pages/Dashboard";
import MonthlyBilling from "./pages/MonthlyBilling";
import ProjectCosts from "./pages/ProjectCosts";
import ProjectDetail from "./pages/ProjectDetail";
import TokenGuide from "./pages/TokenGuide";
import UsageLogs from "./pages/UsageLogs";

const TITLE_KEYS: Record<string, string> = {
  "/": "nav.dashboard",
  "/logs": "nav.logs",
  "/billing": "nav.billing",
  "/projects": "nav.projects",
  "/projects/detail": "nav.projectDetail",
  "/guide": "nav.guide",
};

function Shell() {
  const location = useLocation();
  const { t } = useI18n();
  const key = TITLE_KEYS[location.pathname];
  return (
    <div className="min-h-screen">
      <Sidebar />
      <div className="ml-[280px]">
        <TopBar title={key ? t(key) : "TokenScope"} />
        <main className="mx-auto max-w-container px-8 py-6">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/logs" element={<UsageLogs />} />
            <Route path="/billing" element={<MonthlyBilling />} />
            <Route path="/projects" element={<ProjectCosts />} />
            <Route path="/projects/detail" element={<ProjectDetail />} />
            <Route path="/guide" element={<TokenGuide />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

export default function App() {
  const [refreshKey, setRefreshKey] = useState(0);
  const ctx = useMemo(
    () => ({ refreshKey, bump: () => setRefreshKey((k) => k + 1) }),
    [refreshKey],
  );
  return (
    <SyncContext.Provider value={ctx}>
      <HashRouter>
        <Shell />
      </HashRouter>
    </SyncContext.Provider>
  );
}
