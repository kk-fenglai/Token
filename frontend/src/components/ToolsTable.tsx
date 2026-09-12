import type { ToolsBreakdown } from "../api/types";
import { useI18n } from "../i18n";
import { useMoney } from "../lib/currency";
import { formatTokens } from "../lib/format";

export default function ToolsTable({ data, compact = false }: { data: ToolsBreakdown; compact?: boolean }) {
  const { t } = useI18n();
  const { money } = useMoney();
  const rows = compact ? data.tools.slice(0, 8) : data.tools;
  const maxShare = Math.max(...data.tools.map((x) => x.cost_share), 0.0001);
  return (
    <div className="space-y-3">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[520px] text-sm">
          <thead>
            <tr className="border-b border-border-card text-left text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
              <th className="py-2 pr-3">{t("insights.colTool")}</th>
              <th className="px-3 py-2 text-right">{t("insights.colCalls")}</th>
              {!compact && <th className="px-3 py-2 text-right">{t("insights.colMessages")}</th>}
              <th className="px-3 py-2 text-right">{t("insights.colOutput")}</th>
              <th className="px-3 py-2 text-right">{t("insights.colCost")}</th>
              <th className="px-3 py-2">{t("insights.colShare")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((x) => (
              <tr key={x.name} className="border-b border-border-card/60 last:border-0">
                <td className="py-2 pr-3 font-mono text-xs font-medium">{x.name}</td>
                <td className="px-3 py-2 text-right font-mono text-xs">{x.calls.toLocaleString()}</td>
                {!compact && <td className="px-3 py-2 text-right font-mono text-xs">{x.messages.toLocaleString()}</td>}
                <td className="px-3 py-2 text-right font-mono text-xs">{formatTokens(x.output_tokens)}</td>
                <td className="px-3 py-2 text-right font-mono text-xs font-semibold">{money(x.cost)}</td>
                <td className="px-3 py-2">
                  <div className="flex items-center gap-2">
                    <div className="h-2 flex-1 rounded-full bg-surface">
                      <div className="h-2 rounded-full bg-primary-container" style={{ width: `${Math.max((x.cost_share / maxShare) * 100, 1)}%` }} />
                    </div>
                    <span className="w-12 text-right font-mono text-xs">{(x.cost_share * 100).toFixed(1)}%</span>
                  </div>
                </td>
              </tr>
            ))}
            <tr className="border-t border-border-card text-on-surface-variant">
              <td className="py-2 pr-3 text-xs">{t("insights.textOnly")}</td>
              <td className="px-3 py-2 text-right font-mono text-xs">—</td>
              {!compact && <td className="px-3 py-2 text-right font-mono text-xs">{data.text_only.messages.toLocaleString()}</td>}
              <td className="px-3 py-2 text-right font-mono text-xs">{formatTokens(data.text_only.output_tokens)}</td>
              <td className="px-3 py-2 text-right font-mono text-xs">{money(data.text_only.cost)}</td>
              <td className="px-3 py-2 font-mono text-xs">
                {data.totals.cost ? `${((data.text_only.cost / data.totals.cost) * 100).toFixed(1)}%` : "—"}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      {data.subagents.events > 0 && (
        <p className="text-xs text-on-surface-variant">
          {t("insights.subagents", { pct: (data.subagents.cost_share * 100).toFixed(0), cost: money(data.subagents.cost) })}
          {" · "}
          {data.subagents.by_agent.map((a) => `${a.agent} ${money(a.cost)}`).join(" · ")}
        </p>
      )}
    </div>
  );
}
