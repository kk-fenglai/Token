import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useApi } from "../api/useApi";
import {
  STATUSES, STATUS_LABEL, STATUS_STYLE, VERDICT_LABEL, VERDICT_STYLE, api, cardHref, day, errorText, productHref,
  usd, type Card, type ClusterSummary,
} from "../lib/ideas";

export default function IdeasNeeds() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const focus = Number(params.get("cluster") ?? 0);
  const clusters = useApi<ClusterSummary[]>("/api/ideas/clusters");
  const cards = useApi<Card[]>("/api/ideas/cards");
  const [name, setName] = useState("");
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState({ name: "", note: "" });
  const [error, setError] = useState<string | null>(null);
  const [pick, setPick] = useState<number[]>([]);

  useEffect(() => {
    if (focus && clusters.data) document.getElementById(`cl-${focus}`)?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [focus, clusters.data]);

  const reload = () => { clusters.retry(); cards.retry(); };
  const run = async (fn: () => Promise<unknown>) => {
    setError(null);
    try { await fn(); reload(); } catch (e) { setError(errorText(e)); }
  };

  async function newCard(clusterId: number | null) {
    try {
      const c = await api<Card>("/cards", "POST", { cluster_id: clusterId });
      navigate(cardHref(c.id));
    } catch (e) { setError(errorText(e)); }
  }

  const togglePick = (id: number) =>
    setPick((p) => (p.includes(id) ? p.filter((x) => x !== id) : p.length >= 3 ? p : [...p, id]));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold">需求看板</h3>
          <p className="mt-0.5 max-w-3xl text-xs text-on-surface-variant">
            需求簇是一组解决同一个需求的产品;信号满 3 个就可以写成需求卡片。卡片以需求为单位,产品只是证据。
          </p>
        </div>
        <div className="flex gap-2">
          {pick.length >= 2 && (
            <Link to={`/ideas/compare?ids=${pick.join(",")}`} className="rounded bg-primary-container px-3 py-1.5 text-sm font-semibold text-on-primary">
              对比所选 {pick.length} 张
            </Link>
          )}
          <button onClick={() => newCard(null)} className="rounded border border-border-card px-3 py-1.5 text-sm hover:bg-surface">从生活观察新建卡片</button>
        </div>
      </div>
      {error && <div className="text-xs text-error">{error}</div>}

      <section>
        <h4 className="mb-2 text-sm font-semibold">卡片(按状态)</h4>
        <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-5">
          {STATUSES.map((s) => {
            const list = (cards.data ?? []).filter((c) => c.status === s);
            return (
              <div key={s} className="rounded border border-border-card bg-surface p-2">
                <div className="mb-2 flex items-center justify-between px-1">
                  <span className={`rounded border px-2 py-0.5 text-xs font-semibold ${STATUS_STYLE[s]}`}>{STATUS_LABEL[s]}</span>
                  <span className="text-xs text-outline">{list.length}</span>
                </div>
                <div className="space-y-2">
                  {list.map((c) => (
                    <div key={c.id} className={`rounded border bg-surface-card p-2 shadow-card ${c.stale ? "border-error" : "border-border-card"}`}>
                      <div className="flex items-start gap-2">
                        <input type="checkbox" checked={pick.includes(c.id)} onChange={() => togglePick(c.id)} title="加入对比(最多 3 张)" className="mt-1" />
                        <Link to={cardHref(c.id)} className="flex-1 text-sm font-medium leading-5 hover:underline">{c.need || "未命名需求"}</Link>
                      </div>
                      <div className="mt-1 flex items-center justify-between text-xs">
                        <span className={VERDICT_STYLE[c.evaluation.verdict]}>{c.evaluation.total}/12 · {VERDICT_LABEL[c.evaluation.verdict]}</span>
                        <span className="text-outline">{c.cluster_stats.count} 信号</span>
                      </div>
                      {c.stale && <div className="mt-1 text-xs text-error">超过 14 天没动</div>}
                    </div>
                  ))}
                  {list.length === 0 && <div className="px-1 py-3 text-center text-xs text-outline">空</div>}
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <section>
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h4 className="text-sm font-semibold">需求簇</h4>
          <div className="flex gap-1">
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="新需求簇:谁想完成什么"
              onKeyDown={(e) => e.key === "Enter" && name.trim() && run(async () => { await api("/clusters", "POST", { name }); setName(""); })}
              className="w-72 rounded border border-border-card bg-surface-card px-2 py-1.5 text-sm" />
            <button onClick={() => name.trim() && run(async () => { await api("/clusters", "POST", { name }); setName(""); })}
              className="rounded bg-primary-container px-3 py-1.5 text-sm font-semibold text-on-primary">新建</button>
          </div>
        </div>
        {clusters.data?.length === 0 && (
          <p className="rounded border border-dashed border-border-card p-6 text-center text-sm text-on-surface-variant">
            还没有需求簇。去 <Link to="/ideas/signals" className="text-primary underline">付费信号</Link> 把感兴趣的产品归进来。
          </p>
        )}
        <div className="grid gap-3 lg:grid-cols-2">
          {clusters.data?.map((c) => {
            const ready = c.stats.count >= 3;
            return (
              <div id={`cl-${c.id}`} key={c.id}
                className={`rounded border bg-surface-card p-4 shadow-card ${focus === c.id ? "border-primary-container ring-1 ring-primary-container" : "border-border-card"}`}>
                {editing === c.id ? (
                  <div className="space-y-2">
                    <input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} className="w-full rounded border border-border-card px-2 py-1 text-sm" />
                    <textarea value={draft.note} onChange={(e) => setDraft({ ...draft, note: e.target.value })} rows={2} placeholder="备注"
                      className="w-full rounded border border-border-card px-2 py-1 text-sm" />
                    <div className="flex gap-2">
                      <button onClick={() => run(async () => { await api(`/clusters/${c.id}`, "PUT", draft); setEditing(null); })}
                        className="rounded bg-primary-container px-3 py-1 text-xs font-semibold text-on-primary">保存</button>
                      <button onClick={() => setEditing(null)} className="rounded border border-border-card px-3 py-1 text-xs">取消</button>
                      <button onClick={() => window.confirm(`删除需求簇“${c.name}”?卡片和观察会保留,只是解除关联。`) && run(() => api(`/clusters/${c.id}`, "DELETE"))}
                        className="ml-auto rounded border border-error px-3 py-1 text-xs text-error">删除</button>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="font-semibold">{c.name}</div>
                      {c.note && <div className="mt-0.5 text-xs text-on-surface-variant">{c.note}</div>}
                    </div>
                    <button onClick={() => { setEditing(c.id); setDraft({ name: c.name, note: c.note }); }} className="text-outline hover:text-on-surface" title="编辑">
                      <span className="material-symbols-outlined text-[18px]">edit</span>
                    </button>
                  </div>
                )}
                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-on-surface-variant">
                  <span className={ready ? "text-success" : "text-secondary"}>{c.stats.count} 个产品{ready ? "" : `(还差 ${3 - c.stats.count} 个)`}</span>
                  <span>MRR ≥ $1k:{c.stats.paying_count}</span>
                  <span>MRR 中位数 {usd(c.stats.mrr_median)}</span>
                  <span>区间 {usd(c.stats.mrr_min)}–{usd(c.stats.mrr_max)}</span>
                  {c.observations > 0 && <span>{c.observations} 条生活观察</span>}
                </div>
                <div className="mt-2 flex flex-wrap gap-1">
                  {c.products.map((p) => (
                    <span key={p.slug} className="group flex items-center gap-1 rounded bg-surface px-2 py-0.5 text-xs">
                      <Link to={productHref(p.slug)} className="hover:underline">{p.name}</Link>
                      <span className="text-outline">{usd(p.mrr)}</span>
                      <button onClick={() => run(() => api(`/clusters/${c.id}/products/${encodeURIComponent(p.slug)}`, "DELETE"))}
                        className="hidden text-outline hover:text-error group-hover:inline" title="移出">×</button>
                    </span>
                  ))}
                </div>
                <div className="mt-3 flex items-center justify-between">
                  <span className="text-xs text-outline">更新于 {day(c.updated_at)}</span>
                  {c.card ? (
                    <Link to={cardHref(c.card.id)} className={`rounded border px-3 py-1 text-xs ${STATUS_STYLE[c.card.status]}`}>
                      查看卡片 · {STATUS_LABEL[c.card.status]}
                    </Link>
                  ) : (
                    <button onClick={() => newCard(c.id)}
                      className={`rounded px-3 py-1 text-xs font-semibold ${ready ? "bg-primary-container text-on-primary" : "border border-border-card text-on-surface-variant"}`}>
                      写需求卡片
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}
