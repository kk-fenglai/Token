import { useLocation } from "react-router-dom";

export interface PageContext {
  route: string;
  query: Record<string, string>;
  title?: string;
}

// What the user is looking at, sent with each assistant message so "this
// project" / "this session" resolve to the path or id in the URL.
export function usePageContext(title?: string): PageContext {
  const location = useLocation();
  const query: Record<string, string> = {};
  new URLSearchParams(location.search).forEach((v, k) => { query[k] = v; });
  return { route: location.pathname, query, title };
}
