import { useNavigate } from "react-router-dom";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ProjectTopItem } from "../api/types";
import { formatTokens, formatUSD } from "../lib/format";

export default function ProjectBars({ items }: { items: ProjectTopItem[] }) {
  const navigate = useNavigate();
  const data = items.map((x) => ({ ...x }));
  const height = Math.max(220, data.length * 36 + 20);

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ top: 0, right: 24, left: 8, bottom: 0 }}>
        <XAxis type="number" tickFormatter={formatTokens} tick={{ fontSize: 11, fill: "#404750" }} tickLine={false} axisLine={{ stroke: "#e1e4e8" }} />
        <YAxis
          type="category"
          dataKey="name"
          width={190}
          tick={{ fontSize: 12, fill: "#191c20" }}
          tickLine={false}
          axisLine={false}
        />
        <Tooltip
          cursor={{ fill: "rgba(15,110,173,0.06)" }}
          contentStyle={{ background: "#1a1c1e", border: "none", borderRadius: 8, color: "#fff", fontSize: 12 }}
          formatter={(value: number, _name, entry) => [
            `${formatTokens(value)} tokens · ${formatUSD((entry?.payload as ProjectTopItem)?.cost ?? 0)}`,
            "本月消耗",
          ]}
        />
        <Bar
          dataKey="tokens"
          fill="#0F6EAD"
          radius={[0, 4, 4, 0]}
          maxBarSize={20}
          cursor="pointer"
          onClick={(entry) => {
            const p = (entry as unknown as { payload?: ProjectTopItem })?.payload ?? (entry as unknown as ProjectTopItem);
            if (p?.path) navigate(`/projects/detail?path=${encodeURIComponent(p.path)}`);
          }}
        >
          {data.map((d) => (
            <Cell key={d.path} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
