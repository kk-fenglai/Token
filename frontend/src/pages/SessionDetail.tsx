import { Link, useSearchParams } from "react-router-dom";
import type { SessionDetailResponse } from "../api/types";
import { useApi } from "../api/useApi";
import ContextChart from "../charts/ContextChart";
import ChartCard from "../components/ChartCard";
import StatCard from "../components/StatCard";
import ToolsTable from "../components/ToolsTable";
import { useI18n } from "../i18n";
import { useMoney } from "../lib/currency";
import { formatDuration, formatLocalTime, formatTokens, modelLabel } from "../lib/format";

export default function SessionDetail() {
  const { t } = useI18n();
  const { money, precise } = useMoney();
  const [sp] = useSearchParams();
  const id = sp.get("id") ?? "";
  const detail = useApi<SessionDetailResponse>(id ? `/api/sessions/detail?id=${encodeURIComponent(id)}` : null);
  const d = detail.data;

  return (
    <div className="space-y-6">
      <nav className="flex items-center gap-2 text-sm text-on-surface-variant">
        <Link to="/sessions" className="hover:text-primary-container hover:underline">{t("sessions.title")}</Link>
        <span className="material-symbols-outlined text-base">chevron_right</span>
        <span className="font-mono text-xs text-on-surface">{id.slice(0, 8)}</span>
      </nav>

      {detail.error ? (
        <div className="flex h-48 flex-col items-center justify-center gap-3 rounded border border-border-card bg-surface-card text-sm text-on-surface-variant">
          <span>{t("common.loadFailed", { error: detail.error })}</span>
          <button onClick={detail.retry} className="rounded border border-primary-container px-3 py-1.5 text-primary-container">{t("common.retry")}</button>
        </div>
      ) : !d ? (
        <div className="flex h-48 items-center justify-center rounded border border-border-card bg-surface-card text-sm text-on-surface-variant">{t("common.loading")}</div>
      ) : (
        <>
          <div>
            <h3 className="text-3xl font-bold">
              <Link to={`/projects/detail?path=${encodeURIComponent(d.session.project)}`} className="hover:underline">{d.session.name}</Link>
            </h3>
            <div className="mt-2 flex flex-wrap items-center gap-4 text-sm text-on-surface-variant">
              <span className="font-mono text-xs" title={d.session.session_id}>{d.session.session_id}</span>
              <span>{formatLocalTime(d.session.first_ts)} → {formatLocalTime(d.session.last_ts)}</span>
              <span>{d.session.models.map(modelLabel).join(", ")}</span>
              {d.session.subagent_events > 0 && (
                <span className="rounded-full bg-chart-cache-read px-2.5 py-0.5 text-xs font-medium text-primary">
                  {t("sessionDetail.subagentNote", { n: d.session.subagent_events, cost: money(d.session.subagent_cost) })}
                </span>
              )}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
            <StatCard label={t("sessionDetail.cardCost")} icon="attach_money" value={money(d.session.cost)}
              note={t("sessionDetail.cardCostNote", { avg: precise(d.session.messages ? d.session.cost / d.session.messages : 0) })} />
            <StatCard label={t("sessionDetail.cardMessages")} icon="forum" value={d.session.messages.toLocaleString()}
              note={t("sessionDetail.cardDuration", { d: formatDuration(d.session.duration_s) })} />
            <StatCard label={t("sessionDetail.cardPeak")} icon="memory" value={formatTokens(d.session.ctx_max)}
              note={d.peak_context ? t("sessionDetail.peakAt", { i: d.peak_context.i + 1 }) : ""}
              accent={d.session.ctx_max >= 150_000 ? "text-error" : undefined} />
            <StatCard label={t("sessionDetail.cardTools")} icon="build" value={d.session.tool_calls.toLocaleString()}
              note={t("sessionDetail.cardTokens", { tokens: formatTokens(d.session.tokens_total) })} />
          </div>

          <ChartCard title={t("sessionDetail.chartTitle")} subtitle={t("sessionDetail.chartSubtitle")} empty={!d.messages.length}>
            <ContextChart messages={d.messages} peak={d.peak_context} />
          </ChartCard>

          <ChartCard title={t("sessionDetail.toolsTitle")} empty={!d.tools.tools.length} emptyText={t("sessionDetail.noToolsAtAll")}>
            <ToolsTable data={d.tools} compact />
          </ChartCard>

          <ChartCard title={t("sessionDetail.timeline")} subtitle={d.truncated ? t("sessionDetail.truncated") : undefined}>
            <div className="max-h-[520px] overflow-auto">
              <table className="w-full min-w-[820px] text-sm">
                <thead className="sticky top-0 bg-surface-card">
                  <tr className="border-b border-border-card text-left text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
                    <th className="py-2 pr-3">#</th>
                    <th className="px-3 py-2">{t("sessionDetail.colTime")}</th>
                    <th className="px-3 py-2">{t("sessionDetail.colModel")}</th>
                    <th className="px-3 py-2 text-right">{t("sessionDetail.colContext")}</th>
                    <th className="px-3 py-2 text-right">{t("sessionDetail.colOutput")}</th>
                    <th className="px-3 py-2">{t("sessionDetail.colTools")}</th>
                    <th className="px-3 py-2 text-right">{t("sessionDetail.colCost")}</th>
                    <th className="px-3 py-2 text-right">{t("sessionDetail.colCumulative")}</th>
                  </tr>
                </thead>
                <tbody>
                  {d.messages.map((m) => (
                    <tr key={m.i} className={`border-b border-border-card/60 last:border-0 ${d.peak_context?.i === m.i ? "bg-error-container/40" : ""}`}>
                      <td className="py-1.5 pr-3 font-mono text-xs text-outline">{m.i + 1}</td>
                      <td className="px-3 py-1.5 font-mono text-xs">{formatLocalTime(m.ts).slice(11)}</td>
                      <td className="px-3 py-1.5 text-xs">
                        {modelLabel(m.model)}
                        {m.sidechain && <span className="ml-1 rounded bg-surface px-1.5 py-0.5 text-[10px] text-on-surface-variant">{m.agent ?? t("sessionDetail.sidechainTag")}</span>}
                      </td>
                      <td className="px-3 py-1.5 text-right font-mono text-xs">{formatTokens(m.context)}</td>
                      <td className="px-3 py-1.5 text-right font-mono text-xs">{formatTokens(m.output)}</td>
                      <td className="px-3 py-1.5 font-mono text-[11px] text-on-surface-variant">{m.tools.length ? m.tools.join(", ") : "—"}</td>
                      <td className="px-3 py-1.5 text-right font-mono text-xs">{precise(m.cost)}</td>
                      <td className="px-3 py-1.5 text-right font-mono text-xs">{money(m.cumulative_cost)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </ChartCard>
        </>
      )}
    </div>
  );
}
