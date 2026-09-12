import type { ReactNode } from "react";
import type { BillingMonth, MonthlyBilling as Billing } from "../api/types";
import { useApi } from "../api/useApi";
import SavingsChart from "../charts/SavingsChart";
import { useI18n } from "../i18n";
import { useMoney } from "../lib/currency";
import { formatTokens } from "../lib/format";

/** 回本参照档位 — 与后端 PLANS 一致,只做展示用。 */
const BREAKEVEN_PLANS = [
  { id: "pro", label: "Pro", fee: 20 },
  { id: "max5", label: "Max 5x", fee: 100 },
  { id: "max20", label: "Max 20x", fee: 200 },
];

export default function MonthlyBilling() {
  const { t } = useI18n();
  const { money } = useMoney();
  const billing = useApi<Billing>("/api/billing/monthly");

  if (billing.error) {
    return (
      <div className="flex h-48 flex-col items-center justify-center gap-3 rounded border border-border-card bg-surface-card text-sm text-on-surface-variant">
        <span>{t("common.loadFailed", { error: billing.error })}</span>
        <button onClick={billing.retry} className="rounded border border-primary-container px-3 py-1.5 text-primary-container">{t("common.retry")}</button>
      </div>
    );
  }
  if (!billing.data) {
    return <div className="flex h-48 items-center justify-center rounded border border-border-card bg-surface-card text-sm text-on-surface-variant">{t("common.loading")}</div>;
  }

  const { subscription: sub, current, timeline } = billing.data;
  // 表格新→旧;图表保持时间升序。
  const rows = [...timeline.points].reverse();
  const thisMonth = timeline.points.find((p) => p.partial);
  // 用本月(或最近有数据月)的混合单价把「回本要多少钱」换算成「大约多少 tokens」。
  const ref = thisMonth?.tokens ? thisMonth
    : rows.find((p) => p.tokens > 0 && p.api_cost > 0);
  const usdPerMTok = ref && ref.tokens > 0 ? ref.api_cost / (ref.tokens / 1e6) : null;

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-2xl font-bold">{t("billing.title")}</h3>
        <p className="mt-1 text-sm text-on-surface-variant">{t("billing.subtitle")}</p>
      </div>

      {/* 三张摘要卡:套餐 / 本月账单 / 累计 */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Card
          label={t("billing.planCard")}
          value={sub.comparable ? `${current.plan_label} · ${money(current.monthly_fee, 0)}/${t("billing.perMonth")}` : sub.label}
          note={sub.source === "detected" ? t("savings.sourceDetected") : sub.source === "manual" ? t("savings.sourceManual") : t("savings.sourceUnknown")}
        />
        <Card
          label={t("billing.mtdCard")}
          value={money(current.api_cost_mtd)}
          note={current.comparable
            ? current.breakeven_reached
              ? t("billing.mtdBreakeven", { x: current.multiple ?? 0 })
              : t("savings.breakevenRemaining", { amount: money(current.remaining_to_breakeven) })
            : t("billing.notComparable")}
          accent={current.comparable && current.breakeven_reached ? "text-success" : undefined}
        />
        <Card
          label={t("savings.cumulativeLabel", { months: timeline.paid_months })}
          value={money(timeline.total_saved)}
          note={t("savings.cumulativeNote", {
            api: money(timeline.total_api_cost), fees: money(timeline.total_fees),
          })}
          accent={timeline.total_saved >= 0 ? "text-success" : "text-error"}
        />
      </div>

      {/* 回本线说明 */}
      {current.comparable && (
        <div className="rounded border border-border-card bg-surface-card p-5 shadow-card">
          <h4 className="text-base font-semibold">{t("billing.breakevenTitle")}</h4>
          <p className="mt-1 text-sm text-on-surface-variant">{t("billing.breakevenIntro")}</p>
          <div className="mt-3 grid gap-3 sm:grid-cols-3">
            {BREAKEVEN_PLANS.map((p) => (
              <div key={p.id} className={`rounded border p-3 ${current.plan === p.id ? "border-primary-container bg-surface" : "border-border-card"}`}>
                <div className="flex items-baseline justify-between">
                  <span className="text-sm font-semibold">{p.label}</span>
                  {current.plan === p.id && (
                    <span className="rounded-full bg-primary-container px-2 py-0.5 text-[11px] font-semibold text-on-primary">{t("billing.yourPlan")}</span>
                  )}
                </div>
                <div className="mt-1 text-xl font-bold">{money(p.fee, 0)}<span className="text-xs font-normal text-on-surface-variant">/{t("billing.perMonth")}</span></div>
                <div className="mt-0.5 text-xs text-outline">
                  {usdPerMTok
                    ? t("billing.breakevenTokens", { tokens: formatTokens((p.fee / usdPerMTok) * 1e6) })
                    : t("billing.breakevenCost", { fee: money(p.fee, 0) })}
                </div>
              </div>
            ))}
          </div>
          {usdPerMTok && (
            <p className="mt-3 text-xs text-outline">
              {t("billing.mixNote", { rate: money(usdPerMTok, 2), month: ref?.month ?? "" })}
            </p>
          )}
        </div>
      )}

      {/* 月度图 */}
      <div className="rounded border border-border-card bg-surface-card p-5 shadow-card">
        <h4 className="mb-3 text-base font-semibold">{t("billing.chartTitle")}</h4>
        <SavingsChart points={timeline.points} />
        <p className="mt-3 text-xs text-outline">{t("savings.chartNote", { fee: money(timeline.monthly_fee, 0) })}</p>
      </div>

      {/* 账单表:一行一个月 */}
      <div className="overflow-x-auto rounded border border-border-card bg-surface-card shadow-card">
        <table className="w-full min-w-[760px] text-sm">
          <thead>
            <tr className="border-b border-border-card text-left text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
              <th className="px-4 py-3">{t("billing.colMonth")}</th>
              <th className="px-4 py-3 text-right">{t("common.tokens")}</th>
              <th className="px-4 py-3 text-right">{t("billing.colEvents")}</th>
              <th className="px-4 py-3 text-right">{t("billing.colApiCost")}</th>
              <th className="px-4 py-3 text-right">{t("billing.colFee")}</th>
              <th className="px-4 py-3 text-right">{t("billing.colSaved")}</th>
              <th className="px-4 py-3 text-right">{t("billing.colCumulative")}</th>
              <th className="px-4 py-3">{t("billing.colStatus")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => <Row key={p.month} p={p} />)}
          </tbody>
          {timeline.paid_months > 0 && (
            <tfoot>
              <tr className="border-t border-border-card font-semibold">
                <td className="px-4 py-3">{t("billing.totalRow", { months: timeline.paid_months })}</td>
                <td className="px-4 py-3 text-right font-mono">{formatTokens(timeline.total_tokens)}</td>
                <td className="px-4 py-3 text-right font-mono">{timeline.total_events.toLocaleString()}</td>
                <td className="px-4 py-3 text-right font-mono">{money(timeline.total_api_cost)}</td>
                <td className="px-4 py-3 text-right font-mono">{money(timeline.total_fees)}</td>
                <td className={`px-4 py-3 text-right font-mono ${timeline.total_saved >= 0 ? "text-success" : "text-error"}`}>{money(timeline.total_saved)}</td>
                <td className="px-4 py-3" colSpan={2} />
              </tr>
            </tfoot>
          )}
        </table>
      </div>
      {timeline.months_missing_data > 0 && (
        <p className="text-xs text-outline">{t("savings.missingNote", { n: timeline.months_missing_data, zero: money(0, 0) })}</p>
      )}
    </div>
  );
}

function Row({ p }: { p: BillingMonth }) {
  const { t } = useI18n();
  const { money } = useMoney();
  return (
    <tr className="border-b border-border-card last:border-0 hover:bg-surface">
      <td className="px-4 py-3 font-mono font-medium">{p.month}</td>
      <td className="px-4 py-3 text-right font-mono">{p.tokens > 0 ? formatTokens(p.tokens) : "—"}</td>
      <td className="px-4 py-3 text-right font-mono">{p.events > 0 ? p.events.toLocaleString() : "—"}</td>
      <td className="px-4 py-3 text-right font-mono">{money(p.api_cost)}</td>
      <td className="px-4 py-3 text-right font-mono">{p.subscribed ? money(p.fee) : "—"}</td>
      <td className={`px-4 py-3 text-right font-mono ${!p.subscribed ? "" : p.saved >= 0 ? "text-success" : "text-error"}`}>
        {p.subscribed ? money(p.saved) : "—"}
      </td>
      <td className="px-4 py-3 text-right font-mono">{p.subscribed ? money(p.cumulative_saved) : "—"}</td>
      <td className="px-4 py-3">
        {p.partial ? <Tag tone="info">{t("savings.tagPartial")}</Tag>
          : p.data_missing && p.subscribed ? <Tag tone="warn">{t("billing.tagMissing")}</Tag>
          : !p.subscribed ? <Tag tone="muted">{t("billing.tagNotSubscribed")}</Tag>
          : <Tag tone="ok">{t("billing.tagSettled")}</Tag>}
      </td>
    </tr>
  );
}

function Tag({ tone, children }: { tone: "ok" | "info" | "warn" | "muted"; children: ReactNode }) {
  const cls = {
    ok: "bg-success-container text-success",
    info: "bg-surface text-primary-container border border-primary-container",
    warn: "bg-error-container text-error",
    muted: "bg-surface text-outline",
  }[tone];
  return <span className={`inline-block rounded-full px-2 py-0.5 text-[11px] font-medium ${cls}`}>{children}</span>;
}

function Card({ label, value, note, accent }: { label: string; value: string; note: string; accent?: string }) {
  return (
    <div className="rounded border border-border-card bg-surface-card p-5 shadow-card">
      <div className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">{label}</div>
      <div className={`mt-1 text-2xl font-bold ${accent ?? "text-on-surface"}`}>{value}</div>
      <div className="mt-0.5 text-xs text-outline">{note}</div>
    </div>
  );
}
