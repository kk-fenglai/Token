import { Link, useSearchParams } from "react-router-dom";
import { useApi } from "../api/useApi";
import { STATUS_LABEL, cardHref, day, productHref, usd, type Status } from "../lib/ideas";

interface Results {
  products: { slug: string; name: string; description: string | null; mrr: number | null; category: string | null }[];
  cards: { id: number; need: string; status: Status }[];
  observations: { id: number; text: string; created_at: string }[];
}

export default function IdeasSearch() {
  const [params] = useSearchParams();
  const q = params.get("q") ?? "";
  const res = useApi<Results>(q ? `/api/ideas/search?q=${encodeURIComponent(q)}` : null, [q]);
  const r = res.data;
  const empty = r && !r.products.length && !r.cards.length && !r.observations.length;

  return (
    <div className="space-y-6">
      <h3 className="text-base font-semibold">搜索“{q}”</h3>
      {empty && <p className="text-sm text-on-surface-variant">没有结果。产品数据多为英文,可以试试英文关键词。</p>}
      {r && r.cards.length > 0 && (
        <section>
          <h4 className="mb-2 text-sm font-semibold">需求卡片</h4>
          <ul className="space-y-1 text-sm">
            {r.cards.map((c) => <li key={c.id}><Link to={cardHref(c.id)} className="text-primary hover:underline">{c.need || "未命名需求"}</Link> <span className="text-xs text-outline">{STATUS_LABEL[c.status]}</span></li>)}
          </ul>
        </section>
      )}
      {r && r.observations.length > 0 && (
        <section>
          <h4 className="mb-2 text-sm font-semibold">生活观察</h4>
          <ul className="space-y-1 text-sm">
            {r.observations.map((o) => <li key={o.id}><span className="mr-2 text-xs text-outline">{day(o.created_at)}</span>{o.text}</li>)}
          </ul>
          <Link to="/ideas/inbox" className="text-xs text-primary hover:underline">去生活观察</Link>
        </section>
      )}
      {r && r.products.length > 0 && (
        <section>
          <h4 className="mb-2 text-sm font-semibold">产品</h4>
          <ul className="space-y-1 text-sm">
            {r.products.map((p) => (
              <li key={p.slug} className="flex gap-3">
                <Link to={productHref(p.slug)} className="font-medium text-primary hover:underline">{p.name}</Link>
                <span className="font-mono text-xs">{usd(p.mrr)}</span>
                <span className="flex-1 truncate text-xs text-on-surface-variant">{p.description}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
