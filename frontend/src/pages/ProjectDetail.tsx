import { Link, useSearchParams } from "react-router-dom";
import type { ProjectDetail as Detail } from "../api/types";
import { useApi } from "../api/useApi";
import StatCard from "../components/StatCard";
import { formatLocalTime, formatTokens, formatUSD } from "../lib/format";

export default function ProjectDetail() {
  const [sp] = useSearchParams();
  const path = sp.get("path") ?? "";
  const detail = useApi<Detail>(path ? `/api/projects/detail?path=${encodeURIComponent(path)}` : null);
  const d = detail.data;

  return (
    <div className="space-y-6">
      <nav className="flex items-center gap-2 text-sm text-on-surface-variant">
        <Link to="/projects" className="hover:text-primary-container hover:underline">Project Costs</Link>
        <span className="material-symbols-outlined text-base">chevron_right</span>
        <span className="text-on-surface">{d?.name ?? "…"}</span>
      </nav>

      {detail.error ? (
        <div className="flex h-48 flex-col items-center justify-center gap-3 rounded border border-border-card bg-surface-card text-sm text-on-surface-variant">
          <span>加载失败:{detail.error}</span>
          <button onClick={detail.retry} className="rounded border border-primary-container px-3 py-1.5 text-primary-container">重试</button>
        </div>
      ) : !d ? (
        <div className="flex h-48 items-center justify-center rounded border border-border-card bg-surface-card text-sm text-on-surface-variant">加载中…</div>
      ) : (
        <>
          <div>
            <h3 className="text-3xl font-bold">{d.name}</h3>
            <div className="mt-2 flex flex-wrap items-center gap-4 text-sm text-on-surface-variant">
              <span className="flex items-center gap-1 font-mono text-xs">
                <span className="material-symbols-outlined text-base">folder</span>{d.path}
              </span>
              <span className="flex items-center gap-1">
                <span className="material-symbols-outlined text-base">calendar_today</span>
                首次活动 {formatLocalTime(d.first_seen).slice(0, 10)}
              </span>
              <span className="rounded-full bg-chart-cache-read px-2.5 py-0.5 text-xs font-medium text-primary">
                最近活动 {formatLocalTime(d.last_active)}
              </span>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
            <StatCard label="Total Tokens" icon="data_usage"
              value={formatTokens(d.tokens)}
              note={d.tokens_delta_pct != null ? `${d.tokens_delta_pct > 0 ? "+" : ""}${d.tokens_delta_pct}% vs 上月(本月 ${formatTokens(d.month_tokens)})` : `本月 ${formatTokens(d.month_tokens)}`}
              accent={d.tokens_delta_pct != null && d.tokens_delta_pct > 0 ? "text-secondary" : "text-on-surface-variant"} />
            <StatCard label="虚拟成本(全部)" icon="attach_money"
              value={formatUSD(d.cost)}
              note="等效 API 成本(虚拟)" />
            <StatCard label="Avg Request Cost" icon="request_quote"
              value={`$${d.avg_cost_per_event.toFixed(4)}`}
              note={`${d.sessions} 个会话`} />
            <StatCard label="Associated Logs" icon="receipt_long"
              value={d.events.toLocaleString()}
              note="条 assistant 消息" />
          </div>

          <div className="rounded border border-border-card bg-surface-card p-5 shadow-card">
            <h4 className="mb-3 text-base font-semibold">Token 构成(全部时间)</h4>
            <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
              {(
                [
                  ["Input", d.tokens_detail.input, "bg-chart-input"],
                  ["Output", d.tokens_detail.output, "bg-chart-output"],
                  ["Cache Write", d.tokens_detail.cache_write, "bg-chart-cache-write"],
                  ["Cache Read", d.tokens_detail.cache_read, "bg-chart-cache-read"],
                ] as const
              ).map(([label, value, color]) => (
                <div key={label} className="flex items-center gap-3">
                  <span className={`h-3 w-3 rounded-full ${color}`} />
                  <div>
                    <div className="text-xs text-on-surface-variant">{label}</div>
                    <div className="font-mono text-sm font-semibold">{formatTokens(value)}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <Link
            to={`/logs`}
            className="inline-flex items-center gap-2 text-sm font-medium text-primary-container hover:underline"
          >
            <span className="material-symbols-outlined">receipt_long</span>
            在 Usage Logs 中查看该项目明细
          </Link>
        </>
      )}
    </div>
  );
}
