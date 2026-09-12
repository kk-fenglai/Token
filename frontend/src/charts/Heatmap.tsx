import type { Heatmap as HeatmapData } from "../api/types";
import { useI18n } from "../i18n";
import { useMoney } from "../lib/currency";
import { formatTokens } from "../lib/format";

/** 7×24 grid, no chart library: 168 cells with an alpha ramp is cheaper and
 *  crisper as plain DOM than as an SVG scatter. dow 0 = Sunday (SQLite %w);
 *  rows are shown Monday-first. */
const ROW_ORDER = [1, 2, 3, 4, 5, 6, 0];

export default function Heatmap({ data }: { data: HeatmapData }) {
  const { t } = useI18n();
  const { money } = useMoney();
  const byKey = new Map(data.cells.map((c) => [`${c.dow}-${c.hour}`, c]));
  const max = data.max_cost || 1;
  return (
    <div className="overflow-x-auto">
      <div className="min-w-[640px]">
        <div className="grid gap-[3px]" style={{ gridTemplateColumns: "44px repeat(24, minmax(0, 1fr))" }}>
          <div />
          {Array.from({ length: 24 }, (_, h) => (
            <div key={h} className="text-center font-mono text-[10px] text-outline">{h % 3 === 0 ? h : ""}</div>
          ))}
          {ROW_ORDER.map((d) => (
            <>
              <div key={`l${d}`} className="pr-2 text-right text-xs text-on-surface-variant">{t(`insights.dow${d}`)}</div>
              {Array.from({ length: 24 }, (_, h) => {
                const c = byKey.get(`${d}-${h}`);
                const v = c ? c.cost / max : 0;
                const alpha = v === 0 ? 0 : 0.12 + 0.88 * Math.sqrt(v);
                return (
                  <div
                    key={`${d}-${h}`}
                    className="aspect-square rounded-[3px] border border-border-card/60"
                    style={{ background: alpha ? `rgba(15,110,173,${alpha.toFixed(3)})` : "#f7f9fb" }}
                    title={c ? `${t(`insights.dow${d}`)} ${String(h).padStart(2, "0")}:00 · ${money(c.cost)} · ${formatTokens(c.tokens)} tokens · ${c.events}` : ""}
                  />
                );
              })}
            </>
          ))}
        </div>
        {data.peak && (
          <p className="mt-3 text-xs text-on-surface-variant">
            {t("insights.heatmapPeak", {
              dow: t(`insights.dow${data.peak.dow}`),
              hour: String(data.peak.hour).padStart(2, "0"),
              cost: money(data.peak.cost),
            })}
          </p>
        )}
      </div>
    </div>
  );
}
