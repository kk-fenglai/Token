import { useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../api/useApi";
import { api, day, errorText, productHref, usd, type ClusterSummary, type Observation } from "../lib/ideas";

interface SearchHit { slug: string; name: string; description: string | null; mrr: number | null; category: string | null }

export default function IdeasInbox() {
  const obs = useApi<Observation[]>("/api/ideas/observations");
  const clusters = useApi<ClusterSummary[]>("/api/ideas/clusters");
  const [text, setText] = useState("");
  const [tags, setTags] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [lookup, setLookup] = useState<{ id: number; q: string; hits: SearchHit[] | null } | null>(null);

  async function add() {
    if (!text.trim()) return;
    try {
      await api("/observations", "POST", { text: text.trim(), tags: tags.split(/[,,\s]+/).filter(Boolean) });
      setText("");
      setTags("");
      obs.retry();
    } catch (e) { setError(errorText(e)); }
  }

  async function search(o: Observation, q: string) {
    setLookup({ id: o.id, q, hits: null });
    try {
      const res = await api<{ products: SearchHit[] }>(`/search?q=${encodeURIComponent(q)}`);
      setLookup({ id: o.id, q, hits: res.products });
    } catch (e) { setError(errorText(e)); }
  }

  async function link(o: Observation, clusterId: number | null) {
    try { await api(`/observations/${o.id}`, "PUT", { cluster_id: clusterId }); obs.retry(); }
    catch (e) { setError(errorText(e)); }
  }

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-base font-semibold">生活观察</h3>
        <p className="mt-0.5 max-w-3xl text-xs text-on-surface-variant">
          反方向的入口:先在生活里看到一个麻烦,再回到数据里查有没有人为它付钱。有付费信号就关联到需求簇。
        </p>
      </div>

      <section className="rounded border border-border-card bg-surface-card p-4 shadow-card">
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2}
          onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) add(); }}
          placeholder="一句话:谁在什么时候遇到了什么麻烦。比如:楼下理发店老板每天用微信一条条回复预约"
          className="w-full rounded border border-border-card bg-surface px-3 py-2 text-sm" />
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="标签(可选,逗号分隔):小商家, 预约"
            className="min-w-[240px] flex-1 rounded border border-border-card bg-surface px-3 py-1.5 text-sm" />
          <span className="text-xs text-outline">Ctrl + Enter 保存</span>
          <button onClick={add} className="rounded bg-primary-container px-4 py-1.5 text-sm font-semibold text-on-primary">记下</button>
        </div>
        {error && <div className="mt-2 text-xs text-error">{error}</div>}
      </section>

      <div className="space-y-2">
        {obs.data?.length === 0 && <p className="text-sm text-on-surface-variant">还没有观察。目标是每周至少 3 条。</p>}
        {obs.data?.map((o) => (
          <div key={o.id} className="rounded border border-border-card bg-surface-card p-3 shadow-card">
            <div className="flex items-start gap-3">
              <span className="w-12 shrink-0 pt-0.5 text-xs text-outline">{day(o.created_at)}</span>
              <div className="flex-1">
                <div className="whitespace-pre-wrap text-sm">{o.text}</div>
                {o.tags.length > 0 && (
                  <div className="mt-1 flex flex-wrap gap-1">{o.tags.map((t) => <span key={t} className="rounded bg-surface px-1.5 text-[11px] text-on-surface-variant">{t}</span>)}</div>
                )}
              </div>
              <select value={o.cluster_id ?? ""} onChange={(e) => link(o, e.target.value ? Number(e.target.value) : null)}
                className="rounded border border-border-card bg-surface px-2 py-1 text-xs">
                <option value="">未关联需求簇</option>
                {clusters.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
              <button onClick={() => search(o, o.tags[0] ?? o.text.slice(0, 12))} className="rounded border border-border-card px-2 py-1 text-xs hover:bg-surface">查付费信号</button>
              <button onClick={() => window.confirm("删除这条观察?") && api(`/observations/${o.id}`, "DELETE").then(obs.retry)}
                className="text-outline hover:text-error" title="删除">
                <span className="material-symbols-outlined text-[18px]">delete</span>
              </button>
            </div>
            {lookup?.id === o.id && (
              <div className="mt-3 rounded bg-surface p-3">
                <div className="flex items-center gap-2 text-xs">
                  <span>在本机产品库里搜:</span>
                  <input value={lookup.q} onChange={(e) => setLookup({ ...lookup, q: e.target.value })}
                    onKeyDown={(e) => e.key === "Enter" && search(o, lookup.q)}
                    className="rounded border border-border-card bg-surface-card px-2 py-1" />
                  <span className="text-outline">产品数据多为英文,可以换英文关键词,比如 booking、salon</span>
                  <button onClick={() => setLookup(null)} className="ml-auto text-outline">收起</button>
                </div>
                {lookup.hits === null ? <div className="mt-2 text-xs text-outline">搜索中…</div> : lookup.hits.length === 0 ? (
                  <div className="mt-2 text-xs text-on-surface-variant">没有找到相关产品:可能没人为它付钱,也可能是关键词不对。</div>
                ) : (
                  <ul className="mt-2 space-y-1 text-sm">
                    {lookup.hits.map((h) => (
                      <li key={h.slug} className="flex gap-3">
                        <Link to={productHref(h.slug)} className="font-medium text-primary hover:underline">{h.name}</Link>
                        <span className="font-mono text-xs">{usd(h.mrr)}</span>
                        <span className="flex-1 truncate text-xs text-on-surface-variant">{h.description}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
