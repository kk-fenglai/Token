import { Suspense, lazy, useMemo, useState } from "react";
import { HashRouter, Route, Routes, useLocation } from "react-router-dom";
import { SyncContext } from "./api/useApi";
import AgentDock from "./components/agent/AgentDock";
import AnalysisLayout from "./components/AnalysisLayout";
import IdeasLayout from "./components/IdeasLayout";
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
const DevProjects = lazy(() => import("./pages/DevProjects"));
const DevProjectDetail = lazy(() => import("./pages/DevProjectDetail"));
const Agent = lazy(() => import("./pages/Agent"));
const IdeasWeek = lazy(() => import("./pages/IdeasWeek"));
const IdeasSignals = lazy(() => import("./pages/IdeasSignals"));
const IdeasSignalDetail = lazy(() => import("./pages/IdeasSignalDetail"));
const IdeasNeeds = lazy(() => import("./pages/IdeasNeeds"));
const IdeasCard = lazy(() => import("./pages/IdeasCard"));
const IdeasInbox = lazy(() => import("./pages/IdeasInbox"));
const IdeasCompare = lazy(() => import("./pages/IdeasCompare"));
const IdeasSettings = lazy(() => import("./pages/IdeasSettings"));
const IdeasSearch = lazy(() => import("./pages/IdeasSearch"));

const TITLE_KEYS: Record<string, string> = {
  "/": "nav.dashboard",
  "/logs": "nav.analysis",
  "/billing": "nav.billing",
  "/projects": "nav.projects",
  "/projects/detail": "nav.projectDetail",
  "/guide": "nav.guide",
  "/sessions": "nav.analysis",
  "/sessions/detail": "nav.sessionDetail",
  "/insights": "nav.analysis",
  "/dev-projects": "nav.devProjects",
  "/dev-projects/detail": "nav.devProjectDetail",
  "/agent": "nav.agent",
};

function titleKey(pathname: string): string | undefined {
  return TITLE_KEYS[pathname] ?? (pathname.startsWith("/ideas") ? "nav.ideas" : undefined);
}

function Shell() {
  const location = useLocation();
  const { t } = useI18n();
  const key = titleKey(location.pathname);
  return (
    <div className="min-h-screen">
      <Sidebar />
      <div className="ml-[280px]">
        <TopBar title={key ? t(key) : "TokenScope"} />
        <main className="mx-auto max-w-container px-8 py-6">
          <Suspense fallback={<div className="flex h-48 items-center justify-center text-sm text-on-surface-variant">{t("common.loading")}</div>}>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route element={<AnalysisLayout />}>
                <Route path="/logs" element={<UsageLogs />} />
                <Route path="/sessions" element={<Sessions />} />
                <Route path="/insights" element={<Insights />} />
              </Route>
              <Route path="/sessions/detail" element={<SessionDetail />} />
              <Route path="/billing" element={<MonthlyBilling />} />
              <Route path="/projects" element={<ProjectCosts />} />
              <Route path="/projects/detail" element={<ProjectDetail />} />
              <Route path="/guide" element={<TokenGuide />} />
              <Route path="/dev-projects" element={<DevProjects />} />
              <Route path="/dev-projects/detail" element={<DevProjectDetail />} />
              <Route path="/agent" element={<Agent />} />
              <Route element={<IdeasLayout />}>
                <Route path="/ideas" element={<IdeasWeek />} />
                <Route path="/ideas/signals" element={<IdeasSignals />} />
                <Route path="/ideas/signal" element={<IdeasSignalDetail />} />
                <Route path="/ideas/needs" element={<IdeasNeeds />} />
                <Route path="/ideas/card" element={<IdeasCard />} />
                <Route path="/ideas/inbox" element={<IdeasInbox />} />
                <Route path="/ideas/compare" element={<IdeasCompare />} />
                <Route path="/ideas/settings" element={<IdeasSettings />} />
                <Route path="/ideas/search" element={<IdeasSearch />} />
              </Route>
            </Routes>
          </Suspense>
        </main>
        <AgentDock title={key ? t(key) : undefined} />
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
