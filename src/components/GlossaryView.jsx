import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { SectionHeading, VerifiedSources } from "./common";
import { PUBLISHED_GLOSSARY_TERMS, glossaryKey } from "../data/published";
import { localizeGlossaryTerm } from "../data/localize";
import { useT } from "../i18n";

export function GlossaryItem({ item: rawItem, open, onToggle }) {
  const t = useT();
  const item = localizeGlossaryTerm(rawItem);
  return (
    <div
      className={`rounded-2xl bg-[var(--c-surface)] border-2 overflow-hidden transition-colors ${
        open ? "border-[var(--accent)]" : "border-[var(--c-border)]"
      }`}
    >
      <button
        onClick={onToggle}
        className="w-full flex items-start justify-between gap-3 p-4 text-left"
      >
        <div>
          <span
            className={`text-[11px] px-2 py-0.5 rounded-full border transition-colors ${
              open
                ? "bg-[var(--accent)] text-[var(--on-accent)] border-[var(--accent)] font-medium"
                : "bg-[var(--c-surface-2)] text-[var(--accent-muted)] border-[var(--c-border)]"
            }`}
          >
            {t(item.category)}
          </span>
          <h3 className="font-serif text-[17px] text-[var(--c-text)] mt-1.5">{item.term}</h3>
          <p className="text-[13px] text-[var(--c-text-3)] mt-1">{item.summary}</p>
        </div>
        <ChevronDown
          size={16}
          className={`shrink-0 transition-transform mt-1 ${open ? "rotate-180 text-[var(--accent)]" : "text-[var(--accent-label)]"}`}
        />
      </button>
      {open && (
        <div className="px-4 pb-4 pt-0">
          <p className="text-[13px] leading-relaxed text-[var(--c-text-2)] border-t border-[var(--c-border)] pt-3">
            {item.detail}
          </p>
          <VerifiedSources keys={[glossaryKey(rawItem)]} />
        </div>
      )}
    </div>
  );
}

export function GlossaryView({ hideHeading = false }) {
  const t = useT();
  const [openTerm, setOpenTerm] = useState(null);
  return (
    <main className="px-5 py-5 flex flex-col gap-3 max-w-xl mx-auto">
      {!hideHeading && <SectionHeading en="Glossary" ja="用語解説" />}
      <p className="text-[13px] text-[var(--c-text-3)]">
        {t("精選方法・焙煎度・グレードなど、コーヒー豆選びに役立つ基礎用語をまとめました。")}
      </p>
      {PUBLISHED_GLOSSARY_TERMS.map((item) => (
        <GlossaryItem
          key={item.term}
          item={item}
          open={openTerm === item.term}
          onToggle={() => setOpenTerm(openTerm === item.term ? null : item.term)}
        />
      ))}
    </main>
  );
}
