import { Fragment, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { RangeKey, SessionItem, SessionsResponse } from "../api/types";
import { useScope } from "../api/scope";
import { useApi } from "../api/useApi";
import TimeRangeSelector from "../components/TimeRangeSelector";
import { useI18n } from "../i18n";
import { useMoney } from "../lib/currency";
import { formatDuration, formatLocalTime, formatTokens, modelLabel } from "../lib/format";

const PAGE_SIZE = 50;

export default function Sessions() {
  const { t } = useI18n();
  const { money } = useMoney();
  const { project, ready } = useScope();
  const navigate = useNavigate();
  const [range, setRange] = useState<RangeKey>("7d");
  const [sort, setSort] = useState<"start" | "cost">("start");
  const [q, setQ] = useState("");
  const [qInput, setQInput] = useState("");
  const [page, setPage] = useState(1);

  const params = useMemo(() => {
    const p = new URLSearchParams({ range, sort, page: String(page), page_size: String(PAGE_SIZE) });
    if (project) p.set("project", project);
    if (q) p.set("q", q);
    return p;
  }, [range, sort, page, project, q]);
  const data = useApi<SessionsResponse>(ready ? `/api/sessions?${params.toString()}` : null);
  const totalPages = data.data ? Math.max(1, Math.ceil(data.data.total / PAGE_SIZE)) : 1;

  function reset(fn: () => void) { setPage(1); fn(); }

  // Newest-first lists read better with a day divider; cost order does not.
  const rows: (SessionItem | { dayHeader: string; n: number; cost: number })[] = [];
  if (data.data) {
    let day = "";
    for (const s of data.data.items) {
      if (sort === "start" && s.day !== day) {
        day = s.day;
        const same = data.data.items.filter((x) => x.day === day);
        rows.push({ dayHeader: day, n: same.length, cost: same.reduce((a, x) => a + x.cost, 0) });
      }
      rows.push(s);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-2xl font-bold">{t("sessions.title")}</h3>
          <p className="mt-1 text-sm text-on-surface-variant">{t("sessions.subtitle")}</p>
        </div>
        <TimeRangeSelector value={range} onChange={(r) => reset(() => setRange(r))} />
      </div>

      <div className="flex flex-wrap items-end gap-4 rounded border border-border-card bg-surface-card p-4 shadow-card">
        <label className="flex flex-col gap-1 text-xs font-semibold text-on-surface-variant">
          {t("logs.search")}
          <input value={qInput} onChange={(e) => setQInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && reset(() => setQ(qInput))}
            onBlur={() => reset(() => setQ(qInput))}
            placeholder={t("sessions.searchPlaceholder")}
            className="h-9 w-64 rounded border border-outline-variant px-3 text-sm font-normal text-on-surface focus:border-primary-container focus:outline-none" />
        </label>
        <div className="flex flex-col gap-1 text-xs font-semibold text-on-surface-variant">
          {t("sessions.sortLabel")}
          <div className="inline-flex rounded border border-border-card p-0.5 text-sm font-normal">
            {(["start", "cost"] as const).map((s) => (
              <button key={s} onClick={() => reset(() => setSort(s))}
                className={`rounded px-3 py-1 ${sort === s ? "bg-primary-container font-semibold text-on-primary" : "text-on-surface-variant hover:bg-surface"}`}>
                {t(`sessions.sort.${s}`)}
              </button>
            ))}
          </div>
        </div>
        {data.data && (
          <span className="ml-auto self-center text-sm text-on-surface-variant">
            {t("sessions.summary", { n: data.data.totals.sessions, cost: money(data.data.totals.cost), msgs: data.data.totals.messages.toLocaleString() })}
          </span>
        )}
      </div>

      <div className="overflow-hidden rounded border border-border-card bg-surface-card shadow-card">
        {data.error ? (
          <div className="flex h-48 flex-col items-center justify-center gap-3 text-sm text-on-surface-variant">
            <span>{t("common.loadFailed", { error: data.error })}</span>
            <button onClick={data.retry} className="rounded border border-primary-container px-3 py-1.5 text-primary-container">{t("common.retry")}</button>
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[900px] text-sm">
                <thead>
                  <tr className="border-b border-border-card bg-surface text-left text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
                    <th className="px-4 py-3">{t("sessions.colProject")}</th>
                    <th className="px-4 py-3">{t("sessions.colStart")}</th>
                    <th className="px-4 py-3 text-right">{t("sessions.colDuration")}</th>
                    <th className="px-4 py-3 text-right">{t("sessions.colMessages")}</th>
                    <th className="px-4 py-3">{t("sessions.colModels")}</th>
                    <th className="px-4 py-3 text-right">{t("sessions.colTools")}</th>
                    <th className="px-4 py-3 text-right">{t("sessions.colPeakCtx")}</th>
                    <th className="px-4 py-3 text-right">{t("sessions.colCost")}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.loading && !data.data ? (
                    <tr><td colSpan={8} className="px-4 py-12 text-center text-on-surface-variant">{t("common.loading")}</td></tr>
                  ) : rows.length === 0 ? (
                    <tr><td colSpan={8} className="px-4 py-12 text-center text-on-surface-variant">{t("sessions.empty")}</td></tr>
                  ) : rows.map((r) =>
                    "dayHeader" in r ? (
                      <tr key={`d-${r.dayHeader}`} className="bg-surface/70">
                        <td colSpan={8} className="px-4 py-1.5 text-xs font-semibold text-on-surface-variant">
                          {t("sessions.dayHeader", { day: r.dayHeader, n: r.n, cost: money(r.cost) })}
                        </td>
                      </tr>
                    ) : (
                      <Fragment key={r.session_id}>
                        <tr
                          onClick={() => navigate(`/sessions/detail?id=${encodeURIComponent(r.session_id)}`)}
                          className="cursor-pointer border-b border-border-card/60 last:border-0 hover:bg-surface/60"
                        >
                          <td className="max-w-56 px-4 py-2.5">
                            <div className="truncate font-medium" title={r.project_path}>{r.name}</div>
                            <div className="truncate font-mono text-[11px] text-outline" title={r.session_id}>{r.session_id.slice(0, 8)}</div>
                          </td>
                          <td className="px-4 py-2.5 font-mono text-xs">{formatLocalTime(r.first_ts)}</td>
                          <td className="px-4 py-2.5 text-right font-mono text-xs">{formatDuration(r.duration_s)}</td>
                          <td className="px-4 py-2.5 text-right font-mono text-xs">{r.messages.toLocaleString()}</td>
                          <td className="px-4 py-2.5 text-xs">{r.models.map(modelLabel).join(", ")}</td>
                          <td className="px-4 py-2.5 text-right font-mono text-xs">{r.tool_calls.toLocaleString()}</td>
                          <td className={`px-4 py-2.5 text-right font-mono text-xs ${r.ctx_max >= 150_000 ? "font-semibold text-error" : ""}`}>{formatTokens(r.ctx_max)}</td>
                          <td className="px-4 py-2.5 text-right font-mono text-xs font-semibold">
                            {money(r.cost)}
                            {r.subagent_cost > 0 && (
                              <div className="text-[11px] font-normal text-outline">
                                {t("sessions.subagentTag", { pct: r.cost ? ((r.subagent_cost / r.cost) * 100).toFixed(0) : 0 })}
                              </div>
                            )}
                          </td>
                        </tr>
                      </Fragment>
                    ),
                  )}
                </tbody>
              </table>
            </div>
            <div className="flex items-center justify-between border-t border-border-card px-4 py-3 text-sm text-on-surface-variant">
              <span>
                {data.data ? t("logs.summary", {
                  total: data.data.total.toLocaleString(),
                  from: Math.min((page - 1) * PAGE_SIZE + 1, data.data.total),
                  to: Math.min(page * PAGE_SIZE, data.data.total),
                }) : ""}
              </span>
              <div className="flex items-center gap-1">
                <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="rounded px-2 py-1 hover:bg-surface disabled:opacity-40">‹</button>
                <span className="rounded bg-primary-container px-2.5 py-1 text-on-primary">{page}</span>
                <span className="px-1">/ {totalPages}</span>
                <button disabled={page >= totalPages} onClick={() => setPage(page + 1)} className="rounded px-2 py-1 hover:bg-surface disabled:opacity-40">›</button>
              </div>
            </div>
          </>
        )}
      </div>
      <p className="text-xs text-outline">
        {t("sessions.footnote")}{" "}
        <Link to="/insights" className="text-primary-container hover:underline">{t("nav.insights")}</Link>
      </p>
    </div>
  );
}
