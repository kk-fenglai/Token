import type { ReactNode } from "react";

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
          <span>加载失败:{error}</span>
          {onRetry && (
            <button
              onClick={onRetry}
              className="rounded border border-primary-container px-3 py-1.5 text-primary-container hover:bg-surface"
            >
              重试
            </button>
          )}
        </div>
      ) : loading ? (
        <div className="flex h-48 items-center justify-center text-sm text-on-surface-variant">
          加载中…
        </div>
      ) : empty ? (
        <div className="flex h-48 items-center justify-center text-sm text-on-surface-variant">
          {emptyText ?? "暂无数据 — 使用 Claude Code 后点击 Sync Now"}
        </div>
      ) : (
        children
      )}
    </section>
  );
}
