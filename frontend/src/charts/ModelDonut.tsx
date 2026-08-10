import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import type { ModelItem } from "../api/types";
import { FAMILY_COLORS, FAMILY_LABELS, formatTokens, formatUSD } from "../lib/format";

export default function ModelDonut({ items, mode }: { items: ModelItem[]; mode: "tokens" | "cost" }) {
  const data = items
    .filter((x) => (mode === "tokens" ? x.tokens > 0 : x.cost > 0))
    .map((x) => ({
      name: FAMILY_LABELS[x.family] ?? x.family,
      family: x.family,
      value: mode === "tokens" ? x.tokens : x.cost,
      share: mode === "tokens" ? x.token_share : x.cost_share,
    }));

  return (
    <div className="flex items-center gap-6">
      <ResponsiveContainer width="55%" height={220}>
        <PieChart>
          <Pie data={data} dataKey="value" innerRadius={58} outerRadius={90} paddingAngle={2} strokeWidth={0}>
            {data.map((d) => (
              <Cell key={d.family} fill={FAMILY_COLORS[d.family] ?? "#E8833A"} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{ background: "#1a1c1e", border: "none", borderRadius: 8, color: "#fff", fontSize: 12 }}
            formatter={(value: number, name: string) => [
              mode === "tokens" ? formatTokens(value) : formatUSD(value),
              name,
            ]}
          />
        </PieChart>
      </ResponsiveContainer>
      <ul className="flex-1 space-y-2 text-sm">
        {data.map((d) => (
          <li key={d.family} className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: FAMILY_COLORS[d.family] ?? "#E8833A" }} />
            <span className="font-medium">{d.name}</span>
            <span className="ml-auto text-on-surface-variant">
              {mode === "tokens" ? formatTokens(d.value) : formatUSD(d.value)}
            </span>
            <span className="w-12 text-right font-mono text-xs text-outline">
              {(d.share * 100).toFixed(1)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
