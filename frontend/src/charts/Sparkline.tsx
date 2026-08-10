import { Area, AreaChart, ResponsiveContainer } from "recharts";
import type { SparkPoint } from "../api/types";

export default function Sparkline({ points }: { points: SparkPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={56}>
      <AreaChart data={points} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="sparkFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#0F6EAD" stopOpacity={0.25} />
            <stop offset="100%" stopColor="#0F6EAD" stopOpacity={0} />
          </linearGradient>
        </defs>
        <Area type="monotone" dataKey="tokens" stroke="#0F6EAD" strokeWidth={2} fill="url(#sparkFill)" isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}
