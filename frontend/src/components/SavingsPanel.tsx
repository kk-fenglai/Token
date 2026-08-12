import { useState } from "react";
import type { SavingsReport } from "../api/types";
import SavingsChart from "../charts/SavingsChart";
import { Rich, useI18n, type TFunc } from "../i18n";
import { formatUSD } from "../lib/format";

/** Plan ids the backend catalog can return; only these two are real words. */
function planLabel(id: string, fallback: string, t: TFunc): string {
  if (id === "api") return t("savings.planApi");
  if (id === "team") return t("savings.planTeam");
  return fallback;
}

export default function SavingsPanel({ report, onChanged }: {
  report: SavingsReport;
  onChanged: () => void;
}) {
  const { subscription: sub, current, timeline } = report;
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  async function apply(body: Record<string, unknown>) {
    setSaving(true);
    try {
      await fetch("/api/subscription", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      onChanged();
      setOpen(false);
    } finally {
      setSaving(false);
    }
  }

  const sourceLabel = t(
    current.source === "manual" ? "savings.sourceManual"
      : current.source === "detected" ? "savings.sourceDetected"
      : "savings.sourceUnknown",
  );

  // Pay-as-you-go / undetected: no fixed fee to beat, so no savings claim.
  if (!current.comparable) {
    return (
      <div className="rounded border border-border-card bg-surface-card p-5 shadow-card">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h4 className="text-base font-semibold">{t("savings.title")}</h4>
            <p className="mt-1 text-sm text-on-surface-variant">
              {sub.source === "unknown"
                ? t("savings.undetected", { reason: sub.detect_reason ?? "—" })
                : t("savings.payAsYouGo")}
            </p>
          </div>
          <button onClick={() => setOpen(!open)} className="rounded border border-primary-container px-3 py-1.5 text-sm font-semibold text-primary-container hover:bg-surface">
            {open ? t("common.collapse") : t("savings.pickPlan")}
          </button>
        </div>
        {open && <PlanPicker sub={sub} saving={saving} apply={apply} />}
      </div>
    );
  }

  const positive = current.saved >= 0;
  const planName = planLabel(current.plan ?? "", current.plan_label, t);

  return (
    <div className="rounded border border-border-card bg-surface-card shadow-card">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-border-card p-5">
        <div className="flex items-start gap-3">
          <span className={`material-symbols-outlined rounded p-2 text-2xl ${positive ? "bg-success-container text-success" : "bg-error-container text-error"}`}>
            savings
          </span>
          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
              {t("savings.header", { plan: planName, fee: current.monthly_fee })}
            </div>
            <div className={`mt-1 text-[32px] font-bold leading-10 ${positive ? "text-success" : "text-error"}`}>
              {t(positive ? "savings.saved" : "savings.lost")}
              {formatUSD(Math.abs(current.saved))}
            </div>
            <p className="mt-1 text-sm text-on-surface-variant">
              {t("savings.line", {
                api: formatUSD(current.api_cost_mtd),
                fee: formatUSD(current.monthly_fee),
              })}
              {current.multiple != null && (
                <span className="text-success">
                  {t("savings.earnedBack", { x: current.multiple })}
                </span>
              )}
            </p>
          </div>
        </div>
        <div className="flex flex-col items-end gap-1 text-right">
          <span className="rounded-full bg-surface px-2.5 py-1 text-xs text-on-surface-variant">
            {sourceLabel}
            {sub.fee_overridden && t("savings.feeOverridden")}
          </span>
          <button onClick={() => setOpen(!open)} className="text-sm font-medium text-primary-container hover:underline">
            {open ? t("common.collapse") : t("savings.wrongPlan")}
          </button>
        </div>
      </div>

      {open && <div className="border-b border-border-card px-5"><PlanPicker sub={sub} saving={saving} apply={apply} /></div>}

      <div className="grid gap-4 p-5 sm:grid-cols-3">
        <Metric
          label={t("savings.breakevenLabel")}
          value={current.breakeven_reached
            ? t("savings.breakevenReached")
            : t("savings.breakevenRemaining", { amount: formatUSD(current.remaining_to_breakeven) })}
          note={t("savings.monthProgress", {
            day: current.month_progress.day, total: current.month_progress.days_in_month,
          })}
          accent={current.breakeven_reached ? "text-success" : "text-secondary"}
        />
        <Metric
          label={t("savings.projectedLabel")}
          value={formatUSD(current.projected_api_cost)}
          note={t("savings.projectedNote", { amount: formatUSD(current.projected_saved) })}
        />
        <Metric
          label={t("savings.cumulativeLabel", { months: timeline.paid_months })}
          value={formatUSD(timeline.total_saved)}
          note={t("savings.cumulativeNote", {
            api: formatUSD(timeline.total_api_cost), fees: formatUSD(timeline.total_fees),
          })}
          accent={timeline.total_saved >= 0 ? "text-success" : "text-error"}
        />
      </div>

      <div className="px-5 pb-5">
        <SavingsChart points={timeline.points} />
        <p className="mt-3 text-xs text-outline">
          {t("savings.chartNote", { fee: timeline.monthly_fee })}
          {timeline.months_missing_data > 0 && (
            <Rich text={t("savings.missingNote", { n: timeline.months_missing_data })} />
          )}
        </p>
      </div>
    </div>
  );
}

function Metric({ label, value, note, accent }: { label: string; value: string; note: string; accent?: string }) {
  return (
    <div className="rounded border border-border-card bg-surface p-3">
      <div className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">{label}</div>
      <div className={`mt-1 text-xl font-bold ${accent ?? "text-on-surface"}`}>{value}</div>
      <div className="mt-0.5 text-xs text-outline">{note}</div>
    </div>
  );
}

function PlanPicker({ sub, saving, apply }: {
  sub: SavingsReport["subscription"];
  saving: boolean;
  apply: (body: Record<string, unknown>) => void;
}) {
  const { t } = useI18n();
  const [fee, setFee] = useState("");
  return (
    <div className="space-y-3 py-4">
      <div className="flex flex-wrap gap-2">
        {sub.catalog.map((p) => (
          <button
            key={p.id}
            disabled={saving}
            onClick={() => apply({ mode: "manual", plan: p.id, monthly_usd: fee ? Number(fee) : undefined })}
            className={`rounded border px-3 py-1.5 text-sm ${
              sub.plan === p.id
                ? "border-primary-container bg-primary-container font-semibold text-on-primary"
                : "border-outline-variant hover:bg-surface"
            }`}
          >
            {planLabel(p.id, p.label, t)}
            {p.monthly_usd > 0 && <span className="ml-1 font-mono text-xs opacity-80">${p.monthly_usd}</span>}
          </button>
        ))}
        <button
          disabled={saving}
          onClick={() => apply({ mode: "auto" })}
          className={`rounded border px-3 py-1.5 text-sm ${
            sub.mode === "auto" ? "border-primary-container text-primary-container" : "border-outline-variant hover:bg-surface"
          }`}
          title={t("savings.autoDetectTitle")}
        >
          {t("savings.autoDetect")}
        </button>
      </div>
      <label className="flex flex-wrap items-center gap-2 text-xs text-on-surface-variant">
        {t("savings.customFee")}
        <input
          value={fee}
          onChange={(e) => setFee(e.target.value)}
          placeholder={String(sub.monthly_usd)}
          inputMode="decimal"
          className="h-8 w-28 rounded border border-outline-variant px-2 font-mono text-sm text-on-surface focus:border-primary-container focus:outline-none"
        />
        <span>{t("savings.customFeeHint")}</span>
      </label>
      {sub.detect_reason && (
        <p className="text-xs text-outline">
          {t("savings.detectBasis")}
          <span className="font-mono">{sub.detect_reason}</span>
          {sub.since && t("savings.since", { date: String(sub.since).slice(0, 10) })}
        </p>
      )}
    </div>
  );
}
