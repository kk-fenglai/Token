import {
  Bar, CartesianGrid, ComposedChart, Cell, Legend, Line, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import type { SavingsMonth } from "../api/types";
import { useI18n } from "../i18n";
import { formatUSD } from "../lib/format";

const AXIS = { stroke: "#717881", fontSize: 12 };

export default function SavingsChart({ points }: { points: SavingsMonth[] }) {
  const { t } = useI18n();
  if (!points.length) return null;
  const fee = points.find((p) => p.fee > 0)?.fee ?? 0;

  return (
    <ResponsiveContainer width="100%" height={260}>
      <ComposedChart data={points} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="#e1e4e8" vertical={false} />
        <XAxis dataKey="month" tickLine={false} axisLine={false} tick={AXIS} />
        <YAxis yAxisId="l" tickLine={false} axisLine={false} tick={AXIS}
          tickFormatter={(v: number) => `$${v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v}`} />
        <YAxis yAxisId="r" orientation="right" tickLine={false} axisLine={false} tick={AXIS}
          tickFormatter={(v: number) => `$${v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v}`} />
        <Tooltip
          contentStyle={{ background: "#1a1c1e", border: "none", borderRadius: 8, color: "#fff", fontSize: 12 }}
          formatter={(value: number, name: string) => [formatUSD(value), name]}
          labelFormatter={(label: string) => {
            const p = points.find((x) => x.month === label);
            const tags = [p?.partial && t("savings.tagPartial"), p?.data_missing && t("savings.tagMissing")]
              .filter(Boolean).join(" · ");
            return tags ? `${label} (${tags})` : label;
          }}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        {fee > 0 && (
          <ReferenceLine yAxisId="l" y={fee} stroke="#974800" strokeDasharray="4 4"
            label={{ value: t("savings.chartFee", { fee }), position: "insideTopRight", fontSize: 11, fill: "#974800" }} />
        )}
        <Bar yAxisId="l" dataKey="api_cost" name={t("savings.chartBar")} radius={[3, 3, 0, 0]}>
          {points.map((p) => (
            <Cell
              key={p.month}
              fill={p.data_missing ? "#c0c7d1" : p.saved >= 0 ? "#1b6d43" : "#ba1a1a"}
              fillOpacity={p.partial ? 0.55 : 1}
            />
          ))}
        </Bar>
        <Line yAxisId="r" type="monotone" dataKey="cumulative_saved" name={t("savings.chartLine")}
          stroke="#0F6EAD" strokeWidth={2} dot={{ r: 3 }} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
