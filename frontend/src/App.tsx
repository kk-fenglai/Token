import { Suspense, lazy, useMemo, useState } from "react";
import { HashRouter, Route, Routes, useLocation } from "react-router-dom";
import { SyncContext } from "./api/useApi";
import Sidebar from "./components/Sidebar";
import TopBar from "./components/TopBar";
import { useI18n } from "./i18n";

// Route-level code splitting: each page (and recharts with it) loads on first
// visit instead of in one 700 kB bundle.
const Dashboard = lazy(() => import("./pages/Dashboard"));
const MonthlyBilling = lazy(() => import("./pages/MonthlyBilling"));
const ProjectCosts = lazy(() => import("./pages/ProjectCosts"));
const ProjectDetail = lazy(() => import("./pages/ProjectDetail"));
const TokenGuide = lazy(() => import("./pages/TokenGuide"));
const UsageLogs = lazy(() => import("./pages/UsageLogs"));
const Sessions = lazy(() => import("./pages/Sessions"));
const SessionDetail = lazy(() => import("./pages/SessionDetail"));
const Insights = lazy(() => import("./pages/Insights"));

const TITLE_KEYS: Record<string, string> = {
  "/": "nav.dashboard",
  "/logs": "nav.logs",
  "/billing": "nav.billing",
  "/projects": "nav.projects",
  "/projects/detail": "nav.projectDetail",
  "/guide": "nav.guide",
  "/sessions": "nav.sessions",
  "/sessions/detail": "nav.sessionDetail",
  "/insights": "nav.insights",
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
          <Suspense fallback={<div className="flex h-48 items-center justify-center text-sm text-on-surface-variant">{t("common.loading")}</div>}>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/logs" element={<UsageLogs />} />
              <Route path="/sessions" element={<Sessions />} />
              <Route path="/sessions/detail" element={<SessionDetail />} />
              <Route path="/insights" element={<Insights />} />
              <Route path="/billing" element={<MonthlyBilling />} />
              <Route path="/projects" element={<ProjectCosts />} />
              <Route path="/projects/detail" element={<ProjectDetail />} />
              <Route path="/guide" element={<TokenGuide />} />
            </Routes>
          </Suspense>
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
