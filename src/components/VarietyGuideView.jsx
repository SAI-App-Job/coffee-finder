import { SectionHeading, VerifiedSources } from "./common";
import { PUBLISHED_VARIETIES, varietyKey, prose } from "../data/published";
import { localizeVariety } from "../data/localize";
import { useT } from "../i18n";

export function VarietyCard({ v: rawV }) {
  const v = localizeVariety(rawV);
  return (
    <div className="rounded-2xl bg-[var(--c-surface)] border border-[var(--c-border)] p-4 flex flex-col gap-2.5">
      <div>
        <p className="text-[11px] tracking-[0.15em] text-[var(--accent-label)] uppercase">{v.english}</p>
        <h3 className="font-serif text-[19px] text-[var(--c-text)] mt-0.5">{v.lineage}</h3>
        <p className="text-[13px] text-[var(--accent)] mt-1">{v.tagline}</p>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {v.varieties.map((name) => (
          <span
            key={name}
            className="text-[12px] px-2.5 py-1 rounded-full bg-[var(--c-surface-2)] text-[var(--accent-muted)] border border-[var(--c-border)]"
          >
            {name}
          </span>
        ))}
      </div>

      <p className="text-[13px] leading-relaxed text-[var(--c-text-2)] border-t border-[var(--c-border)] pt-3">
        {v.note}
      </p>
      <VerifiedSources keys={[varietyKey(rawV)]} />
    </div>
  );
}

export function VarietyGuideView({ hideHeading = false }) {
  const t = useT();
  return (
    <main className="px-5 py-5 flex flex-col gap-3 max-w-xl mx-auto">
      {!hideHeading && <SectionHeading en="Coffee Varieties" ja="品種" />}
      {prose("variety.intro") && (
        <p className="text-[13px] text-[var(--c-text-3)] mb-1">{t(prose("variety.intro"))}</p>
      )}
      {PUBLISHED_VARIETIES.map((v) => (
        <VarietyCard key={v.lineage} v={v} />
      ))}
    </main>
  );
}
