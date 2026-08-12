import {
  createContext, useCallback, useContext, useEffect, useMemo, useState,
  type ReactNode,
} from "react";

export interface ScopeInfo {
  project: string;
  name: string;
  cwds: string[];
  events: number;
  known: boolean;
}

interface Ctx {
  /** Folded project key the dashboard is pinned to, or null for account-wide. */
  project: string | null;
  info: ScopeInfo | null;
  setProject: (p: string | null, info?: ScopeInfo | null) => void;
  /** Appends `project=…` to a path, preserving any existing query string. */
  withScope: (path: string) => string;
  ready: boolean;
}

const ScopeContext = createContext<Ctx | null>(null);
const STORAGE_KEY = "tokenscope.scope";

export function ScopeProvider({ children }: { children: ReactNode }) {
  const [project, setProjectState] = useState<string | null>(null);
  const [info, setInfo] = useState<ScopeInfo | null>(null);
  const [ready, setReady] = useState(false);

  // The server's --project flag wins on first load: launching from inside a
  // repo should show that repo, whatever was last picked in the UI.
  useEffect(() => {
    let cancelled = false;
    fetch("/api/scope")
      .then((r) => r.json())
      .then((d: { default_project: string | null; scope: ScopeInfo | null }) => {
        if (cancelled) return;
        if (d.default_project) {
          setProjectState(d.default_project);
          setInfo(d.scope);
        } else {
          const saved = localStorage.getItem(STORAGE_KEY);
          if (saved) setProjectState(saved);
        }
      })
      .catch(() => { /* account-wide is a safe default */ })
      .finally(() => { if (!cancelled) setReady(true); });
    return () => { cancelled = true; };
  }, []);

  const setProject = useCallback((p: string | null, i?: ScopeInfo | null) => {
    setProjectState(p);
    setInfo(i ?? null);
    if (p) localStorage.setItem(STORAGE_KEY, p);
    else localStorage.removeItem(STORAGE_KEY);
  }, []);

  const withScope = useCallback((path: string) => {
    if (!project) return path;
    return `${path}${path.includes("?") ? "&" : "?"}project=${encodeURIComponent(project)}`;
  }, [project]);

  const value = useMemo<Ctx>(
    () => ({ project, info, setProject, withScope, ready }),
    [project, info, setProject, withScope, ready],
  );

  return <ScopeContext.Provider value={value}>{children}</ScopeContext.Provider>;
}

export function useScope(): Ctx {
  const ctx = useContext(ScopeContext);
  if (!ctx) throw new Error("useScope must be used inside <ScopeProvider>");
  return ctx;
}
