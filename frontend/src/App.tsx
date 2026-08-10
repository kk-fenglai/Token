import { useMemo, useState } from "react";
import { HashRouter, Route, Routes, useLocation } from "react-router-dom";
import { SyncContext } from "./api/useApi";
import Sidebar from "./components/Sidebar";
import TopBar from "./components/TopBar";
import Dashboard from "./pages/Dashboard";
import ProjectCosts from "./pages/ProjectCosts";
import ProjectDetail from "./pages/ProjectDetail";
import UsageLogs from "./pages/UsageLogs";

const TITLES: Record<string, string> = {
  "/": "Dashboard",
  "/logs": "Usage Logs",
  "/projects": "Project Costs",
  "/projects/detail": "Project Detail",
};

function Shell() {
  const location = useLocation();
  const title = TITLES[location.pathname] ?? "TokenScope";
  return (
    <div className="min-h-screen">
      <Sidebar />
      <div className="ml-[280px]">
        <TopBar title={title} />
        <main className="mx-auto max-w-container px-8 py-6">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/logs" element={<UsageLogs />} />
            <Route path="/projects" element={<ProjectCosts />} />
            <Route path="/projects/detail" element={<ProjectDetail />} />
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
