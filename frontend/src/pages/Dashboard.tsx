import { useState } from "react";
import type { ModelsResponse, ProjectTopItem, RangeKey, SummaryCards, TrendPoint } from "../api/types";
import { useApi } from "../api/useApi";
import ModelDonut from "../charts/ModelDonut";
import ProjectBars from "../charts/ProjectBars";
import TrendChart from "../charts/TrendChart";
import ChartCard from "../components/ChartCard";
import StatCard from "../components/StatCard";
import TimeRangeSelector from "../components/TimeRangeSelector";
import { formatTokens, formatUSD } from "../lib/format";

const VIRTUAL_COST_NOTE = "等效 API 成本(虚拟),套餐实际为固定月费";

export default function Dashboard() {
  const [granularity, setGranularity] = useState<"day" | "month">("day");
  const [donutRange, setDonutRange] = useState<RangeKey>("month");
  const [donutMode, setDonutMode] = useState<"tokens" | "cost">("tokens");

  const cards = useApi<SummaryCards>("/api/summary/cards");
  const trend = useApi<{ points: TrendPoint[] }>(
    granularity === "day" ? "/api/trend?granularity=day&days=30" : "/api/trend?granularity=month&months=12",
  );
  const models = useApi<ModelsResponse>(`/api/models?range=${donutRange}`);
  const projects = useApi<{ items: ProjectTopItem[] }>("/api/projects/top?range=month&limit=10");

  return (
    <div className="space-y-6">
      {/* F1 概览指标卡片 */}
      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <StatCard label="今日 Token 总量" icon="token"
          value={cards.data ? formatTokens(cards.data.today.tokens.total) : "…"}
          note={cards.data ? `${cards.data.today.events} 次请求` : undefined} />
        <StatCard label="今日虚拟成本" icon="attach_money"
          value={cards.data ? formatUSD(cards.data.today.cost.total) : "…"}
          note={VIRTUAL_COST_NOTE} />
        <StatCard label="本月 Token 总量" icon="calendar_month"
          value={cards.data ? formatTokens(cards.data.month.tokens.total) : "…"}
          note={cards.data ? `${cards.data.month.events} 次请求` : undefined} />
        <StatCard label="本月虚拟成本" icon="payments"
          value={cards.data ? formatUSD(cards.data.month.cost.total) : "…"}
          note={VIRTUAL_COST_NOTE} />
      </div>

      {/* F2 消耗趋势 */}
      <ChartCard
        title={granularity === "day" ? "近 30 天消耗趋势" : "近 12 个月消耗趋势"}
        subtitle="堆叠柱 = token 分类;右轴折线 = 虚拟成本;点击图例可切换序列"
        loading={trend.loading}
        error={trend.error}
        onRetry={trend.retry}
        empty={!trend.data?.points.some((p) => p.input + p.output + p.cache_write + p.cache_read > 0)}
        actions={
          <div className="inline-flex rounded border border-border-card p-0.5 text-sm">
            {(["day", "month"] as const).map((g) => (
              <button key={g} onClick={() => setGranularity(g)}
                className={`whitespace-nowrap rounded px-3 py-1 ${granularity === g ? "bg-primary-container font-semibold text-on-primary" : "text-on-surface-variant hover:bg-surface"}`}>
                {g === "day" ? "逐日" : "逐月"}
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
          title="模型分布"
          subtitle="Opus 单价约为 Sonnet 五倍,成本占比与用量占比会显著不同"
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
                    {m === "tokens" ? "用量" : "成本"}
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
          title="项目归因 Top 10(本月)"
          subtitle="按会话 cwd 归因;点击条形跳转项目详情"
          loading={projects.loading}
          error={projects.error}
          onRetry={projects.retry}
          empty={!projects.data?.items.length}
        >
          {projects.data && <ProjectBars items={projects.data.items} />}
        </ChartCard>
      </div>
    </div>
  );
}
