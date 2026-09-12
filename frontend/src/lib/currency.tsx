import {
  createContext, useCallback, useContext, useEffect, useMemo, useState,
  type ReactNode,
} from "react";

/** Every cost the backend returns is in USD (pricing.json is $/Mtok and the
 *  subscription fees are list prices in USD). Display currency is purely a
 *  front-end concern: one editable rate per currency, converted at render time. */
export type Currency = "USD" | "GBP" | "EUR" | "CNY";

export const CURRENCY_ORDER: Currency[] = ["USD", "GBP", "EUR", "CNY"];

/** The built-in rates are a snapshot, not a feed — say when they were taken. */
export const RATES_AS_OF = "2026-09-12";

export const CURRENCIES: Record<Currency, { symbol: string; name: string; defaultRate: number }> = {
  USD: { symbol: "$", name: "US Dollar", defaultRate: 1 },
  GBP: { symbol: "£", name: "British Pound", defaultRate: 0.78 },
  EUR: { symbol: "€", name: "Euro", defaultRate: 0.92 },
  CNY: { symbol: "¥", name: "Chinese Yuan", defaultRate: 7.2 },
};

const CURRENCY_KEY = "tokenscope.currency";
const RATES_KEY = "tokenscope.fxrates";

type Rates = Record<Currency, number>;

function defaultRates(): Rates {
  return Object.fromEntries(
    CURRENCY_ORDER.map((c) => [c, CURRENCIES[c].defaultRate]),
  ) as Rates;
}

function loadCurrency(): Currency {
  try {
    const saved = localStorage.getItem(CURRENCY_KEY);
    if (saved && saved in CURRENCIES) return saved as Currency;
  } catch { /* private mode etc. */ }
  return "USD";
}

function loadRates(): Rates {
  const out = defaultRates();
  try {
    const raw = localStorage.getItem(RATES_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<Record<string, unknown>>;
      for (const c of CURRENCY_ORDER) {
        const v = parsed[c];
        if (typeof v === "number" && Number.isFinite(v) && v > 0) out[c] = v;
      }
    }
  } catch { /* ignore corrupt storage */ }
  out.USD = 1;
  return out;
}

export interface Money {
  currency: Currency;
  setCurrency: (c: Currency) => void;
  /** 1 USD = `rate` units of the active currency. */
  rate: number;
  rates: Rates;
  /** Override the rate of any currency; `null` restores the built-in default. */
  setRate: (c: Currency, rate: number | null) => void;
  symbol: string;
  code: Currency;
  convert: (usd: number) => number;
  /** "$1,234.56" — the everyday amount formatter (was `formatUSD`). */
  money: (usd: number, decimals?: number) => string;
  /** Four decimals — a single API call is far below one cent. */
  precise: (usd: number) => string;
  /** Rate-table cell ($/Mtok): integers stay integers, otherwise two decimals. */
  unit: (usd: number) => string;
  /** Compact axis tick: "$1.2k". */
  axis: (usd: number) => string;
}

const MoneyContext = createContext<Money | null>(null);

export function CurrencyProvider({ children }: { children: ReactNode }) {
  const [currency, setCurrencyState] = useState<Currency>(loadCurrency);
  const [rates, setRates] = useState<Rates>(loadRates);

  useEffect(() => {
    try { localStorage.setItem(CURRENCY_KEY, currency); } catch { /* ignore */ }
  }, [currency]);

  useEffect(() => {
    try { localStorage.setItem(RATES_KEY, JSON.stringify(rates)); } catch { /* ignore */ }
  }, [rates]);

  const setRate = useCallback((c: Currency, rate: number | null) => {
    if (c === "USD") return;
    setRates((prev) => ({
      ...prev,
      [c]: rate == null || !Number.isFinite(rate) || rate <= 0 ? CURRENCIES[c].defaultRate : rate,
    }));
  }, []);

  const value = useMemo<Money>(() => {
    const rate = rates[currency];
    const symbol = CURRENCIES[currency].symbol;
    const convert = (usd: number) => usd * rate;
    const fixed = (n: number, decimals: number) =>
      n.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
    return {
      currency,
      setCurrency: setCurrencyState,
      rate,
      rates,
      setRate,
      symbol,
      code: currency,
      convert,
      money: (usd, decimals = 2) => `${symbol}${fixed(convert(usd), decimals)}`,
      precise: (usd) => `${symbol}${convert(usd).toFixed(4)}`,
      unit: (usd) => {
        const v = convert(usd);
        return `${symbol}${v % 1 === 0 ? v.toFixed(0) : v.toFixed(2)}`;
      },
      axis: (usd) => {
        const v = convert(usd);
        if (Math.abs(v) >= 1000) return `${symbol}${(v / 1000).toFixed(1)}k`;
        return `${symbol}${Number.isInteger(v) ? v : v.toFixed(v < 10 ? 2 : 0)}`;
      },
    };
  }, [currency, rates, setRate]);

  return <MoneyContext.Provider value={value}>{children}</MoneyContext.Provider>;
}

export function useMoney(): Money {
  const ctx = useContext(MoneyContext);
  if (!ctx) throw new Error("useMoney must be used inside <CurrencyProvider>");
  return ctx;
}
