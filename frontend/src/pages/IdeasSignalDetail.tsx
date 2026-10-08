import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useApi } from "../api/useApi";
import ClusterPicker from "../components/ideas/ClusterPicker";
import { AUDIENCE_LABEL, api, dateTime, errorText, num, pct, usd, type Product } from "../lib/ideas";

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  if (!value) return null;
  return (
    <div>
      <div className="text-xs font-semibold text-on-surface-variant">{label}</div>
      <div className="mt-0.5 whitespace-pre-wrap text-sm">{value}</div>
    </div>
  );
}

export default function IdeasSignalDetail() {
  const [params] = useSearchParams();
  const slug = params.get("slug") ?? "";
  const res = useApi<Product>(slug ? `/api/ideas/products/${encodeURIComponent(slug)}` : null, [slug]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const p = res.data;

  async function mark(m: "interested" | "ignored" | null) {
    try { await api(`/products/${encodeURIComponent(slug)}/mark`, "PUT", { mark: m }); res.retry(); }
    catch (e) { setError(errorText(e)); }
  }

  async function loadPublic() {
    setBusy(true);
    try { await api(`/products/${encodeURIComponent(slug)}/public-md`, "POST"); res.retry(); }
    catch (e) { setError(errorText(e)); }
    finally { setBusy(false); }
  }

  if (!slug) return <div className="text-sm text-on-surface-variant">缺少产品参数。</div>;
  if (res.error) return <div className="text-sm text-error">加载失败:{res.error}</div>;
  if (!p) return <div className="text-sm text-on-surface-variant">加载中…</div>;

  const d = p.detail ?? {};
  const arpu = p.mrr && p.customers ? p.mrr / p.customers : null;
  const clusters = (p.clusters ?? []) as { id: number; name: string }[];
  const metrics: [string, string][] = [
    ["MRR", usd(p.mrr)], ["近 30 天收入", usd(p.revenue_30d)], ["30 天增长", pct(p.growth_30d)],
    ["客户数", num(p.customers)], ["活跃订阅", num(p.active_subs)], ["客单价/月", usd(arpu)],
    ["近 30 天访客", num(p.visitors_30d)], ["客户类型", p.target_audience ? AUDIENCE_LABEL[p.target_audience] ?? p.target_audience : "—"],
  ];

  return (
    <div className="space-y-6">
      <Link to="/ideas/signals" className="inline-flex items-center gap-1 text-sm text-primary hover:underline">
        <span className="material-symbols-outlined text-[18px]">arrow_back</span>付费信号
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          {p.icon && <img src={p.icon} alt="" className="h-10 w-10 rounded" referrerPolicy="no-referrer" />}
          <div>
            <h3 className="text-lg font-semibold">{p.name}</h3>
            <div className="text-xs text-on-surface-variant">
              {p.category ?? "未分类"} · {p.payment_provider ?? "—"} 验证 · 本地首次看到 {dateTime(p.first_seen)}
            </div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button onClick={() => mark(p.mark === "interested" ? null : "interested")}
            className={`rounded border px-3 py-1.5 text-sm ${p.mark === "interested" ? "border-success text-success" : "border-border-card hover:bg-surface"}`}>
            {p.mark === "interested" ? "已感兴趣" : "感兴趣"}
          </button>
          <button onClick={() => mark(p.mark === "ignored" ? null : "ignored")} className="rounded border border-border-card px-3 py-1.5 text-sm hover:bg-surface">
            {p.mark === "ignored" ? "取消忽略" : "忽略"}
          </button>
          <ClusterPicker slug={p.slug} inClusters={clusters.map((c) => c.id)} onChange={res.retry} />
          {p.url && <a href={p.url} target="_blank" rel="noreferrer noopener" className="rounded border border-border-card px-3 py-1.5 text-sm hover:bg-surface">TrustMRR 原页面</a>}
          {p.website && <a href={p.website} target="_blank" rel="noreferrer noopener" className="rounded border border-border-card px-3 py-1.5 text-sm hover:bg-surface">产品官网</a>}
        </div>
      </div>
      {error && <div className="text-xs text-error">{error}</div>}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {metrics.map(([k, v]) => (
          <div key={k} className="rounded border border-border-card bg-surface-card px-3 py-2 shadow-card">
            <div className="text-xs text-on-surface-variant">{k}</div>
            <div className="mt-1 font-mono text-lg font-semibold">{v}</div>
          </div>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <section className="space-y-3 rounded border border-border-card bg-surface-card p-4 shadow-card lg:col-span-2">
          <h4 className="text-sm font-semibold">它在解决谁的什么问题</h4>
          <p className="text-xs text-outline">以下文字由创始人填写,只作参考,不代表事实。</p>
          <Field label="描述" value={d.description ?? p.description} />
          <Field label="目标用户" value={d.target_persona} />
          <Field label="解决的问题" value={d.problem_solved} />
          <Field label="价值主张" value={d.value_proposition} />
          <Field label="定价模式" value={d.pricing_model} />
          {!p.detail_at && (
            <div className="rounded bg-surface p-3 text-xs text-on-surface-variant">
              {p.source === "trustmrr_api"
                ? "详情会在下次同步时拉取。"
                : "没有 API Key 时只能拿到列表字段。可以读取 TrustMRR 公开的 Markdown 页面补充目标用户和渠道(1 次请求,结果存在本机)。"}
              {p.source !== "trustmrr_api" && (
                <button onClick={loadPublic} disabled={busy} className="ml-2 rounded border border-border-card bg-surface-card px-2 py-0.5 text-primary disabled:opacity-50">
                  {busy ? "读取中…" : p.public_md ? "重新读取" : "读取公开页面"}
                </button>
              )}
            </div>
          )}
          {p.public_md && (
            <details className="rounded border border-border-card p-3" open={!p.detail_at}>
              <summary className="cursor-pointer text-xs font-semibold text-on-surface-variant">公开页面原文(读取于 {dateTime(p.public_md_at)})</summary>
              <pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap font-sans text-xs leading-5">{p.public_md}</pre>
            </details>
          )}
        </section>

        <section className="space-y-4 rounded border border-border-card bg-surface-card p-4 shadow-card">
          <div>
            <h4 className="mb-2 text-sm font-semibold">所在需求簇</h4>
            {clusters.length === 0 ? <p className="text-xs text-on-surface-variant">还没归入任何需求簇。</p> : (
              <ul className="space-y-1 text-sm">
                {clusters.map((c) => <li key={c.id}><Link to={`/ideas/needs?cluster=${c.id}`} className="text-primary hover:underline">{c.name}</Link></li>)}
              </ul>
            )}
          </div>
          {(d.marketing_channels?.length ?? 0) > 0 && (
            <div>
              <h4 className="mb-2 text-sm font-semibold">获客渠道</h4>
              <div className="flex flex-wrap gap-1">{d.marketing_channels!.map((c) => <span key={c.slug} className="rounded bg-surface px-2 py-0.5 text-xs">{c.slug}</span>)}</div>
            </div>
          )}
          {(d.tech_stack?.length ?? 0) > 0 && (
            <div>
              <h4 className="mb-2 text-sm font-semibold">技术栈</h4>
              <div className="flex flex-wrap gap-1">{d.tech_stack!.map((c) => <span key={c.slug} className="rounded bg-surface px-2 py-0.5 text-xs">{c.slug}</span>)}</div>
            </div>
          )}
          <div className="space-y-1 text-xs text-on-surface-variant">
            {d.team_size && <div>团队规模:{d.team_size}</div>}
            {d.funding_status && <div>融资:{d.funding_status === "bootstrapped" ? "自筹" : "风投"}</div>}
            {d.x_followers != null && <div>创始人 X 粉丝:{num(d.x_followers)}(粉丝多可能是“靠创始人影响力获客”)</div>}
            {p.country && <div>国家/地区:{p.country}</div>}
          </div>
          {(p.snapshots?.length ?? 0) > 1 && (
            <div>
              <h4 className="mb-2 text-sm font-semibold">本机记录的 MRR</h4>
              <ul className="space-y-0.5 font-mono text-xs">
                {p.snapshots!.slice(-8).map((s) => <li key={s.day} className="flex justify-between"><span>{s.day}</span><span>{usd(s.mrr)}</span></li>)}
              </ul>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
