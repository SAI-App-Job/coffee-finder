import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { SectionHeading } from "./common";
import { GLOSSARY_TERMS } from "../data/glossary";

export function GlossaryItem({ item, open, onToggle }) {
  return (
    <div
      className={`rounded-2xl bg-[#2F241A] border-2 overflow-hidden transition-colors ${
        open ? "border-[var(--accent)]" : "border-[#4A3A2A]"
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
                ? "bg-[var(--accent)] text-[#231810] border-[var(--accent)] font-medium"
                : "bg-[#3B2211] text-[var(--accent-muted)] border-[#4A3A2A]"
            }`}
          >
            {item.category}
          </span>
          <h3 className="font-serif text-[17px] text-[#F2E9DD] mt-1.5">{item.term}</h3>
          <p className="text-[13px] text-[#8B7361] mt-1">{item.summary}</p>
        </div>
        <ChevronDown
          size={16}
          className={`shrink-0 transition-transform mt-1 ${open ? "rotate-180 text-[var(--accent)]" : "text-[var(--accent-label)]"}`}
        />
      </button>
      {open && (
        <div className="px-4 pb-4 pt-0">
          <p className="text-[13px] leading-relaxed text-[#B8A891] border-t border-[#4A3A2A] pt-3">
            {item.detail}
          </p>
        </div>
      )}
    </div>
  );
}

export function GlossaryView({ hideHeading = false }) {
  const [openTerm, setOpenTerm] = useState(null);
  return (
    <main className="px-5 py-5 flex flex-col gap-3 max-w-xl mx-auto">
      {!hideHeading && <SectionHeading en="Glossary" ja="用語解説" />}
      <p className="text-[13px] text-[#8B7361]">
        精選方法・焙煎度・グレードなど、コーヒー豆選びに役立つ基礎用語をまとめました。
      </p>
      {GLOSSARY_TERMS.map((item) => (
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
