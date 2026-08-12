import { LOCALES, LOCALE_ORDER, useI18n, type Locale } from "../i18n";

const SHORT: Record<Locale, string> = { zh: "中", en: "EN", fr: "FR" };

export default function LocaleSwitcher() {
  const { locale, setLocale, t } = useI18n();
  return (
    <div
      className="inline-flex rounded border border-border-card p-0.5 text-sm"
      role="group"
      aria-label={t("nav.language")}
    >
      {LOCALE_ORDER.map((l) => (
        <button
          key={l}
          onClick={() => setLocale(l)}
          title={LOCALES[l].localeName}
          aria-pressed={locale === l}
          className={`min-w-[34px] rounded px-2 py-1 transition-colors ${
            locale === l
              ? "bg-primary-container font-semibold text-on-primary"
              : "text-on-surface-variant hover:bg-surface"
          }`}
        >
          {SHORT[l]}
        </button>
      ))}
    </div>
  );
}
