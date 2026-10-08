import { useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../api/useApi";
import StatCard from "../components/StatCard";
import {
  STATUSES, STATUS_LABEL, STATUS_STYLE, VERDICT_STYLE, api, cardHref, dateTime, day, errorText,
  type WeekData,
} from "../lib/ideas";

export default function IdeasWeek() {
  const week = useApi<WeekData>("/api/ideas/week");
  const [obs, setObs] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const d = week.data;
  const sync = d?.sync;
  const lastRun = sync?.runs[0];

  async function addObs() {
    if (!obs.trim()) return;
    try {
      await api("/observations", "POST", { text: obs.trim() });
      setObs("");
      week.retry();
    } catch (e) { setError(errorText(e)); }
  }

  async function syncNow() {
    setSyncing(true);
    try { await api("/sync", "POST"); } catch (e) { setError(errorText(e)); }
    setTimeout(() => { setSyncing(false); week.retry(); }, 3000);
  }

  if (week.error) return <div className="text-sm text-error">加载失败:{week.error}</div>;

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-base font-semibold">本周</h3>
        <p className="mt-0.5 max-w-3xl text-xs text-on-surface-variant">
          每周约 30 分钟:扫付费信号 → 归入需求簇 → 写需求卡片 → 周中做验证。目标不是看了多少产品,而是每月验证完 4 张卡片。
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <StatCard label="本月完成验证(北极星)" icon="flag" value={d ? String(d.validated_month) : "…"}
          note="目标 ≥ 4 张/月" accent={d && d.validated_month >= 4 ? "text-success" : undefined} />
        <StatCard label="待扫的新信号" icon="trending_up" value={d ? String(d.new_signals) : "…"}
          note={d ? `库里共 ${d.products} 个产品,${d.unmarked} 个未标记` : undefined} />
        <StatCard label="需求簇" icon="workspaces" value={d ? String(d.clusters) : "…"}
          note={d ? `${d.interested} 个产品标记为感兴趣` : undefined} />
        <StatCard label="本周生活观察" icon="edit_note" value={d ? String(d.observations_week) : "…"}
          note="目标 ≥ 3 条/周" accent={d && d.observations_week >= 3 ? "text-success" : undefined} />
      </div>

      <section className="rounded border border-border-card bg-surface-card p-4 shadow-card">
        <div className="flex flex-wrap items-center gap-2">
          <span className="material-symbols-outlined text-outline">edit_note</span>
          <input value={obs} onChange={(e) => setObs(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addObs()}
            placeholder="随手记一条生活里的麻烦或客户的抱怨,回车保存"
            className="min-w-[280px] flex-1 rounded border border-border-card bg-surface px-3 py-2 text-sm" />
          <button onClick={addObs} className="rounded bg-primary-container px-3 py-2 text-sm font-semibold text-on-primary">记下</button>
        </div>
        {d && d.recent_observations.length > 0 && (
          <ul className="mt-3 space-y-1 text-sm">
            {d.recent_observations.map((o) => (
              <li key={o.id} className="flex gap-3">
                <span className="w-12 shrink-0 text-xs text-outline">{day(o.created_at)}</span>
                <span className="flex-1">{o.text}</span>
                {o.cluster_name && <span className="text-xs text-primary">{o.cluster_name}</span>}
              </li>
            ))}
          </ul>
        )}
        {error && <div className="mt-2 text-xs text-error">{error}</div>}
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="rounded border border-border-card bg-surface-card p-4 shadow-card">
          <h4 className="mb-3 text-sm font-semibold">待验证的卡片</h4>
          {d && d.validating.length === 0 && (
            <p className="text-sm text-on-surface-variant">没有待验证的卡片。写好卡片、填上生活映射后,把状态改成“待验证”。</p>
          )}
          <ul className="space-y-2">
            {d?.validating.map((c) => (
              <li key={c.id} className={`flex items-center gap-3 rounded border px-3 py-2 ${c.stale ? "border-error bg-error-container/30" : "border-border-card"}`}>
                <Link to={cardHref(c.id)} className="flex-1 truncate text-sm font-medium hover:underline">{c.need || "未命名需求"}</Link>
                <span className={`text-xs ${VERDICT_STYLE[c.evaluation.verdict]}`}>{c.evaluation.total}/12</span>
                <span className={`text-xs ${c.stale ? "font-semibold text-error" : "text-outline"}`}>
                  {c.stale ? "超过 14 天没动" : `最近 ${day(c.last_activity)}`}
                </span>
              </li>
            ))}
          </ul>
          {d && d.ready_clusters.length > 0 && (
            <>
              <h4 className="mb-2 mt-5 text-sm font-semibold">信号已满 3 个、还没写卡片的需求簇</h4>
              <ul className="space-y-1 text-sm">
                {d.ready_clusters.map((c) => (
                  <li key={c.id} className="flex items-center justify-between">
                    <Link to={`/ideas/needs?cluster=${c.id}`} className="hover:underline">{c.name}</Link>
                    <span className="text-xs text-outline">{c.n} 个产品</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>

        <section className="rounded border border-border-card bg-surface-card p-4 shadow-card">
          <div className="mb-3 flex items-center justify-between">
            <h4 className="text-sm font-semibold">需求卡片</h4>
            <Link to="/ideas/needs" className="text-xs text-primary hover:underline">去需求看板</Link>
          </div>
          <div className="flex flex-wrap gap-2">
            {STATUSES.map((s) => (
              <span key={s} className={`rounded border px-3 py-1 text-sm ${STATUS_STYLE[s]}`}>
                {STATUS_LABEL[s]} {d ? d.cards_by_status[s] : "…"}
              </span>
            ))}
          </div>
          <h4 className="mb-2 mt-5 text-sm font-semibold">数据同步</h4>
          <div className="space-y-1 text-sm text-on-surface-variant">
            <div>数据源:{sync ? (sync.key.configured ? "TrustMRR 认证 API" : "公开发现接口(未配置 API Key,只有 50 个产品)") : "…"}</div>
            <div>
              上次同步:{lastRun ? `${dateTime(lastRun.finished_at ?? lastRun.started_at)} · ${lastRun.status === "ok" ? "成功" : lastRun.status === "running" ? "进行中" : "失败"}` : "从未同步"}
              {lastRun?.error && <span className="ml-1 text-error">({lastRun.error})</span>}
            </div>
            {sync?.running && <div className="text-primary">同步中:{sync.phase}{sync.page ? ` · 第 ${sync.page} 页` : ""}</div>}
          </div>
          <div className="mt-3 flex gap-2">
            <button onClick={syncNow} disabled={syncing || sync?.running}
              className="flex items-center gap-1 rounded bg-primary-container px-3 py-1.5 text-sm font-semibold text-on-primary disabled:opacity-60">
              <span className={`material-symbols-outlined text-[18px] ${syncing || sync?.running ? "animate-spin" : ""}`}>sync</span>立即同步
            </button>
            <Link to="/ideas/signals?view=new" className="rounded border border-border-card px-3 py-1.5 text-sm hover:bg-surface">开始扫信号</Link>
          </div>
        </section>
      </div>
      <p className="text-xs text-outline">{"TrustMRR 数据只用于本机私人研究:不对外展示、不导出指标、不抓取网页。"}</p>
    </div>
  );
}
