import { Link } from "react-router-dom";
import type { ModelUsage } from "../api/types";
import { useI18n } from "../i18n";
import { useMoney } from "../lib/currency";
import { formatTokens, modelColorMap, modelLabel } from "../lib/format";

interface Props {
  items: ModelUsage[];
  /** Link each row to Usage Logs filtered on that exact model. */
  linkToLogs?: boolean;
  /** Hide the unit-rate columns when space is tight (project detail). */
  compact?: boolean;
}

export default function ModelTable({ items, linkToLogs = true, compact = false }: Props) {
  const { t } = useI18n();
  const { money, unit, precise, symbol } = useMoney();
  const colors = modelColorMap(items);
  const totalCost = items.reduce((s, x) => s + x.cost, 0);
  const totalCalls = items.reduce((s, x) => s + x.events, 0);
  const totalTokens = items.reduce((s, x) => s + x.tokens, 0);

  if (!items.length) {
    return <div className="py-8 text-center text-sm text-on-surface-variant">{t("modelTable.empty")}</div>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] text-sm">
        <thead>
          <tr className="border-b border-border-card text-left text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
            <th className="py-2 pr-3">{t("modelTable.model")}</th>
            <th className="px-3 py-2 text-right">{t("modelTable.apiCalls")}</th>
            <th className="px-3 py-2 text-right">{t("common.tokens")}</th>
            {!compact && (
              <th className="px-3 py-2 text-right">
                {t("modelTable.unitPrice")}
                <div className="font-normal normal-case text-outline">{t("modelTable.unitPriceSub", { sym: symbol })}</div>
              </th>
            )}
            <th className="px-3 py-2 text-right">{t("modelTable.avgPerCall")}</th>
            <th className="px-3 py-2 text-right">{t("common.virtualCost")}</th>
            <th className="py-2 pl-3 text-right">{t("modelTable.costShare")}</th>
          </tr>
        </thead>
        <tbody>
          {items.map((m) => {
            const name = (
              <span className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: colors[m.model] }} />
                <span className="font-medium">{modelLabel(m.model)}</span>
                {m.priced_by === "model" && (
                  <span
                    className="rounded bg-secondary-container/30 px-1.5 py-0.5 text-[10px] font-semibold text-secondary"
                    title={t("modelTable.customPricedTitle")}
                  >
                    {t("modelTable.customPriced")}
                  </span>
                )}
              </span>
            );
            return (
              <tr key={m.model} className="border-b border-border-card/60 last:border-0 hover:bg-surface/60">
                <td className="py-2.5 pr-3">
                  {linkToLogs ? (
                    <Link to={`/logs?model=${encodeURIComponent(m.model)}`} className="hover:underline" title={m.model}>
                      {name}
                    </Link>
                  ) : (
                    <span title={m.model}>{name}</span>
                  )}
                  <div className="ml-[18px] font-mono text-[11px] text-outline">{m.model}</div>
                </td>
                <td className="px-3 py-2.5 text-right font-mono text-xs">{m.events.toLocaleString()}</td>
                <td className="px-3 py-2.5 text-right font-mono text-xs">
                  {formatTokens(m.tokens)}
                  <div className="text-[11px] text-outline">
                    {formatTokens(m.tokens_detail.input)} / {formatTokens(m.tokens_detail.output)} /{" "}
                    {formatTokens(m.tokens_detail.cache_write)} / {formatTokens(m.tokens_detail.cache_read)}
                  </div>
                </td>
                {!compact && (
                  <td className="px-3 py-2.5 text-right font-mono text-xs text-on-surface-variant">
                    {unit(m.rates.input)} / {unit(m.rates.output)} / {unit(m.rates.cache_write)} /{" "}
                    {unit(m.rates.cache_read)}
                  </td>
                )}
                <td className="px-3 py-2.5 text-right font-mono text-xs">{precise(m.avg_cost_per_call)}</td>
                <td className="px-3 py-2.5 text-right font-mono text-xs font-semibold">{money(m.cost)}</td>
                <td className="py-2.5 pl-3 text-right">
                  <div className="flex items-center justify-end gap-2">
                    <span className="hidden h-1.5 w-16 overflow-hidden rounded-full bg-surface sm:block">
                      <span
                        className="block h-full rounded-full"
                        style={{ width: `${Math.max(m.cost_share * 100, 1)}%`, background: colors[m.model] }}
                      />
                    </span>
                    <span className="w-12 font-mono text-xs text-on-surface-variant">
                      {(m.cost_share * 100).toFixed(1)}%
                    </span>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
        <tfoot>
          <tr className="border-t-2 border-border-card text-xs font-semibold">
            <td className="py-2.5 pr-3">{t("modelTable.totalRow", { n: items.length })}</td>
            <td className="px-3 py-2.5 text-right font-mono">{totalCalls.toLocaleString()}</td>
            <td className="px-3 py-2.5 text-right font-mono">{formatTokens(totalTokens)}</td>
            {!compact && <td />}
            <td />
            <td className="px-3 py-2.5 text-right font-mono">{money(totalCost)}</td>
            <td className="py-2.5 pl-3 text-right font-mono text-on-surface-variant">100%</td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
