import { useState } from "react";
import { Link } from "react-router-dom";
import type { ProjectItem, RangeKey } from "../api/types";
import { useApi } from "../api/useApi";
import Sparkline from "../charts/Sparkline";
import TimeRangeSelector from "../components/TimeRangeSelector";
import { useI18n } from "../i18n";
import { formatRelative, formatTokens, formatUSD } from "../lib/format";

export default function ProjectCosts() {
  const { t, tag } = useI18n();
  const rel = { never: t("common.never"), justNow: t("common.justNow") };
  const [range, setRange] = useState<RangeKey>("30d");
  const projects = useApi<{ items: ProjectItem[] }>(`/api/projects?range=${range}`);
  const items = projects.data?.items ?? [];
  const top = items[0];
  const totalCost = items.reduce((s, x) => s + x.cost, 0);
  const todayTokens = items.reduce((s, x) => s + x.today.tokens, 0);
  const todayCost = items.reduce((s, x) => s + x.today.cost, 0);
  const activeToday = items.filter((x) => x.today.tokens > 0).length;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-2xl font-bold">{t("projects.title")}</h3>
          <p className="mt-1 text-sm text-on-surface-variant">
            {t("projects.subtitle")}
          </p>
        </div>
        <TimeRangeSelector value={range} onChange={setRange} />
      </div>

      {projects.error ? (
        <div className="flex h-48 flex-col items-center justify-center gap-3 rounded border border-border-card bg-surface-card text-sm text-on-surface-variant">
          <span>{t("common.loadFailed", { error: projects.error })}</span>
          <button onClick={projects.retry} className="rounded border border-primary-container px-3 py-1.5 text-primary-container">{t("common.retry")}</button>
        </div>
      ) : projects.loading && !projects.data ? (
        <div className="flex h-48 items-center justify-center rounded border border-border-card bg-surface-card text-sm text-on-surface-variant">{t("common.loading")}</div>
      ) : items.length === 0 ? (
        <div className="flex h-48 items-center justify-center rounded border border-border-card bg-surface-card text-sm text-on-surface-variant">{t("projects.empty")}</div>
      ) : (
        <>
          {/* 头部两张摘要卡 */}
          <div className="grid gap-4 lg:grid-cols-2">
            {top && (
              <div className="rounded border border-border-card bg-surface-card p-5 shadow-card">
                <div className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
                  {t("projects.topProject")}
                </div>
                <div className="mt-1 text-lg font-semibold">{top.name}</div>
                <div className="mt-2 text-3xl font-bold">{formatUSD(top.cost)}</div>
                <div className="mt-1 flex items-center justify-between text-sm text-on-surface-variant">
                  <span>{formatTokens(top.tokens)} {t("common.tokens")}</span>
                  <Link to={`/projects/detail?path=${encodeURIComponent(top.path)}`} className="font-medium text-primary-container hover:underline">
                    {t("projects.viewBreakdown")}
                  </Link>
                </div>
              </div>
            )}
            <div className="rounded border border-border-card bg-surface-card p-5 shadow-card">
              <div className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
                {t("projects.totalInRange")}
              </div>
              <div className="mt-1 text-lg font-semibold">{t("projects.activeCount", { n: items.length })}</div>
              <div className="mt-2 text-3xl font-bold">{formatUSD(totalCost)}</div>
              <div className="mt-1 text-sm text-on-surface-variant">
                {formatTokens(items.reduce((s, x) => s + x.tokens, 0))} {t("common.tokens")}
              </div>
              <div className="mt-3 border-t border-border-card pt-2 text-sm">
                <span className="text-on-surface-variant">{t("projects.todayTotal")}: </span>
                <span className="font-mono font-semibold">
                  {formatTokens(todayTokens)} · {formatUSD(todayCost)}
                </span>
                <span className="ml-2 text-xs text-outline">
                  {t("projects.activeToday", { n: activeToday })}
                </span>
              </div>
            </div>
          </div>

          {/* 项目卡片网格 */}
          <div>
            <h4 className="mb-3 text-base font-semibold">{t("projects.breakdownTitle")}</h4>
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {items.map((p) => (
                <div key={p.path} className="flex flex-col rounded border border-border-card bg-surface-card p-4 shadow-card">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="truncate font-semibold" title={p.name}>{p.name}</div>
                      <div className="mt-0.5 truncate font-mono text-xs text-outline" title={p.path}>{p.path}</div>
                    </div>
                    <span className="shrink-0 rounded-full bg-chart-cache-read px-2.5 py-0.5 text-xs font-medium text-primary">
                      {formatRelative(p.last_active, tag, rel)}
                    </span>
                  </div>
                  <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
                    <div>
                      <div className="text-xs text-on-surface-variant">{t("projects.tokensUsed")}</div>
                      <div className="font-semibold">{formatTokens(p.tokens)}</div>
                    </div>
                    <div>
                      <div className="text-xs text-on-surface-variant">{t("common.virtualCost")}</div>
                      <div className="font-semibold">{formatUSD(p.cost)}</div>
                    </div>
                  </div>
                  {/* 今日始终显示,与所选范围无关 —— 除非范围本身就是今日 */}
                  {range !== "today" && (
                    <div className={`mt-2 flex items-center justify-between rounded px-2 py-1.5 text-xs ${
                      p.today.tokens > 0
                        ? "bg-success-container text-on-success-container"
                        : "bg-surface text-outline"
                    }`}>
                      <span className="font-semibold">{t("projects.today")}</span>
                      {p.today.tokens > 0 ? (
                        <span className="font-mono">
                          {formatTokens(p.today.tokens)} · {formatUSD(p.today.cost)} ·{" "}
                          {t("dashboard.requests", { n: p.today.events })}
                        </span>
                      ) : (
                        <span>{t("projects.todayIdle")}</span>
                      )}
                    </div>
                  )}
                  <div className="mt-2"><Sparkline points={p.spark} /></div>
                  <Link
                    to={`/projects/detail?path=${encodeURIComponent(p.path)}`}
                    className="mt-3 rounded border border-primary-container py-2 text-center text-sm font-semibold text-primary-container hover:bg-surface"
                  >
                    {t("projects.viewDetails")}
                  </Link>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
