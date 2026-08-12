import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { ModelsResponse, RateSet } from "../api/types";
import { useApi } from "../api/useApi";
import ChartCard from "../components/ChartCard";
import { Rich, useI18n } from "../i18n";
import { formatTokens, formatUSD, modelLabel } from "../lib/format";

type Kind = "input" | "output" | "cache_write" | "cache_read";

const KINDS: { key: Kind; label: string; color: string }[] = [
  { key: "input", label: "Input", color: "#0F6EAD" },
  { key: "output", label: "Output", color: "#E8833A" },
  { key: "cache_write", label: "Cache Write", color: "#7C9CB5" },
  { key: "cache_read", label: "Cache Read", color: "#C9D8E4" },
];

const KIND_KEY: Record<Kind, string> = {
  input: "input", output: "output", cache_write: "cw", cache_read: "cr",
};

/** Rough character-based estimate — NOT the real tokenizer, just an order of
 *  magnitude. CJK packs roughly one token per character; Latin text about four
 *  characters per token; punctuation and code sit in between. */
function estimateTokens(text: string): { low: number; high: number; cjk: number; other: number } {
  const cjk = (text.match(/[㐀-鿿぀-ヿ가-힯]/g) ?? []).length;
  const other = text.length - cjk;
  const mid = cjk * 1.0 + other / 4;
  return { low: Math.round(mid * 0.8), high: Math.round(mid * 1.25), cjk, other };
}

export default function TokenGuide() {
  const { t, locale } = useI18n();
  const models = useApi<ModelsResponse>("/api/models?range=all");
  const [sample, setSample] = useState(() => t("guide.s1.sample"));
  const [touched, setTouched] = useState(false);
  const est = useMemo(() => estimateTokens(sample), [sample]);

  // Swap the demo sentence with the language, unless the reader typed their own.
  useEffect(() => {
    if (!touched) setSample(t("guide.s1.sample"));
  }, [locale, touched, t]);

  // Tokens and cost per kind, summed across every model at its own rate.
  const split = useMemo(() => {
    const zero = { input: 0, output: 0, cache_write: 0, cache_read: 0 };
    const tokens: Record<Kind, number> = { ...zero };
    const cost: Record<Kind, number> = { ...zero };
    for (const m of models.data?.models ?? []) {
      for (const k of Object.keys(tokens) as Kind[]) {
        tokens[k] += m.tokens_detail[k];
        cost[k] += (m.tokens_detail[k] * m.rates[k]) / 1e6;
      }
    }
    const tokenTotal = Object.values(tokens).reduce((a, b) => a + b, 0) || 1;
    const costTotal = Object.values(cost).reduce((a, b) => a + b, 0) || 1;
    return { tokens, cost, tokenTotal, costTotal };
  }, [models.data]);

  // One representative rate card per family actually used.
  const families = useMemo(() => {
    const seen = new Map<string, RateSet>();
    for (const m of models.data?.models ?? []) {
      if (!seen.has(m.family)) seen.set(m.family, m.rates);
    }
    return [...seen.entries()];
  }, [models.data]);

  const flow = ["f1", "f2", "f3", "f4", "f5"] as const;
  const flowColors = ["#C9D8E4", "#C9D8E4", "#7C9CB5", "#0F6EAD", "#E8833A"];

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-2xl font-bold">{t("guide.title")}</h3>
        <p className="mt-1 text-sm text-on-surface-variant">{t("guide.subtitle")}</p>
      </div>

      {/* 1. 什么是 token */}
      <ChartCard title={t("guide.s1.title")} subtitle={t("guide.s1.subtitle")}>
        <div className="grid gap-5 lg:grid-cols-[1.1fr_1fr]">
          <div className="space-y-3 text-sm leading-relaxed">
            <p><Rich text={t("guide.s1.p1")} /></p>
            <div className="rounded border border-border-card bg-surface p-3">
              {t("guide.s1.convHead")}
              <br />· <Rich text={t("guide.s1.convEn")} />
              <br />· <Rich text={t("guide.s1.convZh")} />
              <br />· <Rich text={t("guide.s1.convCode")} />
            </div>
            <p className="text-on-surface-variant">{t("guide.s1.p2")}</p>
          </div>

          <div className="rounded border border-border-card bg-surface p-4">
            <label className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
              {t("guide.s1.tryIt")}
            </label>
            <textarea
              value={sample}
              onChange={(e) => { setTouched(true); setSample(e.target.value); }}
              rows={4}
              className="mt-2 w-full resize-y rounded border border-outline-variant bg-surface-card p-2 text-sm focus:border-primary-container focus:outline-none"
            />
            <div className="mt-3 flex items-baseline gap-2">
              <span className="font-mono text-2xl font-bold text-primary-container">
                ≈ {est.low}–{est.high}
              </span>
              <span className="text-sm text-on-surface-variant">tokens</span>
            </div>
            <p className="mt-1 text-xs text-outline">
              <Rich text={t("guide.s1.estNote", {
                chars: sample.length, cjk: est.cjk, other: est.other,
              })} />
            </p>
          </div>
        </div>
      </ChartCard>

      {/* 2. 四类 token 从哪来 */}
      <ChartCard title={t("guide.s2.title")} subtitle={t("guide.s2.subtitle")}>
        <div className="space-y-4">
          <div className="overflow-x-auto">
            <div className="flex min-w-[640px] items-stretch gap-2 text-xs">
              {flow.map((f, i) => (
                <div key={f} className="flex-1 rounded border border-border-card p-3">
                  <div className="mb-2 h-1.5 rounded-full" style={{ background: flowColors[i] }} />
                  <div className="font-semibold">{t(`guide.s2.${f}`)}</div>
                  <div className="mt-1 text-on-surface-variant">{t(`guide.s2.${f}d`)}</div>
                </div>
              ))}
            </div>
          </div>

          <p className="text-sm leading-relaxed"><Rich text={t("guide.s2.p1")} /></p>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {KINDS.map((k) => (
              <div key={k.key} className="rounded border border-border-card bg-surface p-3">
                <div className="flex items-center gap-2">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ background: k.color }} />
                  <span className="text-sm font-semibold">{k.label}</span>
                </div>
                <div className="mt-1 text-xs font-medium text-on-surface-variant">
                  {t(`guide.s2.${KIND_KEY[k.key]}From`)}
                </div>
                <p className="mt-1.5 text-xs leading-relaxed text-outline">
                  {t(`guide.s2.${KIND_KEY[k.key]}Blurb`)}
                </p>
              </div>
            ))}
          </div>

          <p className="rounded border border-border-card bg-surface p-3 text-xs leading-relaxed text-on-surface-variant">
            <Rich text={t("guide.s2.ttl")} />
          </p>
        </div>
      </ChartCard>

      {/* 3. 你的真实构成 */}
      <ChartCard
        title={t("guide.s3.title")}
        subtitle={t("guide.s3.subtitle")}
        loading={models.loading}
        error={models.error}
        onRetry={models.retry}
        empty={!models.data?.models.length}
      >
        <div className="space-y-3">
          {KINDS.map((k) => {
            const tShare = split.tokens[k.key] / split.tokenTotal;
            const cShare = split.cost[k.key] / split.costTotal;
            return (
              <div key={k.key} className="grid items-center gap-3 sm:grid-cols-[120px_1fr_1fr]">
                <div className="flex items-center gap-2 text-sm font-medium">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ background: k.color }} />
                  {k.label}
                </div>
                <Bar share={tShare} color={k.color}
                  left={formatTokens(split.tokens[k.key])} right={`${(tShare * 100).toFixed(2)}%`} />
                <Bar share={cShare} color={k.color}
                  left={formatUSD(split.cost[k.key])} right={`${(cShare * 100).toFixed(2)}%`} />
              </div>
            );
          })}
          <div className="grid gap-3 pt-1 sm:grid-cols-[120px_1fr_1fr] text-xs text-outline">
            <div />
            <div>{t("guide.s3.tokenShare")}</div>
            <div>{t("guide.s3.costShare")}</div>
          </div>
          {models.data && (
            <p className="mt-2 rounded border border-border-card bg-surface p-3 text-sm leading-relaxed">
              <Rich text={t("guide.s3.readout", {
                crToken: (split.tokens.cache_read / split.tokenTotal * 100).toFixed(1),
                crCost: (split.cost.cache_read / split.costTotal * 100).toFixed(1),
                outToken: (split.tokens.output / split.tokenTotal * 100).toFixed(2),
                outCost: (split.cost.output / split.costTotal * 100).toFixed(1),
              })} />
            </p>
          )}
        </div>
      </ChartCard>

      {/* 4. 计费方式 */}
      <ChartCard
        title={t("guide.s4.title")}
        subtitle={t("guide.s4.subtitle")}
        loading={models.loading}
        empty={!families.length}
      >
        <div className="space-y-4">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-sm">
              <thead>
                <tr className="border-b border-border-card text-left text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
                  <th className="py-2 pr-3">{t("guide.s4.colFamily")}</th>
                  {KINDS.map((k) => (
                    <th key={k.key} className="px-3 py-2 text-right">{k.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {families.map(([fam, rates]) => (
                  <tr key={fam} className="border-b border-border-card/60 last:border-0">
                    <td className="py-2.5 pr-3 font-medium">{t(`family.${fam}`)}</td>
                    {KINDS.map((k) => (
                      <td key={k.key} className="px-3 py-2.5 text-right font-mono text-xs">
                        ${rates[k.key]}
                        <div className="text-[11px] text-outline">
                          {rates.input ? `${(rates[k.key] / rates.input).toFixed(2)}×` : "—"}
                        </div>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-outline"><Rich text={t("guide.s4.ratioNote")} /></p>

          <div className="rounded border border-border-card bg-surface p-4 text-sm leading-relaxed">
            <div className="font-semibold">{t("guide.s4.formulaTitle")}</div>
            <div className="mt-2 overflow-x-auto">
              <code className="block whitespace-pre font-mono text-xs text-on-surface-variant">
                {t("guide.s4.formula")}
              </code>
            </div>
            <p className="mt-2 text-on-surface-variant">
              <Rich text={t("guide.s4.formulaNote")} />
            </p>
          </div>
        </div>
      </ChartCard>

      {/* 5. 订阅 vs API */}
      <ChartCard title={t("guide.s5.title")} subtitle={t("guide.s5.subtitle")}>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded border border-border-card bg-surface p-4">
            <div className="text-sm font-semibold">{t("guide.s5.apiTitle")}</div>
            <p className="mt-1.5 text-sm leading-relaxed text-on-surface-variant">
              <Rich text={t("guide.s5.apiBody")} />
            </p>
          </div>
          <div className="rounded border border-border-card bg-surface p-4">
            <div className="text-sm font-semibold">{t("guide.s5.subTitle")}</div>
            <p className="mt-1.5 text-sm leading-relaxed text-on-surface-variant">
              <Rich text={t("guide.s5.subBody")} />
            </p>
          </div>
        </div>
        <p className="mt-4 text-sm">
          {interleave(t("guide.s5.links"), {
            savings: <Link key="s" to="/" className="font-medium text-primary-container hover:underline">{t("guide.s5.linkSavings")}</Link>,
            models: <Link key="m" to="/" className="font-medium text-primary-container hover:underline">{t("guide.s5.linkModels")}</Link>,
            logs: <Link key="l" to="/logs" className="font-medium text-primary-container hover:underline">{t("guide.s5.linkLogs")}</Link>,
          })}
        </p>
        {models.data && (
          <p className="mt-3 text-xs text-outline">
            {t("guide.s5.basis", {
              calls: models.data.totals.events.toLocaleString(),
              tokens: formatTokens(models.data.totals.tokens),
              models: models.data.totals.model_count,
              names: models.data.models.slice(0, 3).map((m) => modelLabel(m.model)).join(" / "),
              more: models.data.models.length > 3 ? t("guide.s5.more") : "",
            })}
          </p>
        )}
      </ChartCard>
    </div>
  );
}

/** Splits a translated sentence on {placeholders} and drops React nodes in,
 *  so link positions follow each language's word order. */
function interleave(text: string, nodes: Record<string, React.ReactNode>): React.ReactNode[] {
  return text.split(/(\{\w+\})/g).map((part, i) => {
    const m = part.match(/^\{(\w+)\}$/);
    return m && nodes[m[1]] !== undefined
      ? <span key={i}>{nodes[m[1]]}</span>
      : <span key={i}>{part}</span>;
  });
}

function Bar({ share, color, left, right }: {
  share: number; color: string; left: string; right: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="h-2.5 flex-1 overflow-hidden rounded-full bg-surface">
        <span className="block h-full rounded-full"
          style={{ width: `${Math.max(share * 100, 0.4)}%`, background: color }} />
      </span>
      <span className="w-16 shrink-0 text-right font-mono text-xs">{left}</span>
      <span className="w-14 shrink-0 text-right font-mono text-xs text-on-surface-variant">{right}</span>
    </div>
  );
}
