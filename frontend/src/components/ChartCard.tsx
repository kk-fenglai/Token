import type { ReactNode } from "react";
import { useI18n } from "../i18n";

interface Props {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  empty?: boolean;
  emptyText?: string;
  children: ReactNode;
  className?: string;
}

export default function ChartCard({
  title, subtitle, actions, loading, error, onRetry, empty, emptyText, children, className = "",
}: Props) {
  const { t } = useI18n();
  return (
    <section className={`rounded border border-border-card bg-surface-card p-4 shadow-card ${className}`}>
      <div className="mb-3 flex items-start justify-between gap-2">
        <div>
          <h3 className="text-base font-semibold">{title}</h3>
          {subtitle && <p className="mt-0.5 text-xs text-on-surface-variant">{subtitle}</p>}
        </div>
        {actions}
      </div>
      {error ? (
        <div className="flex h-48 flex-col items-center justify-center gap-3 text-sm text-on-surface-variant">
          <span>{t("common.loadFailed", { error })}</span>
          {onRetry && (
            <button
              onClick={onRetry}
              className="rounded border border-primary-container px-3 py-1.5 text-primary-container hover:bg-surface"
            >
              {t("common.retry")}
            </button>
          )}
        </div>
      ) : loading ? (
        <div className="flex h-48 items-center justify-center text-sm text-on-surface-variant">
          {t("common.loading")}
        </div>
      ) : empty ? (
        <div className="flex h-48 items-center justify-center text-sm text-on-surface-variant">
          {emptyText ?? t("common.empty")}
        </div>
      ) : (
        children
      )}
    </section>
  );
}
