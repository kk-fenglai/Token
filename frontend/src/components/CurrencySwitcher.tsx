import { useEffect, useRef, useState } from "react";
import { useI18n } from "../i18n";
import { CURRENCIES, CURRENCY_ORDER, RATES_AS_OF, useMoney, type Currency } from "../lib/currency";

/** Display-currency picker. Amounts stay USD underneath (that is what the
 *  pricing table and plan fees are quoted in); this only changes how they are
 *  shown, using a rate the user can edit — no network call, nothing leaves the box. */
export default function CurrencySwitcher() {
  const { t } = useI18n();
  const { currency, setCurrency, rates, setRate } = useMoney();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const boxRef = useRef<HTMLDivElement>(null);

  // The popover always starts from the stored rate so a stale draft never leaks in.
  useEffect(() => {
    if (open) setDraft(String(rates[currency]));
  }, [open, currency, rates]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  function commit() {
    const n = Number(draft);
    setRate(currency, Number.isFinite(n) && n > 0 ? n : null);
  }

  const isDefault = rates[currency] === CURRENCIES[currency].defaultRate;

  return (
    <div ref={boxRef} className="relative">
      <div className="flex items-center gap-1">
        <label className="flex items-center gap-2 text-xs text-on-surface-variant">
          <span className="sr-only">{t("nav.currency")}</span>
          <select
            value={currency}
            onChange={(e) => setCurrency(e.target.value as Currency)}
            className="h-8 rounded border border-outline-variant bg-surface-card px-2 font-mono text-sm text-on-surface"
            title={t("nav.currency")}
          >
            {CURRENCY_ORDER.map((c) => (
              <option key={c} value={c}>{CURRENCIES[c].symbol} {c}</option>
            ))}
          </select>
        </label>
        {currency !== "USD" && (
          <button
            onClick={() => setOpen(!open)}
            aria-expanded={open}
            title={t("currency.rateHint", { rate: rates[currency], code: currency })}
            className={`flex h-8 items-center gap-1 rounded border px-2 font-mono text-xs transition-colors ${
              open ? "border-primary-container text-primary-container" : "border-outline-variant text-on-surface-variant hover:bg-surface"
            }`}
          >
            <span className="material-symbols-outlined text-base">currency_exchange</span>
            {rates[currency]}
          </button>
        )}
      </div>

      {open && currency !== "USD" && (
        <div className="absolute right-0 top-10 z-20 w-72 rounded border border-border-card bg-surface-card p-3 text-sm shadow-card">
          <div className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
            {t("currency.rateLabel")}
          </div>
          <div className="mt-2 flex items-center gap-2 font-mono">
            <span>1 USD =</span>
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onBlur={commit}
              onKeyDown={(e) => { if (e.key === "Enter") { commit(); setOpen(false); } }}
              inputMode="decimal"
              className="h-8 w-24 rounded border border-outline-variant px-2 text-right text-on-surface focus:border-primary-container focus:outline-none"
            />
            <span>{currency}</span>
          </div>
          <p className="mt-2 text-xs text-outline">{t("currency.note")} {t("currency.asOf", { date: RATES_AS_OF })}</p>
          {!isDefault && (
            <button
              onClick={() => { setRate(currency, null); setOpen(false); }}
              className="mt-2 text-xs font-medium text-primary-container hover:underline"
            >
              {t("currency.reset", { rate: CURRENCIES[currency].defaultRate })}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
