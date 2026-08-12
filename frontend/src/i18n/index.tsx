import {
  createContext, useCallback, useContext, useEffect, useMemo, useState,
  type ReactNode,
} from "react";
import en from "./en";
import fr from "./fr";
import zh, { type Dict } from "./zh";

export const LOCALES = { zh, en, fr };
export type Locale = keyof typeof LOCALES;
export const LOCALE_ORDER: Locale[] = ["zh", "en", "fr"];

/** BCP-47 tags for Intl — only used for date/number formatting. */
const INTL_TAG: Record<Locale, string> = { zh: "zh-CN", en: "en-US", fr: "fr-FR" };

const STORAGE_KEY = "tokenscope.locale";

function detect(): Locale {
  const saved = localStorage.getItem(STORAGE_KEY);
  if (saved && saved in LOCALES) return saved as Locale;
  const nav = navigator.languages?.[0] ?? navigator.language ?? "en";
  if (nav.startsWith("zh")) return "zh";
  if (nav.startsWith("fr")) return "fr";
  return "en";
}

export type TFunc = (key: string, vars?: Record<string, string | number>) => string;

function lookup(dict: Dict, key: string): string | undefined {
  const hit = key.split(".").reduce<unknown>(
    (o, k) => (o && typeof o === "object" ? (o as Record<string, unknown>)[k] : undefined),
    dict,
  );
  return typeof hit === "string" ? hit : undefined;
}

interface Ctx {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: TFunc;
  /** BCP-47 tag for Intl.* APIs. */
  tag: string;
}

const I18nContext = createContext<Ctx | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(detect);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, locale);
    document.documentElement.lang = INTL_TAG[locale];
  }, [locale]);

  const t = useCallback<TFunc>((key, vars) => {
    // Fall back through English before showing the raw key, so a gap in one
    // dictionary degrades to readable text rather than "guide.s3.readout".
    const raw = lookup(LOCALES[locale], key) ?? lookup(en, key) ?? lookup(zh, key);
    if (raw === undefined) return key;
    return vars
      ? raw.replace(/\{(\w+)\}/g, (_, k: string) => String(vars[k] ?? `{${k}}`))
      : raw;
  }, [locale]);

  const value = useMemo<Ctx>(
    () => ({ locale, setLocale: setLocaleState, t, tag: INTL_TAG[locale] }),
    [locale, t],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): Ctx {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used inside <I18nProvider>");
  return ctx;
}

/** Renders `**bold**` segments — keeps emphasis inside translatable prose
 *  instead of splitting every sentence into fragments around <b> tags. */
export function Rich({ text, className }: { text: string; className?: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return (
    <span className={className}>
      {parts.map((p, i) =>
        p.startsWith("**") && p.endsWith("**") && p.length > 4
          ? <b key={i}>{p.slice(2, -2)}</b>
          : <span key={i}>{p}</span>,
      )}
    </span>
  );
}
