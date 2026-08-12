import { Link, useSearchParams } from "react-router-dom";
import type { ProjectDetail as Detail } from "../api/types";
import { useApi } from "../api/useApi";
import ModelTable from "../components/ModelTable";
import StatCard from "../components/StatCard";
import { useI18n } from "../i18n";
import { formatLocalTime, formatTokens, formatUSD } from "../lib/format";

export default function ProjectDetail() {
  const { t } = useI18n();
  const [sp] = useSearchParams();
  const path = sp.get("path") ?? "";
  const detail = useApi<Detail>(path ? `/api/projects/detail?path=${encodeURIComponent(path)}` : null);
  const d = detail.data;

  return (
    <div className="space-y-6">
      <nav className="flex items-center gap-2 text-sm text-on-surface-variant">
        <Link to="/projects" className="hover:text-primary-container hover:underline">{t("projects.title")}</Link>
        <span className="material-symbols-outlined text-base">chevron_right</span>
        <span className="text-on-surface">{d?.name ?? "…"}</span>
      </nav>

      {detail.error ? (
        <div className="flex h-48 flex-col items-center justify-center gap-3 rounded border border-border-card bg-surface-card text-sm text-on-surface-variant">
          <span>{t("common.loadFailed", { error: detail.error })}</span>
          <button onClick={detail.retry} className="rounded border border-primary-container px-3 py-1.5 text-primary-container">{t("common.retry")}</button>
        </div>
      ) : !d ? (
        <div className="flex h-48 items-center justify-center rounded border border-border-card bg-surface-card text-sm text-on-surface-variant">{t("common.loading")}</div>
      ) : (
        <>
          <div>
            <h3 className="text-3xl font-bold">{d.name}</h3>
            <div className="mt-2 flex flex-wrap items-center gap-4 text-sm text-on-surface-variant">
              <span className="flex items-center gap-1 font-mono text-xs">
                <span className="material-symbols-outlined text-base">folder</span>{d.path}
              </span>
              <span className="flex items-center gap-1">
                <span className="material-symbols-outlined text-base">calendar_today</span>
                {t("detail.firstSeen", { date: formatLocalTime(d.first_seen).slice(0, 10) })}
              </span>
              <span className="rounded-full bg-chart-cache-read px-2.5 py-0.5 text-xs font-medium text-primary">
                {t("detail.lastActive", { time: formatLocalTime(d.last_active) })}
              </span>
              {d.today.tokens > 0 && (
                <span className="rounded-full bg-success-container px-2.5 py-0.5 text-xs font-medium text-on-success-container">
                  {t("projects.today")} {formatTokens(d.today.tokens)} · {formatUSD(d.today.cost)}
                </span>
              )}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
            <StatCard label={t("detail.totalTokens")} icon="data_usage"
              value={formatTokens(d.tokens)}
              note={d.tokens_delta_pct != null
                ? t("detail.deltaVsPrev", {
                    sign: d.tokens_delta_pct > 0 ? "+" : "",
                    pct: d.tokens_delta_pct,
                    tokens: formatTokens(d.month_tokens),
                  })
                : t("detail.thisMonth", { tokens: formatTokens(d.month_tokens) })}
              accent={d.tokens_delta_pct != null && d.tokens_delta_pct > 0 ? "text-secondary" : "text-on-surface-variant"} />
            <StatCard label={t("detail.costAll")} icon="attach_money"
              value={formatUSD(d.cost)}
              note={t("detail.costAllNote")} />
            <StatCard label={t("detail.avgRequest")} icon="request_quote"
              value={`$${d.avg_cost_per_event.toFixed(4)}`}
              note={t("detail.sessionCount", { n: d.sessions })} />
            <StatCard label={t("detail.associatedLogs")} icon="receipt_long"
              value={d.events.toLocaleString()}
              note={t("detail.assistantMessages")} />
          </div>

          <div className="rounded border border-border-card bg-surface-card p-5 shadow-card">
            <h4 className="mb-3 text-base font-semibold">{t("detail.composition")}</h4>
            <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
              {(
                [
                  ["Input", d.tokens_detail.input, "bg-chart-input"],
                  ["Output", d.tokens_detail.output, "bg-chart-output"],
                  ["Cache Write", d.tokens_detail.cache_write, "bg-chart-cache-write"],
                  ["Cache Read", d.tokens_detail.cache_read, "bg-chart-cache-read"],
                ] as const
              ).map(([label, value, color]) => (
                <div key={label} className="flex items-center gap-3">
                  <span className={`h-3 w-3 rounded-full ${color}`} />
                  <div>
                    <div className="text-xs text-on-surface-variant">{label}</div>
                    <div className="font-mono text-sm font-semibold">{formatTokens(value)}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded border border-border-card bg-surface-card p-5 shadow-card">
            <h4 className="text-base font-semibold">{t("detail.modelsUsed")}</h4>
            <p className="mb-3 mt-0.5 text-sm text-on-surface-variant">
              {t("detail.modelsUsedSub")}
            </p>
            <ModelTable items={d.by_model} />
          </div>

          <Link
            to={`/logs`}
            className="inline-flex items-center gap-2 text-sm font-medium text-primary-container hover:underline"
          >
            <span className="material-symbols-outlined">receipt_long</span>
            {t("detail.viewInLogs")}
          </Link>
        </>
      )}
    </div>
  );
}
