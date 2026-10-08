import { useEffect, useRef, useState } from "react";
import { api, errorText, type ClusterSummary } from "../../lib/ideas";

/** "归入需求簇" — pick an existing cluster or name a new one, for one product. */
export default function ClusterPicker({ slug, inClusters, onChange, compact }: {
  slug: string;
  inClusters: number[];
  onChange: () => void;
  compact?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [clusters, setClusters] = useState<ClusterSummary[] | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    api<ClusterSummary[]>("/clusters").then(setClusters).catch((e) => setError(errorText(e)));
    const close = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  async function toggle(id: number, present: boolean) {
    try {
      await api(`/clusters/${id}/products/${encodeURIComponent(slug)}`, present ? "DELETE" : "PUT");
      setClusters(await api<ClusterSummary[]>("/clusters"));
      onChange();
    } catch (e) { setError(errorText(e)); }
  }

  async function create() {
    if (!name.trim()) return;
    try {
      await api("/clusters", "POST", { name: name.trim(), slug });
      setName("");
      setClusters(await api<ClusterSummary[]>("/clusters"));
      onChange();
    } catch (e) { setError(errorText(e)); }
  }

  return (
    <div ref={box} className="relative inline-block">
      <button onClick={() => setOpen((o) => !o)} title="归入需求簇"
        className={`flex items-center gap-1 rounded border px-2 py-1 text-xs ${
          inClusters.length ? "border-primary-container text-primary-container" : "border-border-card text-on-surface-variant hover:bg-surface"}`}>
        <span className="material-symbols-outlined text-[16px]">workspaces</span>
        {compact ? (inClusters.length || "") : inClusters.length ? `已在 ${inClusters.length} 个簇` : "归入需求簇"}
      </button>
      {open && (
        <div className="absolute right-0 z-20 mt-1 w-72 rounded border border-border-card bg-surface-card p-3 text-sm shadow-float">
          <div className="mb-2 text-xs font-semibold text-on-surface-variant">这个产品在解决哪个需求?</div>
          <div className="max-h-56 space-y-1 overflow-auto">
            {clusters === null && <div className="text-xs text-outline">加载中…</div>}
            {clusters?.length === 0 && <div className="text-xs text-outline">还没有需求簇,在下面新建一个。</div>}
            {clusters?.map((c) => {
              const present = c.products.some((p) => p.slug === slug);
              return (
                <label key={c.id} className="flex cursor-pointer items-center gap-2 rounded px-1 py-1 hover:bg-surface">
                  <input type="checkbox" checked={present} onChange={() => toggle(c.id, present)} />
                  <span className="flex-1 truncate">{c.name}</span>
                  <span className="text-xs text-outline">{c.stats.count}</span>
                </label>
              );
            })}
          </div>
          <div className="mt-2 flex gap-1 border-t border-border-card pt-2">
            <input value={name} onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === "Enter" && create()}
              placeholder="新需求簇:谁想完成什么" className="flex-1 rounded border border-border-card bg-surface px-2 py-1 text-xs" />
            <button onClick={create} className="rounded bg-primary-container px-2 py-1 text-xs font-semibold text-on-primary">新建</button>
          </div>
          {error && <div className="mt-2 text-xs text-error">{error}</div>}
        </div>
      )}
    </div>
  );
}
