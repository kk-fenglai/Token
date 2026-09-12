import { useState } from "react";
import {
  Bar, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import type { TrendPoint } from "../api/types";
import { useI18n } from "../i18n";
import { useMoney } from "../lib/currency";
import { formatTokens, SERIES_COLORS, SERIES_LABELS } from "../lib/format";

const SERIES = ["input", "output", "cache_write", "cache_read"] as const;

export default function TrendChart({ points, granularity }: { points: TrendPoint[]; granularity: "day" | "month" }) {
  const { t } = useI18n();
  const { money } = useMoney();
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const costName = t("common.virtualCost");

  const data = points.map((p) => ({
    ...p,
    label: granularity === "day" ? p.bucket.slice(5) : p.bucket,
  }));

  function toggle(key: string) {
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  return (
    <ResponsiveContainer width="100%" height={300}>
      <ComposedChart data={data} margin={{ top: 4, right: 8, left: 8, bottom: 0 }}>
        <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#404750" }} tickLine={false} axisLine={{ stroke: "#e1e4e8" }} />
        <YAxis yAxisId="tokens" tickFormatter={formatTokens} tick={{ fontSize: 11, fill: "#404750" }} tickLine={false} axisLine={false} width={48} />
        <YAxis yAxisId="cost" orientation="right" tickFormatter={(v: number) => money(v, 0)} tick={{ fontSize: 11, fill: "#974800" }} tickLine={false} axisLine={false} width={48} />
        <Tooltip
          contentStyle={{ background: "#1a1c1e", border: "none", borderRadius: 8, color: "#fff", fontSize: 12 }}
          formatter={(value: number, name: string) =>
            name === costName ? [money(value), name] : [formatTokens(value), name]
          }
        />
        <Legend
          wrapperStyle={{ fontSize: 12, cursor: "pointer" }}
          onClick={(e) => {
            const key = SERIES.find((s) => SERIES_LABELS[s] === e.value);
            if (key) toggle(key);
          }}
        />
        {SERIES.map((key) => (
          <Bar
            key={key}
            yAxisId="tokens"
            dataKey={key}
            name={SERIES_LABELS[key]}
            stackId="tokens"
            fill={SERIES_COLORS[key]}
            hide={hidden.has(key)}
            maxBarSize={28}
          />
        ))}
        <Line
          yAxisId="cost"
          dataKey="cost"
          name={costName}
          stroke="#974800"
          strokeWidth={2}
          dot={false}
          hide={hidden.has("cost")}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
