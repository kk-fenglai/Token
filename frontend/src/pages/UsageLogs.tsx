import { useMemo, useState } from "react";
import type { LogsResponse } from "../api/types";
import { useApi } from "../api/useApi";
import { FAMILY_LABELS, formatLocalTime, formatTokens } from "../lib/format";

const PAGE_SIZE = 50;

function isoDaysAgo(days: number): string {
  const d = new Date(Date.now() - days * 86400_000);
  return d.toISOString().slice(0, 10);
}

const DATE_PRESETS = [
  { key: "", label: "全部时间" },
  { key: "7", label: "近 7 天" },
  { key: "30", label: "近 30 天" },
];

export default function UsageLogs() {
  const [q, setQ] = useState("");
  const [qInput, setQInput] = useState("");
  const [preset, setPreset] = useState("7");
  const [family, setFamily] = useState("");
  const [page, setPage] = useState(1);

  const params = useMemo(() => {
    const sp = new URLSearchParams();
    if (preset) sp.set("from", isoDaysAgo(Number(preset) - 1));
    if (family) sp.set("model_family", family);
    if (q) sp.set("q", q);
    sp.set("page", String(page));
    sp.set("page_size", String(PAGE_SIZE));
    return sp;
  }, [q, preset, family, page]);

  const logs = useApi<LogsResponse>(`/api/logs?${params.toString()}`);
  const totalPages = logs.data ? Math.max(1, Math.ceil(logs.data.total / PAGE_SIZE)) : 1;

  const exportParams = new URLSearchParams(params);
  exportParams.delete("page");
  exportParams.delete("page_size");

  function resetPageAnd(fn: () => void) {
    setPage(1);
    fn();
  }

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-2xl font-bold">Usage Logs</h3>
          <p className="mt-1 text-sm text-on-surface-variant">每条 assistant 消息的 token 明细记录</p>
        </div>
        <a
          href={`/api/logs/export.csv?${exportParams.toString()}`}
          className="flex items-center gap-2 rounded border border-primary-container px-4 py-2 text-sm font-semibold text-primary-container hover:bg-surface"
        >
          <span className="material-symbols-outlined">download</span>
          Export CSV
        </a>
      </div>

      {/* 筛选栏 */}
      <div className="flex flex-wrap items-end gap-4 rounded border border-border-card bg-surface-card p-4 shadow-card">
        <label className="flex flex-col gap-1 text-xs font-semibold text-on-surface-variant">
          搜索
          <input
            value={qInput}
            onChange={(e) => setQInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && resetPageAnd(() => setQ(qInput))}
            onBlur={() => resetPageAnd(() => setQ(qInput))}
            placeholder="项目名 / Session ID / Message ID…"
            className="h-9 w-64 rounded border border-outline-variant px-3 text-sm font-normal text-on-surface focus:border-primary-container focus:outline-none focus:ring-2 focus:ring-primary-container/20"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs font-semibold text-on-surface-variant">
          日期范围
          <select
            value={preset}
            onChange={(e) => resetPageAnd(() => setPreset(e.target.value))}
            className="h-9 rounded border border-outline-variant bg-surface-card px-3 text-sm font-normal"
          >
            {DATE_PRESETS.map((p) => (
              <option key={p.key} value={p.key}>{p.label}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs font-semibold text-on-surface-variant">
          模型筛选
          <select
            value={family}
            onChange={(e) => resetPageAnd(() => setFamily(e.target.value))}
            className="h-9 rounded border border-outline-variant bg-surface-card px-3 text-sm font-normal"
          >
            <option value="">All Models</option>
            {Object.entries(FAMILY_LABELS).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </label>
        <button
          onClick={() => resetPageAnd(() => { setQ(""); setQInput(""); setPreset(""); setFamily(""); })}
          className="h-9 text-sm text-on-surface-variant underline hover:text-on-surface"
        >
          Clear Filters
        </button>
      </div>

      {/* 明细表 */}
      <div className="overflow-hidden rounded border border-border-card bg-surface-card shadow-card">
        {logs.error ? (
          <div className="flex h-48 flex-col items-center justify-center gap-3 text-sm text-on-surface-variant">
            <span>加载失败:{logs.error}</span>
            <button onClick={logs.retry} className="rounded border border-primary-container px-3 py-1.5 text-primary-container">重试</button>
          </div>
        ) : (
          <>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border-card bg-surface text-left text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
                  <th className="px-4 py-3">时间(本地)</th>
                  <th className="px-4 py-3">模型</th>
                  <th className="px-4 py-3">项目</th>
                  <th className="px-4 py-3 text-right">Tokens (In / Out / Cache W / Cache R)</th>
                  <th className="px-4 py-3 text-right">虚拟成本</th>
                </tr>
              </thead>
              <tbody>
                {logs.loading && !logs.data ? (
                  <tr><td colSpan={5} className="px-4 py-12 text-center text-on-surface-variant">加载中…</td></tr>
                ) : logs.data?.items.length === 0 ? (
                  <tr><td colSpan={5} className="px-4 py-12 text-center text-on-surface-variant">没有匹配的记录</td></tr>
                ) : (
                  logs.data?.items.map((it, i) => (
                    <tr key={`${it.ts}-${i}`} className="border-b border-border-card/60 last:border-0 hover:bg-surface/60">
                      <td className="px-4 py-2.5 font-mono text-xs">{formatLocalTime(it.ts)}</td>
                      <td className="px-4 py-2.5 font-mono text-xs">{it.model}</td>
                      <td className="max-w-56 truncate px-4 py-2.5" title={it.project_path}>{it.project_name}</td>
                      <td className="px-4 py-2.5 text-right font-mono text-xs">
                        {formatTokens(it.input)} / {formatTokens(it.output)} /{" "}
                        <span className="text-chart-cache-write">{formatTokens(it.cache_write)}</span> /{" "}
                        <span className="text-primary-container">{formatTokens(it.cache_read)}</span>
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono text-xs">${it.cost.toFixed(4)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
            <div className="flex items-center justify-between border-t border-border-card px-4 py-3 text-sm text-on-surface-variant">
              <span>
                {logs.data
                  ? `共 ${logs.data.total.toLocaleString()} 条 · 第 ${(page - 1) * PAGE_SIZE + 1}–${Math.min(page * PAGE_SIZE, logs.data.total)} 条`
                  : ""}
              </span>
              <div className="flex items-center gap-1">
                <button disabled={page <= 1} onClick={() => setPage(page - 1)}
                  className="rounded px-2 py-1 hover:bg-surface disabled:opacity-40">‹</button>
                <span className="rounded bg-primary-container px-2.5 py-1 text-on-primary">{page}</span>
                <span className="px-1">/ {totalPages}</span>
                <button disabled={page >= totalPages} onClick={() => setPage(page + 1)}
                  className="rounded px-2 py-1 hover:bg-surface disabled:opacity-40">›</button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
