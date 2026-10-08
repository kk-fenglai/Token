import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useApi } from "../api/useApi";
import {
  CARD_FIELDS, GATES, RED_FLAGS, SCORES, STATUSES, STATUS_LABEL, STATUS_STYLE, VERDICT_LABEL, VERDICT_STYLE,
  api, day, errorText, num, pct, productHref, today, usd,
  type Card, type ClusterSummary, type FlagKey, type GateKey, type ScoreKey, type Status,
} from "../lib/ideas";

type Texts = Pick<Card, "need" | "payer" | "job" | "alternative" | "life_mapping" | "validation_action" | "conclusion">;

export default function IdeasCard() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const id = Number(params.get("id") ?? 0);
  const res = useApi<Card>(id ? `/api/ideas/cards/${id}` : null, [id]);
  const clusters = useApi<ClusterSummary[]>("/api/ideas/clusters");
  const [card, setCard] = useState<Card | null>(null);
  const [texts, setTexts] = useState<Texts | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [val, setVal] = useState({ action: "", day: today(), result: "" });
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (res.data) {
      setCard(res.data);
      const { need, payer, job, alternative, life_mapping, validation_action, conclusion } = res.data;
      setTexts({ need, payer, job, alternative, life_mapping, validation_action, conclusion });
      setDirty(false);
    }
  }, [res.data]);

  async function patch(body: Record<string, unknown>) {
    setError(null);
    try {
      const c = await api<Card>(`/cards/${id}`, "PUT", body);
      setCard(c);
      return c;
    } catch (e) { setError(errorText(e)); return null; }
  }

  async function saveTexts() {
    if (!texts) return;
    if (await patch(texts)) {
      setDirty(false);
      setSaved(true);
      setTimeout(() => setSaved(false), 1500);
    }
  }

  async function setStatus(s: Status) {
    // Save pending text first so the draft rule sees the life mapping just typed.
    await patch({ ...(dirty && texts ? texts : {}), status: s }).then((c) => c && setDirty(false));
  }

  async function addValidation() {
    if (!val.action.trim()) return;
    try {
      const c = await api<Card>(`/cards/${id}/validations`, "POST", val);
      setCard(c);
      setVal({ action: "", day: today(), result: "" });
    } catch (e) { setError(errorText(e)); }
  }

  async function copyMarkdown() {
    try {
      const md = await api<string>(`/cards/${id}/markdown`);
      await navigator.clipboard.writeText(md);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch (e) { setError(errorText(e)); }
  }

  if (!id) return <div className="text-sm text-on-surface-variant">缺少卡片参数。</div>;
  if (res.error) return <div className="text-sm text-error">加载失败:{res.error}</div>;
  if (!card || !texts) return <div className="text-sm text-on-surface-variant">加载中…</div>;

  const ev = card.evaluation;
  const sug = card.suggested;
  const st = card.cluster_stats;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link to="/ideas/needs" className="inline-flex items-center gap-1 text-sm text-primary hover:underline">
          <span className="material-symbols-outlined text-[18px]">arrow_back</span>需求看板
        </Link>
        <div className="flex items-center gap-2">
          <button onClick={copyMarkdown} className="rounded border border-border-card px-3 py-1.5 text-sm hover:bg-surface">
            {copied ? "已复制" : "复制为 Markdown"}
          </button>
          <button onClick={() => window.confirm("删除这张卡片和它的验证记录?") && api(`/cards/${id}`, "DELETE").then(() => navigate("/ideas/needs"))}
            className="rounded border border-error px-3 py-1.5 text-sm text-error">删除</button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {STATUSES.map((s) => (
          <button key={s} onClick={() => s !== card.status && setStatus(s)}
            className={`rounded border px-3 py-1 text-sm ${card.status === s ? `${STATUS_STYLE[s]} font-semibold ring-1 ring-current` : "border-border-card text-on-surface-variant hover:bg-surface"}`}>
            {STATUS_LABEL[s]}
          </button>
        ))}
        <span className="ml-2 text-xs text-outline">离开草稿需要:需求簇里至少 3 个产品信号,并填好“生活映射”。</span>
      </div>
      {error && <div className="rounded bg-error-container px-3 py-2 text-sm text-on-error-container">{error}</div>}
      {card.stale && <div className="rounded bg-error-container px-3 py-2 text-sm text-on-error-container">这张卡片待验证超过 14 天没动了:做一次验证,或者给它下结论。</div>}

      <div className="grid gap-6 xl:grid-cols-3">
        <section className="space-y-4 rounded border border-border-card bg-surface-card p-4 shadow-card xl:col-span-2">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-semibold">需求卡片</h4>
            <div className="flex items-center gap-2">
              {saved && <span className="text-xs text-success">已保存</span>}
              <button onClick={saveTexts} disabled={!dirty} className="rounded bg-primary-container px-3 py-1 text-sm font-semibold text-on-primary disabled:opacity-50">保存</button>
            </div>
          </div>
          {CARD_FIELDS.slice(0, 1).map((f) => (
            <label key={f.key} className="block">
              <span className="text-xs font-semibold text-on-surface-variant">{f.label} · {f.question}</span>
              <textarea value={texts[f.key]} rows={f.rows} onChange={(e) => { setTexts({ ...texts, [f.key]: e.target.value }); setDirty(true); }}
                className="mt-1 w-full rounded border border-border-card bg-surface px-3 py-2 text-base font-semibold" />
            </label>
          ))}

          <div className="rounded border border-border-card p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-xs font-semibold text-on-surface-variant">付费信号 · 哪几个产品证明有人付钱(至少 3 个)</span>
              <select value={card.cluster_id ?? ""} onChange={(e) => patch({ cluster_id: e.target.value ? Number(e.target.value) : null })}
                className="rounded border border-border-card bg-surface px-2 py-1 text-xs">
                <option value="">未关联需求簇</option>
                {clusters.data?.map((c) => <option key={c.id} value={c.id}>{c.name}({c.stats.count})</option>)}
              </select>
            </div>
            {card.products.length === 0 ? (
              <p className="mt-2 text-xs text-on-surface-variant">关联一个需求簇后,这里会列出它的产品。</p>
            ) : (
              <>
                <div className="mt-2 text-xs text-on-surface-variant">
                  {st.count} 个产品 · MRR ≥ $1k 的 {st.paying_count} 个 · 中位数 {usd(st.mrr_median)} · 客单价中位数 {usd(st.arpu_median)}/月
                  {st.growing_share != null && ` · ${Math.round(st.growing_share * 100)}% 在增长`}
                </div>
                <table className="mt-2 w-full text-xs">
                  <tbody>
                    {card.products.map((p) => (
                      <tr key={p.slug} className="border-t border-border-card">
                        <td className="py-1"><Link to={productHref(p.slug)} className="hover:underline">{p.name}</Link></td>
                        <td className="py-1 text-right font-mono">{usd(p.mrr)}</td>
                        <td className="py-1 text-right font-mono">{num(p.customers)} 客户</td>
                        <td className="py-1 text-right font-mono">{pct(p.growth_30d)}</td>
                        <td className="py-1 text-right">{p.url && <a href={p.url} target="_blank" rel="noreferrer noopener" className="text-primary">原页面</a>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </div>

          {CARD_FIELDS.slice(1).map((f) => (
            <label key={f.key} className="block">
              <span className={`text-xs font-semibold ${f.key === "life_mapping" ? "text-secondary" : "text-on-surface-variant"}`}>
                {f.label} · {f.question}{f.key === "life_mapping" ? "(必填,没有生活映射不算完成)" : ""}
              </span>
              <textarea value={texts[f.key]} rows={f.rows} onChange={(e) => { setTexts({ ...texts, [f.key]: e.target.value }); setDirty(true); }}
                className="mt-1 w-full rounded border border-border-card bg-surface px-3 py-2 text-sm" />
            </label>
          ))}

          {card.observations.length > 0 && (
            <div>
              <div className="text-xs font-semibold text-on-surface-variant">关联的生活观察</div>
              <ul className="mt-1 space-y-1 text-sm">
                {card.observations.map((o) => <li key={o.id} className="flex gap-2"><span className="text-xs text-outline">{day(o.created_at)}</span>{o.text}</li>)}
              </ul>
            </div>
          )}
        </section>

        <div className="space-y-6">
          <section className="rounded border border-border-card bg-surface-card p-4 shadow-card">
            <div className={`text-lg font-semibold ${VERDICT_STYLE[ev.verdict]}`}>{VERDICT_LABEL[ev.verdict]}</div>
            <div className="mt-1 text-xs text-on-surface-variant">
              评分 {ev.total}/12(已评 {ev.scored}/6 项)· 门槛 {ev.gates_passed}/5 · 反面信号 {card.red_flags.length} 条
            </div>
            <div className="mt-1 text-xs text-outline">9 分以上本周验证 · 6–8 分观察 · 5 分以下放弃;每条反面信号降一档。</div>
          </section>

          <section className="rounded border border-border-card bg-surface-card p-4 shadow-card">
            <h4 className="mb-2 text-sm font-semibold">第一层 · 门槛(5 条全过)</h4>
            <div className="space-y-2">
              {GATES.map((g) => {
                const on = !!card.gates[g.key];
                const hint = sug.gates[g.key as GateKey];
                return (
                  <label key={g.key} className="flex cursor-pointer items-start gap-2 text-sm">
                    <input type="checkbox" checked={on} className="mt-1" onChange={() => patch({ gates: { ...card.gates, [g.key]: !on } })} />
                    <span>
                      {g.label}
                      {hint !== undefined && <span className={`ml-1 text-xs ${hint ? "text-success" : "text-secondary"}`}>数据{hint ? "支持" : "不支持"}</span>}
                      <span className="block text-xs text-on-surface-variant">{g.hint}</span>
                    </span>
                  </label>
                );
              })}
            </div>
          </section>

          <section className="rounded border border-border-card bg-surface-card p-4 shadow-card">
            <h4 className="mb-2 text-sm font-semibold">第二层 · 评分(每项 0–2)</h4>
            <div className="space-y-3">
              {SCORES.map((s) => {
                const cur = card.scores[s.key as ScoreKey];
                const hint = sug.scores[s.key as ScoreKey];
                return (
                  <div key={s.key}>
                    <div className="flex items-center justify-between text-sm">
                      <span>{s.label}<span className="ml-1 text-xs text-outline">依据:{s.source}</span></span>
                      {hint !== undefined && cur === undefined && (
                        <button onClick={() => patch({ scores: { ...card.scores, [s.key]: hint } })} className="text-xs text-primary">采用建议 {hint}</button>
                      )}
                    </div>
                    <div className="mt-1 grid grid-cols-3 gap-1">
                      {s.levels.map((lv, i) => (
                        <button key={i} onClick={() => patch({ scores: { ...card.scores, [s.key]: cur === i ? null : i } })}
                          className={`rounded border px-1.5 py-1 text-left text-[11px] leading-4 ${cur === i ? "border-primary-container bg-primary-container text-on-primary" : hint === i ? "border-dashed border-primary-container text-on-surface" : "border-border-card text-on-surface-variant hover:bg-surface"}`}>
                          <b>{i}</b> {lv}
                        </button>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
            <p className="mt-2 text-xs text-outline">虚线框是根据簇内数据给出的建议;生活相关的三项只能你自己判断。</p>
          </section>

          <section className="rounded border border-border-card bg-surface-card p-4 shadow-card">
            <h4 className="mb-2 text-sm font-semibold">第三层 · 反面信号(每条降一档)</h4>
            <div className="space-y-2">
              {RED_FLAGS.map((f) => {
                const on = card.red_flags.includes(f.key);
                const hint = sug.red_flags.includes(f.key as FlagKey);
                return (
                  <label key={f.key} className="flex cursor-pointer items-start gap-2 text-sm">
                    <input type="checkbox" checked={on} className="mt-1"
                      onChange={() => patch({ red_flags: on ? card.red_flags.filter((x) => x !== f.key) : [...card.red_flags, f.key] })} />
                    <span>
                      {f.label}{hint && <span className="ml-1 text-xs text-error">数据提示可能存在</span>}
                      <span className="block text-xs text-on-surface-variant">{f.hint}</span>
                    </span>
                  </label>
                );
              })}
            </div>
          </section>
        </div>
      </div>

      <section className="rounded border border-border-card bg-surface-card p-4 shadow-card">
        <h4 className="mb-3 text-sm font-semibold">验证记录</h4>
        <div className="flex flex-wrap gap-2">
          <input type="date" value={val.day} onChange={(e) => setVal({ ...val, day: e.target.value })} className="rounded border border-border-card bg-surface px-2 py-1.5 text-sm" />
          <input value={val.action} onChange={(e) => setVal({ ...val, action: e.target.value })} placeholder="做了什么,比如:找 3 位店主各聊 15 分钟"
            className="min-w-[260px] flex-1 rounded border border-border-card bg-surface px-2 py-1.5 text-sm" />
          <input value={val.result} onChange={(e) => setVal({ ...val, result: e.target.value })} placeholder="结果(可以之后再补)"
            className="min-w-[200px] flex-1 rounded border border-border-card bg-surface px-2 py-1.5 text-sm" />
          <button onClick={addValidation} className="rounded bg-primary-container px-3 py-1.5 text-sm font-semibold text-on-primary">记录</button>
        </div>
        {card.validations.length === 0 ? (
          <p className="mt-3 text-sm text-on-surface-variant">还没有验证记录。</p>
        ) : (
          <table className="mt-3 w-full text-sm">
            <tbody>
              {card.validations.map((v) => (
                <tr key={v.id} className="border-t border-border-card">
                  <td className="w-28 py-2 font-mono text-xs">{v.day}</td>
                  <td className="py-2">{v.action}</td>
                  <td className="py-2 text-on-surface-variant">{v.result || "待记录结果"}</td>
                  <td className="w-8 py-2 text-right">
                    <button onClick={() => api<Card>(`/cards/${id}/validations/${v.id}`, "DELETE").then(setCard)} className="text-outline hover:text-error" title="删除">×</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
