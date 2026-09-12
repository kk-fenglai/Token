import {
  Bar, CartesianGrid, ComposedChart, Line, ReferenceDot, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import type { SessionMessage } from "../api/types";
import { useI18n } from "../i18n";
import { useMoney } from "../lib/currency";
import { formatTokens } from "../lib/format";

/** Context size per turn (line) against cost per turn (bars). The line is the
 *  point: it only ever grows until someone /clears, and the bars show what
 *  that growth costs each time the conversation is re-sent. */
export default function ContextChart({ messages, peak }: {
  messages: SessionMessage[];
  peak: { i: number; context: number } | null;
}) {
  const { t } = useI18n();
  const { money } = useMoney();
  const ctxName = t("sessionDetail.seriesContext");
  const costName = t("sessionDetail.seriesCost");
  const data = messages.map((m) => ({ ...m, turn: m.i + 1 }));
  return (
    <ResponsiveContainer width="100%" height={280}>
      <ComposedChart data={data} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
        <CartesianGrid stroke="#e1e4e8" vertical={false} />
        <XAxis dataKey="turn" tick={{ fontSize: 11, fill: "#404750" }} tickLine={false} axisLine={{ stroke: "#e1e4e8" }} minTickGap={24} />
        <YAxis yAxisId="ctx" tickFormatter={formatTokens} tick={{ fontSize: 11, fill: "#404750" }} tickLine={false} axisLine={false} width={52} />
        <YAxis yAxisId="cost" orientation="right" tickFormatter={(v: number) => money(v, 2)} tick={{ fontSize: 11, fill: "#974800" }} tickLine={false} axisLine={false} width={60} />
        <Tooltip
          contentStyle={{ background: "#1a1c1e", border: "none", borderRadius: 8, color: "#fff", fontSize: 12 }}
          labelFormatter={(label: number) => {
            const m = data[label - 1];
            const tools = m?.tools.length ? m.tools.join(", ") : t("sessionDetail.noTools");
            return `#${label} · ${m?.model ?? ""} · ${tools}${m?.sidechain ? ` · ${t("sessionDetail.sidechainTag")}` : ""}`;
          }}
          formatter={(value: number, name: string) => [name === costName ? money(value, 4) : formatTokens(value), name]}
        />
        <Bar yAxisId="cost" dataKey="cost" name={costName} fill="#E8833A" fillOpacity={0.7} maxBarSize={14} />
        <Line yAxisId="ctx" type="monotone" dataKey="context" name={ctxName} stroke="#0F6EAD" strokeWidth={2} dot={false} />
        {peak && (
          <ReferenceDot yAxisId="ctx" x={peak.i + 1} y={peak.context} r={5} fill="#ba1a1a" stroke="#fff" />
        )}
      </ComposedChart>
    </ResponsiveContainer>
  );
}
