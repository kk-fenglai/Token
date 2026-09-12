import { useState } from "react";
import type { ModelsResponse, ProjectShare, ProjectTopItem, RangeKey, SavingsReport, SummaryCards, TrendPoint } from "../api/types";
import { useScope } from "../api/scope";
import { useApi } from "../api/useApi";
import ModelDonut from "../charts/ModelDonut";
import ProjectBars from "../charts/ProjectBars";
import TrendChart from "../charts/TrendChart";
import AlertStrip from "../components/AlertStrip";
import ChartCard from "../components/ChartCard";
import ModelTable from "../components/ModelTable";
import ProjectShareCard from "../components/ProjectShareCard";
import SavingsPanel from "../components/SavingsPanel";
import StatCard from "../components/StatCard";
import TimeRangeSelector from "../components/TimeRangeSelector";
import { useI18n } from "../i18n";
import { useMoney } from "../lib/currency";
import { formatTokens } from "../lib/format";

export default function Dashboard() {
  const { t } = useI18n();
  const { money } = useMoney();
  const { project, withScope, ready } = useScope();
  const [granularity, setGranularity] = useState<"day" | "month">("day");
  const [donutRange, setDonutRange] = useState<RangeKey>("month");
  const [donutMode, setDonutMode] = useState<"tokens" | "cost">("tokens");
  const [subKey, setSubKey] = useState(0);

  // Hold every request until the scope is resolved, so a scoped dashboard
  // never flashes account-wide numbers first.
  const cards = useApi<SummaryCards>(ready ? withScope("/api/summary/cards") : null, [subKey]);
  const savings = useApi<SavingsReport>(ready && !project ? "/api/subscription" : null, [subKey]);
  const share = useApi<ProjectShare>(
    ready && project ? `/api/projects/share?project=${encodeURIComponent(project)}` : null,
  );
  const trend = useApi<{ points: TrendPoint[] }>(ready ? withScope(
    granularity === "day" ? "/api/trend?granularity=day&days=30" : "/api/trend?granularity=month&months=12",
  ) : null);
  const models = useApi<ModelsResponse>(ready ? withScope(`/api/models?range=${donutRange}`) : null);
  // Top-10 stays account-wide: it exists to compare projects against each other.
  const projects = useApi<{ items: ProjectTopItem[] }>(ready ? "/api/projects/top?range=month&limit=10" : null);

  const costNote = t("dashboard.virtualCostNote");

  return (
    <div className="space-y-6">
      <AlertStrip />

      {/* F1 概览指标卡片 */}
      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <StatCard label={t("dashboard.todayTokens")} icon="token"
          value={cards.data ? formatTokens(cards.data.today.tokens.total) : "…"}
          note={cards.data ? t("dashboard.requests", { n: cards.data.today.events }) : undefined} />
        <StatCard label={t("dashboard.todayCost")} icon="attach_money"
          value={cards.data ? money(cards.data.today.cost.total) : "…"}
          note={costNote} />
        <StatCard label={t("dashboard.monthTokens")} icon="calendar_month"
          value={cards.data ? formatTokens(cards.data.month.tokens.total) : "…"}
          note={cards.data
            ? cards.data.month.efficiency?.cache_hit_rate != null
              ? `${t("dashboard.requests", { n: cards.data.month.events })} · ${t("dashboard.cacheNote", {
                  rate: (cards.data.month.efficiency.cache_hit_rate * 100).toFixed(1),
                  saved: money(cards.data.month.efficiency.cache_saved),
                })}`
              : t("dashboard.requests", { n: cards.data.month.events })
            : undefined} />
        <StatCard label={t("dashboard.monthCost")} icon="payments"
          value={cards.data ? money(cards.data.month.cost.total) : "…"}
          note={cards.data?.savings.comparable && !project
            ? t("dashboard.monthCostSaved", {
                plan: cards.data.savings.plan_label,
                fee: money(cards.data.savings.monthly_fee, 0),
                saved: money(cards.data.savings.saved),
              })
            : costNote}
          accent={cards.data?.savings.comparable && !project ? "text-success" : undefined} />
      </div>

      {/* 限定项目时显示该项目占比,否则显示账户级订阅节省 */}
      {project
        ? share.data && <ProjectShareCard data={share.data} />
        : savings.data && <SavingsPanel report={savings.data} onChanged={() => setSubKey((k) => k + 1)} />}

      {/* F2 消耗趋势 */}
      <ChartCard
        title={t(granularity === "day" ? "dashboard.trendDay" : "dashboard.trendMonth")}
        subtitle={t("dashboard.trendSubtitle")}
        loading={trend.loading}
        error={trend.error}
        onRetry={trend.retry}
        empty={!trend.data?.points.some((p) => p.input + p.output + p.cache_write + p.cache_read > 0)}
        actions={
          <div className="inline-flex rounded border border-border-card p-0.5 text-sm">
            {(["day", "month"] as const).map((g) => (
              <button key={g} onClick={() => setGranularity(g)}
                className={`whitespace-nowrap rounded px-3 py-1 ${granularity === g ? "bg-primary-container font-semibold text-on-primary" : "text-on-surface-variant hover:bg-surface"}`}>
                {t(g === "day" ? "dashboard.daily" : "dashboard.monthly")}
              </button>
            ))}
          </div>
        }
      >
        {trend.data && <TrendChart points={trend.data.points} granularity={granularity} />}
      </ChartCard>

      <div className="grid gap-6 xl:grid-cols-2">
        {/* F3 模型分布 */}
        <ChartCard
          title={t("dashboard.modelDist")}
          subtitle={t("dashboard.modelDistSubtitle")}
          loading={models.loading}
          error={models.error}
          onRetry={models.retry}
          empty={!models.data?.items.length}
          actions={
            <div className="flex items-center gap-2">
              <div className="inline-flex rounded border border-border-card p-0.5 text-sm">
                {(["tokens", "cost"] as const).map((m) => (
                  <button key={m} onClick={() => setDonutMode(m)}
                    className={`whitespace-nowrap rounded px-3 py-1 ${donutMode === m ? "bg-primary-container font-semibold text-on-primary" : "text-on-surface-variant hover:bg-surface"}`}>
                    {t(m === "tokens" ? "dashboard.byUsage" : "dashboard.byCost")}
                  </button>
                ))}
              </div>
              <TimeRangeSelector value={donutRange} onChange={setDonutRange} options={["today", "month", "all"]} />
            </div>
          }
        >
          {models.data && <ModelDonut items={models.data.items} mode={donutMode} />}
        </ChartCard>

        {/* F4 项目归因 Top 10 */}
        <ChartCard
          title={t("dashboard.projectsTop")}
          subtitle={t("dashboard.projectsTopSubtitle")}
          loading={projects.loading}
          error={projects.error}
          onRetry={projects.retry}
          empty={!projects.data?.items.length}
        >
          {projects.data && <ProjectBars items={projects.data.items} />}
        </ChartCard>
      </div>

      {/* 精确到模型:调用次数 / 单价 / 费用 */}
      <ChartCard
        title={t("dashboard.modelTable")}
        subtitle={
          models.data
            ? t("dashboard.modelTableSubtitle", {
                range: t(`range.${donutRange === "all" ? "allTime" : donutRange}`),
                models: models.data.totals.model_count,
                calls: models.data.totals.events.toLocaleString(),
                cost: money(models.data.totals.cost),
              })
            : t("dashboard.modelTableFallback")
        }
        loading={models.loading}
        error={models.error}
        onRetry={models.retry}
        empty={!models.data?.models.length}
        actions={<TimeRangeSelector value={donutRange} onChange={setDonutRange} options={["today", "month", "all"]} />}
      >
        {models.data && <ModelTable items={models.data.models} />}
      </ChartCard>
    </div>
  );
}
