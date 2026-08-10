import { useState } from "react";
import { Link } from "react-router-dom";
import type { ProjectItem, RangeKey } from "../api/types";
import { useApi } from "../api/useApi";
import Sparkline from "../charts/Sparkline";
import TimeRangeSelector from "../components/TimeRangeSelector";
import { formatRelative, formatTokens, formatUSD } from "../lib/format";

export default function ProjectCosts() {
  const [range, setRange] = useState<RangeKey>("30d");
  const projects = useApi<{ items: ProjectItem[] }>(`/api/projects?range=${range}`);
  const items = projects.data?.items ?? [];
  const top = items[0];
  const totalCost = items.reduce((s, x) => s + x.cost, 0);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-2xl font-bold">Project Costs</h3>
          <p className="mt-1 text-sm text-on-surface-variant">
            按项目归因的消耗与虚拟成本(等效 API 价,套餐实际为固定月费)
          </p>
        </div>
        <TimeRangeSelector value={range} onChange={setRange} />
      </div>

      {projects.error ? (
        <div className="flex h-48 flex-col items-center justify-center gap-3 rounded border border-border-card bg-surface-card text-sm text-on-surface-variant">
          <span>加载失败:{projects.error}</span>
          <button onClick={projects.retry} className="rounded border border-primary-container px-3 py-1.5 text-primary-container">重试</button>
        </div>
      ) : projects.loading && !projects.data ? (
        <div className="flex h-48 items-center justify-center rounded border border-border-card bg-surface-card text-sm text-on-surface-variant">加载中…</div>
      ) : items.length === 0 ? (
        <div className="flex h-48 items-center justify-center rounded border border-border-card bg-surface-card text-sm text-on-surface-variant">该时间范围内暂无项目消耗</div>
      ) : (
        <>
          {/* 头部两张摘要卡 */}
          <div className="grid gap-4 lg:grid-cols-2">
            {top && (
              <div className="rounded border border-border-card bg-surface-card p-5 shadow-card">
                <div className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
                  最高消耗项目
                </div>
                <div className="mt-1 text-lg font-semibold">{top.name}</div>
                <div className="mt-2 text-3xl font-bold">{formatUSD(top.cost)}</div>
                <div className="mt-1 flex items-center justify-between text-sm text-on-surface-variant">
                  <span>{formatTokens(top.tokens)} Tokens</span>
                  <Link to={`/projects/detail?path=${encodeURIComponent(top.path)}`} className="font-medium text-primary-container hover:underline">
                    View Breakdown
                  </Link>
                </div>
              </div>
            )}
            <div className="rounded border border-border-card bg-surface-card p-5 shadow-card">
              <div className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
                范围内总虚拟成本
              </div>
              <div className="mt-1 text-lg font-semibold">{items.length} 个活跃项目</div>
              <div className="mt-2 text-3xl font-bold">{formatUSD(totalCost)}</div>
              <div className="mt-1 text-sm text-on-surface-variant">
                {formatTokens(items.reduce((s, x) => s + x.tokens, 0))} Tokens
              </div>
            </div>
          </div>

          {/* 项目卡片网格 */}
          <div>
            <h4 className="mb-3 text-base font-semibold">Active Projects Breakdown</h4>
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {items.map((p) => (
                <div key={p.path} className="flex flex-col rounded border border-border-card bg-surface-card p-4 shadow-card">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="truncate font-semibold" title={p.name}>{p.name}</div>
                      <div className="mt-0.5 truncate font-mono text-xs text-outline" title={p.path}>{p.path}</div>
                    </div>
                    <span className="shrink-0 rounded-full bg-chart-cache-read px-2.5 py-0.5 text-xs font-medium text-primary">
                      {formatRelative(p.last_active)}
                    </span>
                  </div>
                  <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
                    <div>
                      <div className="text-xs text-on-surface-variant">Tokens Used</div>
                      <div className="font-semibold">{formatTokens(p.tokens)}</div>
                    </div>
                    <div>
                      <div className="text-xs text-on-surface-variant">虚拟成本</div>
                      <div className="font-semibold">{formatUSD(p.cost)}</div>
                    </div>
                  </div>
                  <div className="mt-2"><Sparkline points={p.spark} /></div>
                  <Link
                    to={`/projects/detail?path=${encodeURIComponent(p.path)}`}
                    className="mt-3 rounded border border-primary-container py-2 text-center text-sm font-semibold text-primary-container hover:bg-surface"
                  >
                    View Details
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
