import type { RangeKey } from "../api/types";

const OPTIONS: { key: RangeKey; label: string }[] = [
  { key: "today", label: "今日" },
  { key: "7d", label: "近 7 天" },
  { key: "30d", label: "近 30 天" },
  { key: "month", label: "本月" },
  { key: "all", label: "全部" },
];

export default function TimeRangeSelector({
  value, onChange, options,
}: {
  value: RangeKey;
  onChange: (r: RangeKey) => void;
  options?: RangeKey[];
}) {
  const visible = options ? OPTIONS.filter((o) => options.includes(o.key)) : OPTIONS;
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
