import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import type { LogsResponse, ModelsResponse } from "../api/types";
import { useScope } from "../api/scope";
import { useApi } from "../api/useApi";
import { useI18n } from "../i18n";
import { FAMILY_KEYS, formatLocalTime, formatTokens, modelLabel } from "../lib/format";

const PAGE_SIZE = 50;

function isoDaysAgo(days: number): string {
  const d = new Date(Date.now() - days * 86400_000);
  return d.toISOString().slice(0, 10);
}

const DATE_PRESETS = [
  { key: "", labelKey: "range.allTime" },
  { key: "7", labelKey: "range.7d" },
  { key: "30", labelKey: "range.30d" },
];

export default function UsageLogs() {
  const { t } = useI18n();
  const { project } = useScope();
  const [sp] = useSearchParams();
  const [q, setQ] = useState("");
  const [qInput, setQInput] = useState("");
  // Arriving from a model row in the dashboard: no date bound, so the filtered
  // model's full history is visible rather than an empty last-7-days view.
  const linkedModel = sp.get("model") ?? "";
  const [preset, setPreset] = useState(linkedModel ? "" : "7");
  const [family, setFamily] = useState("");
  const [model, setModel] = useState(linkedModel);
  const [page, setPage] = useState(1);

  const catalog = useApi<ModelsResponse>("/api/models?range=all");

  const params = useMemo(() => {
    const p = new URLSearchParams();
    if (preset) p.set("from", isoDaysAgo(Number(preset) - 1));
    if (family) p.set("model_family", family);
    if (model) p.set("model", model);
    if (project) p.set("project", project);
    if (q) p.set("q", q);
    p.set("page", String(page));
    p.set("page_size", String(PAGE_SIZE));
    return p;
  }, [q, preset, family, model, project, page]);

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
          <h3 className="text-2xl font-bold">{t("logs.title")}</h3>
          <p className="mt-1 text-sm text-on-surface-variant">{t("logs.subtitle")}</p>
        </div>
        <a
          href={`/api/logs/export.csv?${exportParams.toString()}`}
          className="flex items-center gap-2 rounded border border-primary-container px-4 py-2 text-sm font-semibold text-primary-container hover:bg-surface"
        >
          <span className="material-symbols-outlined">download</span>
          {t("logs.export")}
        </a>
      </div>

      {/* 筛选栏 */}
      <div className="flex flex-wrap items-end gap-4 rounded border border-border-card bg-surface-card p-4 shadow-card">
        <label className="flex flex-col gap-1 text-xs font-semibold text-on-surface-variant">
          {t("logs.search")}
          <input
            value={qInput}
            onChange={(e) => setQInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && resetPageAnd(() => setQ(qInput))}
            onBlur={() => resetPageAnd(() => setQ(qInput))}
            placeholder={t("logs.searchPlaceholder")}
            className="h-9 w-64 rounded border border-outline-variant px-3 text-sm font-normal text-on-surface focus:border-primary-container focus:outline-none focus:ring-2 focus:ring-primary-container/20"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs font-semibold text-on-surface-variant">
          {t("logs.dateRange")}
          <select
            value={preset}
            onChange={(e) => resetPageAnd(() => setPreset(e.target.value))}
            className="h-9 rounded border border-outline-variant bg-surface-card px-3 text-sm font-normal"
          >
            {DATE_PRESETS.map((p) => (
              <option key={p.key} value={p.key}>{t(p.labelKey)}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs font-semibold text-on-surface-variant">
          {t("logs.family")}
          <select
            value={family}
            onChange={(e) => resetPageAnd(() => setFamily(e.target.value))}
            className="h-9 rounded border border-outline-variant bg-surface-card px-3 text-sm font-normal"
          >
            <option value="">{t("logs.allFamilies")}</option>
            {FAMILY_KEYS.map((k) => (
              <option key={k} value={k}>{t(`family.${k}`)}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs font-semibold text-on-surface-variant">
          {t("logs.model")}
          <select
            value={model}
            onChange={(e) => resetPageAnd(() => setModel(e.target.value))}
            className="h-9 rounded border border-outline-variant bg-surface-card px-3 text-sm font-normal"
          >
            <option value="">{t("logs.allModels")}</option>
            {catalog.data?.models
              .filter((m) => !family || m.family === family)
              .map((m) => (
                <option key={m.model} value={m.model}>
                  {t("logs.modelOption", { name: modelLabel(m.model), n: m.events.toLocaleString() })}
                </option>
              ))}
          </select>
        </label>
        <button
          onClick={() => resetPageAnd(() => { setQ(""); setQInput(""); setPreset(""); setFamily(""); setModel(""); })}
          className="h-9 text-sm text-on-surface-variant underline hover:text-on-surface"
        >
          {t("logs.clear")}
        </button>
      </div>

      {/* 明细表 */}
      <div className="overflow-hidden rounded border border-border-card bg-surface-card shadow-card">
        {logs.error ? (
          <div className="flex h-48 flex-col items-center justify-center gap-3 text-sm text-on-surface-variant">
            <span>{t("common.loadFailed", { error: logs.error })}</span>
            <button onClick={logs.retry} className="rounded border border-primary-container px-3 py-1.5 text-primary-container">{t("common.retry")}</button>
          </div>
        ) : (
          <>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border-card bg-surface text-left text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
                  <th className="px-4 py-3">{t("logs.colTime")}</th>
                  <th className="px-4 py-3">{t("logs.colModel")}</th>
                  <th className="px-4 py-3">{t("logs.colProject")}</th>
                  <th className="px-4 py-3 text-right">{t("logs.colTokens")}</th>
                  <th className="px-4 py-3 text-right">{t("logs.colCost")}</th>
                </tr>
              </thead>
              <tbody>
                {logs.loading && !logs.data ? (
                  <tr><td colSpan={5} className="px-4 py-12 text-center text-on-surface-variant">{t("common.loading")}</td></tr>
                ) : logs.data?.items.length === 0 ? (
                  <tr><td colSpan={5} className="px-4 py-12 text-center text-on-surface-variant">{t("logs.noMatch")}</td></tr>
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
                  ? t("logs.summary", {
                      total: logs.data.total.toLocaleString(),
                      from: (page - 1) * PAGE_SIZE + 1,
                      to: Math.min(page * PAGE_SIZE, logs.data.total),
                    })
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
