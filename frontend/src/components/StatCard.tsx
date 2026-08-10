interface Props {
  label: string;
  value: string;
  note?: string;
  icon?: string;
  accent?: string;
}

export default function StatCard({ label, value, note, icon, accent }: Props) {
  return (
    <div className="rounded border border-border-card bg-surface-card p-4 shadow-card">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
          {label}
        </span>
        {icon && (
          <span className="material-symbols-outlined text-outline">{icon}</span>
        )}
      </div>
      <div className="mt-2 text-[28px] font-bold leading-9">{value}</div>
      {note && <div className={`mt-1 text-xs ${accent ?? "text-on-surface-variant"}`}>{note}</div>}
    </div>
  );
}
