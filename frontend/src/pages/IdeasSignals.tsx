import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useApi } from "../api/useApi";
import ClusterPicker from "../components/ideas/ClusterPicker";
import { AUDIENCE_LABEL, api, errorText, num, pct, productHref, usd, type ProductList } from "../lib/ideas";

const VIEWS = [
  { key: "new", label: "本周新增" },
  { key: "growth", label: "30 天增长最快" },
  { key: "todo", label: "未标记" },
  { key: "interested", label: "感兴趣" },
  { key: "ignored", label: "已忽略" },
];

export default function IdeasSignals() {
  const [params, setParams] = useSearchParams();
  const view = params.get("view") ?? "growth";
  const [q, setQ] = useState(params.get("q") ?? "");
  const [category, setCategory] = useState(params.get("category") ?? "");
  const [audience, setAudience] = useState("");
  const [minMrr, setMinMrr] = useState("1000");
  const [maxMrr, setMaxMrr] = useState("20000");
  const [minCustomers, setMinCustomers] = useState("");
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setPage(1), [view, q, category, audience, minMrr, maxMrr, minCustomers]);

  const path = useMemo(() => {
    const s = new URLSearchParams({ page: String(page), limit: "50" });
    if (view === "new") { s.set("view", "new"); s.set("sort", "new"); }
    else if (view === "todo") s.set("view", "todo");
    else if (view === "interested" || view === "ignored") s.set("mark", view);
    s.set("sort", view === "new" ? "new" : "growth");
    if (q) s.set("q", q);
    if (category) s.set("category", category);
    if (audience) s.set("audience", audience);
    // The MRR band narrows the scan views; "new" and my own marks show everything.
    const banded = view === "growth" || view === "todo";
    if (banded) {
      if (minMrr) s.set("min_mrr", minMrr);
      if (maxMrr) s.set("max_mrr", maxMrr);
    }
    if (minCustomers) s.set("min_customers", minCustomers);
    return `/api/ideas/products?${s}`;
  }, [view, q, category, audience, minMrr, maxMrr, minCustomers, page]);

  const list = useApi<ProductList>(path);
  const data = list.data;

  async function mark(slug: string, m: "interested" | "ignored" | null) {
    try {
      await api(`/products/${encodeURIComponent(slug)}/mark`, "PUT", { mark: m });
      list.retry();
    } catch (e) { setError(errorText(e)); }
  }

  const input = "rounded border border-border-card bg-surface px-2 py-1.5 text-sm";

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-semibold">付费信号</h3>
        <p className="mt-0.5 max-w-3xl text-xs text-on-surface-variant">
          每个产品只问一个问题:它背后是不是一个生活里的需求?感兴趣就归入需求簇,不相关就忽略,忽略的不再出现。
          优先看 MRR $1k–$20k、客户多、客单价低、卖给个人或小商家的产品。
        </p>
      </div>

      <div className="flex flex-wrap gap-1">
        {VIEWS.map((v) => (
          <button key={v.key} onClick={() => setParams({ view: v.key })}
            className={`rounded-full border px-3 py-1 text-sm ${view === v.key ? "border-primary-container bg-primary-container text-on-primary" : "border-border-card text-on-surface-variant hover:bg-surface"}`}>
            {v.label}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap items-end gap-3 rounded border border-border-card bg-surface-card p-3 shadow-card text-xs text-on-surface-variant">
        <label>关键词<br /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="名称、描述、目标用户" className={`${input} w-48`} /></label>
        <label>分类<br />
          <select value={category} onChange={(e) => setCategory(e.target.value)} className={input}>
            <option value="">全部</option>
            {data?.categories.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
        <label>客户类型<br />
          <select value={audience} onChange={(e) => setAudience(e.target.value)} className={input}>
            <option value="">全部</option><option value="b2c">B2C</option><option value="b2b">B2B</option><option value="both">两者</option>
          </select>
        </label>
        <label>MRR 下限 ($)<br /><input type="number" value={minMrr} onChange={(e) => setMinMrr(e.target.value)} className={`${input} w-24`} disabled={!(view === "growth" || view === "todo")} /></label>
        <label>MRR 上限 ($)<br /><input type="number" value={maxMrr} onChange={(e) => setMaxMrr(e.target.value)} className={`${input} w-24`} disabled={!(view === "growth" || view === "todo")} /></label>
        <label>客户数 ≥<br /><input type="number" value={minCustomers} onChange={(e) => setMinCustomers(e.target.value)} className={`${input} w-20`} /></label>
        <span className="ml-auto self-center">{data ? `共 ${data.total} 个` : "…"}</span>
      </div>
      {error && <div className="text-xs text-error">{error}</div>}

      <div className="overflow-x-auto rounded border border-border-card bg-surface-card shadow-card">
        <table className="w-full text-sm">
          <thead className="whitespace-nowrap border-b border-border-card bg-surface text-left text-xs text-on-surface-variant">
            <tr>
              <th className="px-3 py-2">产品</th>
              <th className="px-3 py-2 text-right">MRR</th>
              <th className="px-3 py-2 text-right">30 天增长</th>
              <th className="px-3 py-2 text-right">客户数</th>
              <th className="px-3 py-2 text-right">客单价/月</th>
              <th className="px-3 py-2">类型</th>
              <th className="px-3 py-2 text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            {list.loading && !data && <tr><td colSpan={7} className="px-3 py-8 text-center text-on-surface-variant">加载中…</td></tr>}
            {data && data.items.length === 0 && (
              <tr><td colSpan={7} className="px-3 py-8 text-center text-on-surface-variant">
                没有符合条件的产品。{data.total === 0 && view !== "ignored" ? <>还没同步过数据?去 <Link to="/ideas/settings" className="text-primary underline">数据源</Link> 立即同步。</> : null}
              </td></tr>
            )}
            {data?.items.map((p) => {
              const arpu = p.mrr && p.customers ? p.mrr / p.customers : null;
              const persona = p.detail?.target_persona;
              return (
                <tr key={p.slug} className={`border-b border-border-card last:border-0 ${p.mark === "interested" ? "bg-[#f3f8fc]" : ""}`}>
                  <td className="min-w-[240px] max-w-[420px] px-3 py-2">
                    <div className="flex items-center gap-2">
                      {p.icon ? <img src={p.icon} alt="" className="h-5 w-5 rounded" referrerPolicy="no-referrer" /> : <span className="h-5 w-5 rounded bg-surface" />}
                      <Link to={productHref(p.slug)} className="font-medium hover:underline">{p.name}</Link>
                      {p.category && <span className="rounded bg-surface px-1.5 text-[11px] text-outline">{p.category}</span>}
                    </div>
                    <div className="mt-0.5 line-clamp-2 text-xs text-on-surface-variant">{persona ? `目标用户:${persona}` : p.description ?? ""}</div>
                  </td>
                  <td className="px-3 py-2 text-right font-mono">{usd(p.mrr)}</td>
                  <td className={`px-3 py-2 text-right font-mono ${(p.growth_30d ?? 0) > 0 ? "text-success" : (p.growth_30d ?? 0) < 0 ? "text-error" : ""}`}>{pct(p.growth_30d)}</td>
                  <td className="px-3 py-2 text-right font-mono">{num(p.customers)}</td>
                  <td className="px-3 py-2 text-right font-mono">{usd(arpu)}</td>
                  <td className="px-3 py-2 text-xs">{p.target_audience ? AUDIENCE_LABEL[p.target_audience] ?? p.target_audience : "—"}</td>
                  <td className="px-3 py-2">
                    <div className="flex items-center justify-end gap-1">
                      <button onClick={() => mark(p.slug, p.mark === "interested" ? null : "interested")} title="感兴趣"
                        className={`rounded border px-2 py-1 text-xs ${p.mark === "interested" ? "border-success text-success" : "border-border-card text-on-surface-variant hover:bg-surface"}`}>
                        <span className="material-symbols-outlined align-middle text-[16px]">star</span>
                      </button>
                      <ClusterPicker slug={p.slug} inClusters={(p.clusters as number[]) ?? []} onChange={list.retry} compact />
                      <button onClick={() => mark(p.slug, p.mark === "ignored" ? null : "ignored")} title={p.mark === "ignored" ? "取消忽略" : "忽略"}
                        className="rounded border border-border-card px-2 py-1 text-xs text-on-surface-variant hover:bg-surface">
                        <span className="material-symbols-outlined align-middle text-[16px]">{p.mark === "ignored" ? "undo" : "visibility_off"}</span>
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {data && data.total > data.limit && (
        <div className="flex items-center justify-center gap-3 text-sm">
          <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="rounded border border-border-card px-3 py-1 disabled:opacity-40">上一页</button>
          <span>{page} / {Math.ceil(data.total / data.limit)}</span>
          <button disabled={page * data.limit >= data.total} onClick={() => setPage(page + 1)} className="rounded border border-border-card px-3 py-1 disabled:opacity-40">下一页</button>
        </div>
      )}
    </div>
  );
}
