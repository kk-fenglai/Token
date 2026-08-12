import type { ProjectShare } from "../api/types";
import { useScope } from "../api/scope";
import { useI18n } from "../i18n";
import { formatTokens, formatUSD } from "../lib/format";

/** Shown in place of SavingsPanel when the dashboard is scoped to a project.
 *  A subscription fee buys the whole account, so "this project saved you $X"
 *  would be nonsense — the honest question is how much of the fee it used up. */
export default function ProjectShareCard({ data }: { data: ProjectShare }) {
  const { t } = useI18n();
  const { setProject } = useScope();
  const over = (data.pct_of_fee ?? 0) > 100;

  if (data.scope && !data.scope.known) {
    return (
      <div className="rounded border border-secondary-container bg-surface-card p-5 shadow-card">
        <div className="text-base font-semibold">{data.scope.name}</div>
        <p className="mt-1 text-sm text-on-surface-variant">{t("scope.unknown")}</p>
        <button onClick={() => setProject(null)} className="mt-3 text-sm font-medium text-primary-container hover:underline">
          {t("scope.switchHint")}
        </button>
      </div>
    );
  }

  return (
    <div className="rounded border border-border-card bg-surface-card p-5 shadow-card">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <span className="material-symbols-outlined rounded bg-primary-container/15 p-2 text-2xl text-primary-container">
            folder_open
          </span>
          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
              {t("scope.cardTitle")} · {data.scope?.name}
            </div>
            <div className="mt-1 text-[32px] font-bold leading-10">{formatUSD(data.month_cost)}</div>
            <p className="mt-1 text-sm text-on-surface-variant">
              {t("scope.tokensAndCalls", {
                tokens: formatTokens(data.month_tokens),
                calls: data.events.toLocaleString(),
              })}
            </p>
          </div>
        </div>
        <button onClick={() => setProject(null)} className="text-sm font-medium text-primary-container hover:underline">
          {t("scope.switchHint")}
        </button>
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <Metric
          label={t("scope.ofAccount", {
            pct: (data.cost_share * 100).toFixed(1),
            total: formatUSD(data.account_month_cost),
          })}
          share={data.cost_share}
          color="#0F6EAD"
        />
        {data.comparable && data.pct_of_fee != null ? (
          <Metric
            label={t(over ? "scope.ofFeeOver" : "scope.ofFee", {
              plan: data.plan_label, fee: data.monthly_fee, pct: data.pct_of_fee,
            })}
            share={Math.min(data.pct_of_fee / 100, 1)}
            color={over ? "#1b6d43" : "#974800"}
          />
        ) : (
          <p className="self-center text-sm text-on-surface-variant">{t("scope.notComparable")}</p>
        )}
      </div>

      {data.scope && data.scope.cwds.length > 1 && (
        <p className="mt-3 text-xs text-outline" title={data.scope.cwds.join("\n")}>
          {t("scope.foldedFrom", { n: data.scope.cwds.length })}
        </p>
      )}
    </div>
  );
}

function Metric({ label, share, color }: { label: string; share: number; color: string }) {
  return (
    <div className="rounded border border-border-card bg-surface p-3">
      <div className="text-sm">{label}</div>
      <span className="mt-2 block h-2 overflow-hidden rounded-full bg-surface-card">
        <span className="block h-full rounded-full"
          style={{ width: `${Math.max(share * 100, 1)}%`, background: color }} />
      </span>
    </div>
  );
}
