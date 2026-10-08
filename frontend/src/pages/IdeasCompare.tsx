import { Link, useSearchParams } from "react-router-dom";
import { useApi } from "../api/useApi";
import {
  CARD_FIELDS, GATES, RED_FLAGS, SCORES, STATUS_LABEL, VERDICT_LABEL, VERDICT_STYLE, cardHref, usd, type Card,
} from "../lib/ideas";

export default function IdeasCompare() {
  const [params, setParams] = useSearchParams();
  const ids = (params.get("ids") ?? "").split(",").filter(Boolean).slice(0, 3);
  const all = useApi<Card[]>("/api/ideas/cards");
  const picked = useApi<Card[]>(ids.length ? `/api/ideas/cards?ids=${ids.join(",")}` : null, [ids.join(",")]);
  const cards = ids.length ? picked.data ?? [] : [];

  const toggle = (id: number) => {
    const s = String(id);
    const next = ids.includes(s) ? ids.filter((x) => x !== s) : ids.length >= 3 ? ids : [...ids, s];
    setParams(next.length ? { ids: next.join(",") } : {});
  };

  const row = (label: string, render: (c: Card) => React.ReactNode, strong = false) => (
    <tr className="border-t border-border-card align-top">
      <th className="w-40 px-3 py-2 text-left text-xs font-semibold text-on-surface-variant">{label}</th>
      {cards.map((c) => <td key={c.id} className={`px-3 py-2 text-sm ${strong ? "font-semibold" : ""}`}>{render(c)}</td>)}
    </tr>
  );

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-base font-semibold">对比</h3>
        <p className="mt-0.5 text-xs text-on-surface-variant">最多选 3 张卡片并排比较,决定先做哪一个。</p>
      </div>
      <div className="flex flex-wrap gap-2">
        {all.data?.length === 0 && <span className="text-sm text-on-surface-variant">还没有卡片。</span>}
        {all.data?.map((c) => (
          <button key={c.id} onClick={() => toggle(c.id)}
            className={`rounded-full border px-3 py-1 text-sm ${ids.includes(String(c.id)) ? "border-primary-container bg-primary-container text-on-primary" : "border-border-card hover:bg-surface"}`}>
            {c.need || "未命名需求"}
          </button>
        ))}
      </div>

      {cards.length > 0 && (
        <div className="overflow-x-auto rounded border border-border-card bg-surface-card shadow-card">
          <table className="w-full table-fixed">
            <tbody>
              {row("需求", (c) => <Link to={cardHref(c.id)} className="hover:underline">{c.need || "未命名需求"}</Link>, true)}
              {row("建议", (c) => <span className={VERDICT_STYLE[c.evaluation.verdict]}>{VERDICT_LABEL[c.evaluation.verdict]}</span>, true)}
              {row("状态", (c) => STATUS_LABEL[c.status])}
              {row("评分", (c) => `${c.evaluation.total}/12`)}
              {row("门槛", (c) => `${c.evaluation.gates_passed}/5${GATES.filter((g) => !c.gates[g.key]).length ? ` · 未过:${GATES.filter((g) => !c.gates[g.key]).map((g) => g.label).join("、")}` : ""}`)}
              {SCORES.map((s) => row(s.label, (c) => (c.scores[s.key] ?? "—")))}
              {row("反面信号", (c) => c.red_flags.length ? c.red_flags.map((f) => RED_FLAGS.find((r) => r.key === f)?.label).join("、") : "无")}
              {row("付费信号", (c) => `${c.cluster_stats.count} 个产品 · 中位数 ${usd(c.cluster_stats.mrr_median)}`)}
              {CARD_FIELDS.slice(1).map((f) => row(f.label, (c) => <span className="whitespace-pre-wrap">{c[f.key] || "—"}</span>))}
              {row("验证次数", (c) => c.validations.length)}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
