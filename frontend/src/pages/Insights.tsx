import { useState } from "react";
import { Link } from "react-router-dom";
import type {
  AlertsResponse, Heatmap as HeatmapData, RetentionInfo, SummaryCards, ToolsBreakdown, WeeklyReport,
} from "../api/types";
import { useScope } from "../api/scope";
import { useApi } from "../api/useApi";
import Heatmap from "../charts/Heatmap";
import { AlertRow } from "../components/AlertStrip";
import ChartCard from "../components/ChartCard";
import ToolsTable from "../components/ToolsTable";
import { Rich, useI18n } from "../i18n";
import { useMoney } from "../lib/currency";
import { formatRelative, formatTokens } from "../lib/format";

export default function Insights() {
  const { t, tag, locale } = useI18n();
  const { money } = useMoney();
  const { project, ready } = useScope();
  const scoped = project ? `&project=${encodeURIComponent(project)}` : "";
  const scopedOnly = project ? `?project=${encodeURIComponent(project)}` : "";
  const [week, setWeek] = useState(0);
  const [copied, setCopied] = useState(false);

  const alerts = useApi<AlertsResponse>(ready ? `/api/alerts${scopedOnly}` : null);
  const heat = useApi<HeatmapData>(ready ? `/api/heatmap?range=30d${scoped}` : null);
  const tools = useApi<ToolsBreakdown>(ready ? `/api/tools?range=30d${scoped}` : null);
  const cards = useApi<SummaryCards>(ready ? `/api/summary/cards${scopedOnly}` : null);
  const report = useApi<WeeklyReport>(ready ? `/api/report/weekly?week=${week}&lang=${locale}${scoped}` : null);
  const retention = useApi<RetentionInfo>("/api/retention");

  async function copyMarkdown() {
    if (!report.data) return;
    try {
      await navigator.clipboard.writeText(report.data.markdown);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch { /* clipboard blocked: the text is selectable below */ }
  }

  const eff = cards.data?.month.efficiency;
  const ret = retention.data;
  const weekLabel = (n: number) => n === 0 ? t("insights.thisWeek") : n === 1 ? t("insights.lastWeek") : t("insights.weeksAgo", { n });

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-2xl font-bold">{t("insights.title")}</h3>
        <p className="mt-1 text-sm text-on-surface-variant">{t("insights.subtitle")}</p>
      </div>

      {/* 提醒 */}
      <section>
        <h4 className="mb-2 text-sm font-semibold uppercase tracking-wide text-on-surface-variant">{t("alerts.title")}</h4>
        {alerts.data && alerts.data.items.length === 0 ? (
          <p className="rounded border border-border-card bg-surface-card px-4 py-3 text-sm text-on-surface-variant shadow-card">{t("alerts.none")}</p>
        ) : (
          <ul className="space-y-2">{alerts.data?.items.map((a, i) => <AlertRow key={`${a.kind}-${i}`} a={a} />)}</ul>
        )}
      </section>

      {/* 效率 + 留存 */}
      <div className="grid gap-6 xl:grid-cols-2">
        <ChartCard title={t("insights.efficiencyTitle")} subtitle={t("insights.efficiencySubtitle")} loading={cards.loading} empty={!eff}>
          {eff && (
            <div className="grid grid-cols-3 gap-4">
              <Metric label={t("insights.hitRate")} value={eff.cache_hit_rate != null ? `${(eff.cache_hit_rate * 100).toFixed(1)}%` : "—"}
                accent={eff.cache_hit_rate != null && eff.cache_hit_rate < 0.7 ? "text-secondary" : "text-success"} />
              <Metric label={t("insights.cacheSaved")} value={money(eff.cache_saved)} />
              <Metric label={t("insights.per1k")} value={eff.cost_per_1k_output != null ? money(eff.cost_per_1k_output) : "—"} />
            </div>
          )}
        </ChartCard>
        <ChartCard title={t("insights.retentionTitle")} loading={retention.loading} error={retention.error} onRetry={retention.retry}>
          {ret && (
            <div className="space-y-2 text-sm">
              <Rich text={t("insights.retentionBody", {
                days: ret.cleanup_days,
                configured: t(ret.configured ? "insights.configuredYes" : "insights.configuredNo"),
                since: formatRelative(ret.last_sync_at, tag, { never: t("common.never"), justNow: t("common.justNow") }),
                recommended: ret.recommended_days,
              })} />
              <p className={ret.pricing.stale ? "text-secondary" : "text-on-surface-variant"}>
                {t(ret.pricing.stale ? "insights.pricingStale" : "insights.pricingOk",
                  { date: ret.pricing.last_verified ?? "?", days: ret.pricing.age_days ?? 0 })}
              </p>
              <p className="font-mono text-[11px] text-outline">{ret.settings_path}</p>
            </div>
          )}
        </ChartCard>
      </div>

      {/* 热力图 */}
      <ChartCard title={t("insights.heatmapTitle")} subtitle={t("insights.heatmapSubtitle")}
        loading={heat.loading} error={heat.error} onRetry={heat.retry} empty={!heat.data?.total_cost}>
        {heat.data && <Heatmap data={heat.data} />}
      </ChartCard>

      {/* 工具分布 */}
      <ChartCard title={t("insights.toolsTitle")} subtitle={t("insights.toolsSubtitle")}
        loading={tools.loading} error={tools.error} onRetry={tools.retry} empty={!tools.data?.totals.events}>
        {tools.data && <ToolsTable data={tools.data} />}
      </ChartCard>

      {/* 周报 */}
      <ChartCard
        title={t("insights.reportTitle")}
        subtitle={t("insights.reportSubtitle")}
        loading={report.loading && !report.data}
        error={report.error}
        onRetry={report.retry}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <div className="inline-flex rounded border border-border-card p-0.5 text-sm">
              {[0, 1, 2, 3].map((n) => (
                <button key={n} onClick={() => setWeek(n)}
                  className={`whitespace-nowrap rounded px-3 py-1 ${week === n ? "bg-primary-container font-semibold text-on-primary" : "text-on-surface-variant hover:bg-surface"}`}>
                  {weekLabel(n)}
                </button>
              ))}
            </div>
            <button onClick={copyMarkdown} className="rounded border border-primary-container px-3 py-1 text-sm font-semibold text-primary-container hover:bg-surface">
              {copied ? t("insights.copied") : t("insights.copy")}
            </button>
            <a href={`/api/report/weekly.md?week=${week}&lang=${locale}${scoped}`}
              className="rounded border border-outline-variant px-3 py-1 text-sm text-on-surface-variant hover:bg-surface">
              {t("insights.download")}
            </a>
          </div>
        }
      >
        {report.data && (
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
            <div className="space-y-3 text-sm">
              <div className="grid grid-cols-2 gap-3">
                <Metric label={t("insights.weekCost")} value={money(report.data.totals.cost)} note={delta(report.data.delta_pct.cost, t)} />
                <Metric label={t("insights.weekSessions")} value={String(report.data.totals.sessions)} note={delta(report.data.delta_pct.sessions, t)} />
                <Metric label={t("insights.weekCalls")} value={report.data.totals.events.toLocaleString()} note={delta(report.data.delta_pct.events, t)} />
                <Metric label={t("insights.weekTokens")} value={formatTokens(report.data.totals.tokens.total)} note={delta(report.data.delta_pct.tokens, t)} />
              </div>
              {report.data.top_sessions.length > 0 && (
                <div>
                  <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-on-surface-variant">{t("insights.weekTopSessions")}</div>
                  <ul className="space-y-1">
                    {report.data.top_sessions.map((s) => (
                      <li key={s.session_id} className="flex items-center justify-between gap-2">
                        <Link to={`/sessions/detail?id=${encodeURIComponent(s.session_id)}`} className="truncate text-primary-container hover:underline">
                          {s.name} · {s.first_ts.slice(5, 16).replace("T", " ")}
                        </Link>
                        <span className="font-mono text-xs">{money(s.cost)}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
            <pre className="max-h-[480px] overflow-auto whitespace-pre-wrap rounded border border-border-card bg-surface p-3 font-mono text-[11px] leading-relaxed text-on-surface-variant">
              {report.data.markdown}
            </pre>
          </div>
        )}
      </ChartCard>
    </div>
  );
}

function delta(pct: number | null, t: (k: string, v?: Record<string, string | number>) => string): string {
  if (pct == null) return t("insights.noPrev");
  return t("insights.vsLastWeek", { d: `${pct > 0 ? "+" : ""}${pct}` });
}

function Metric({ label, value, note, accent }: { label: string; value: string; note?: string; accent?: string }) {
  return (
    <div className="rounded border border-border-card bg-surface p-3">
      <div className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">{label}</div>
      <div className={`mt-1 text-xl font-bold ${accent ?? "text-on-surface"}`}>{value}</div>
      {note && <div className="mt-0.5 text-xs text-outline">{note}</div>}
    </div>
  );
}
