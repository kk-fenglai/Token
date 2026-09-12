import { Link } from "react-router-dom";
import type { AlertItem, AlertsResponse } from "../api/types";
import { useScope } from "../api/scope";
import { useApi } from "../api/useApi";
import { useI18n, type TFunc } from "../i18n";
import { useMoney, type Money } from "../lib/currency";
import { formatTokens } from "../lib/format";

/** Alert params are raw numbers from the API; the UI decides how each one
 *  reads (money in the display currency, tokens compacted, deltas signed). */
const MONEY_KEYS = new Set(["today", "median", "this", "prev", "cost"]);
const TOKEN_KEYS = new Set(["ctx_max"]);

export function alertText(a: AlertItem, t: TFunc, money: Money["money"]): string {
  const vars: Record<string, string | number> = {};
  for (const [k, v] of Object.entries(a.params)) {
    if (typeof v === "number" && MONEY_KEYS.has(k)) vars[k] = money(v);
    else if (typeof v === "number" && TOKEN_KEYS.has(k)) vars[k] = formatTokens(v);
    else if (k === "delta_pct" && typeof v === "number") vars[k] = `${v > 0 ? "+" : ""}${v}`;
    else vars[k] = v;
  }
  return t(`alerts.kinds.${a.kind}`, vars);
}

const LEVEL_STYLE: Record<AlertItem["level"], { border: string; icon: string; iconColor: string }> = {
  danger: { border: "border-l-error", icon: "error", iconColor: "text-error" },
  warn: { border: "border-l-secondary-container", icon: "warning", iconColor: "text-secondary" },
  info: { border: "border-l-primary-container", icon: "info", iconColor: "text-primary-container" },
};

export function AlertRow({ a }: { a: AlertItem }) {
  const { t } = useI18n();
  const { money } = useMoney();
  const s = LEVEL_STYLE[a.level];
  const sessionId = typeof a.params.session_id === "string" ? a.params.session_id : null;
  return (
    <li className={`flex items-start gap-3 rounded border border-border-card border-l-4 ${s.border} bg-surface-card px-4 py-3 text-sm shadow-card`}>
      <span className={`material-symbols-outlined mt-0.5 ${s.iconColor}`}>{s.icon}</span>
      <div className="min-w-0 flex-1">
        <span className="mr-2 rounded-full bg-surface px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-on-surface-variant">
          {t(`alerts.level.${a.level}`)}
        </span>
        <span>{alertText(a, t, money)}</span>
        {sessionId && (
          <Link to={`/sessions/detail?id=${encodeURIComponent(sessionId)}`}
            className="ml-2 whitespace-nowrap font-medium text-primary-container hover:underline">
            {t("alerts.openSession")}
          </Link>
        )}
      </div>
    </li>
  );
}

/** Dashboard strip: only warn/danger, and nothing at all when there is
 *  nothing to say — a permanent "all good" banner is noise. */
export default function AlertStrip() {
  const { t } = useI18n();
  const { project, ready } = useScope();
  const alerts = useApi<AlertsResponse>(
    ready ? `/api/alerts${project ? `?project=${encodeURIComponent(project)}` : ""}` : null,
  );
  const items = (alerts.data?.items ?? []).filter((a) => a.level !== "info");
  if (!items.length) return null;
  return (
    <section>
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-on-surface-variant">{t("alerts.title")}</h3>
        <Link to="/insights" className="text-sm font-medium text-primary-container hover:underline">{t("alerts.viewAll")}</Link>
      </div>
      <ul className="space-y-2">
        {items.map((a, i) => <AlertRow key={`${a.kind}-${i}`} a={a} />)}
      </ul>
    </section>
  );
}
