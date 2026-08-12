import type { RangeKey } from "../api/types";
import { useI18n } from "../i18n";

const ALL: RangeKey[] = ["today", "7d", "30d", "month", "all"];

export default function TimeRangeSelector({
  value, onChange, options,
}: {
  value: RangeKey;
  onChange: (r: RangeKey) => void;
  options?: RangeKey[];
}) {
  const { t } = useI18n();
  const visible = (options ? ALL.filter((k) => options.includes(k)) : ALL)
    .map((key) => ({ key, label: t(`range.${key}`) }));
  return (
    <div className="inline-flex rounded border border-border-card bg-surface-card p-0.5 text-sm">
      {visible.map((o) => (
        <button
          key={o.key}
          onClick={() => onChange(o.key)}
          className={`whitespace-nowrap rounded px-3 py-1 transition-colors ${
            value === o.key
              ? "bg-primary-container font-semibold text-on-primary"
              : "text-on-surface-variant hover:bg-surface"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
