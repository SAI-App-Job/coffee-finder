import { SectionHeading, SourceLinks } from "./common";
import { PUBLISHED_DESIGNATED_BRANDS, brandKey, prose } from "../data/published";
import { designatedBrandExplanation, localizeBrand } from "../data/localize";
import { ORIGIN_GUIDE } from "../data/originGuide";
import { useT } from "../i18n";

export function DesignatedBrandsView({ hideHeading = false, onLearnOrigin }) {
  const t = useT();
  return (
    <main className="px-5 py-5 flex flex-col gap-3 max-w-xl mx-auto">
      {!hideHeading && <SectionHeading en="Designated Brands" ja="特定銘柄" />}
      {prose("brands.intro") && <p className="text-[13px] text-[var(--c-text-3)]">{t(prose("brands.intro"))}</p>}
      <div className="flex flex-col gap-2">
        {PUBLISHED_DESIGNATED_BRANDS.map((raw) => {
          const b = localizeBrand(raw);
          const explanation = designatedBrandExplanation(raw.name);
          const matchedOrigin = raw.country ? ORIGIN_GUIDE.find((o) => o.country === raw.country) : null;
          return (
            <button
              key={raw.name}
              disabled={!matchedOrigin}
              onClick={() => matchedOrigin && onLearnOrigin(raw.country)}
              className={`text-left rounded-2xl bg-[var(--c-surface)] border border-[var(--c-border)] p-4 flex flex-col gap-1.5 transition-colors ${
                matchedOrigin ? "hover:border-[var(--accent-label)]" : "opacity-70 cursor-default"
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <p className="font-serif text-[16px] text-[var(--c-text)]">{b.name}</p>
                <span className="shrink-0 text-[11px] px-2 py-0.5 rounded-full bg-[var(--c-surface-2)] text-[var(--accent-muted)] border border-[var(--c-border)]">
                  {t(raw.country ?? "キューバ")}
                </span>
              </div>
              {b.note && <p className="text-[12px] text-[var(--c-text-3)]">{b.note}</p>}
              {explanation && <p className="text-[12px] text-[var(--c-text-2)] leading-relaxed">{explanation}</p>}
              <p className="text-[11px] text-[var(--c-text-3)] leading-relaxed">
                <SourceLinks keys={[brandKey(raw)]} />
              </p>
              {matchedOrigin ? (
                <span className="text-[11px] text-[var(--accent)] mt-1">{t("産地タブでこの国を見る →")}</span>
              ) : (
                <span className="text-[11px] text-[var(--c-text-3)] mt-1">{t("この産地は地図の対象国には未収録です")}</span>
              )}
            </button>
          );
        })}
      </div>
    </main>
  );
}
