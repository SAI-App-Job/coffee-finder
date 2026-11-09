import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { SectionHeading, VerifiedSources } from "./common";
import { IS_FLAVOR_WHEEL_PUBLISHED, FLAVOR_WHEEL_KEY, prose, proseKey } from "../data/published";
import { FLAVOR_WHEEL_DATA } from "../data/flavorWheel";
import { useT } from "../i18n";

export function FlavorWheelCategory({ cat, open, onToggle }) {
  const t = useT();
  return (
    <div
      className="rounded-2xl bg-[var(--c-surface)] border overflow-hidden"
      style={{ borderColor: open ? cat.color : "var(--c-border)" }}
    >
      <button onClick={onToggle} className="w-full flex items-center justify-between gap-3 p-3.5 text-left">
        <div className="flex items-center gap-2.5">
          <span className="w-3 h-3 rounded-full shrink-0" style={{ backgroundColor: cat.color }} />
          <div>
            <p
              className="text-[10px] tracking-[0.1em] uppercase"
              style={{ color: `color-mix(in srgb, ${cat.color} calc(100% - var(--label-darken)), black)` }}
            >
              {cat.en}
            </p>
            <p className="text-[14px] font-medium text-[var(--c-text)]">{t(cat.ja)}</p>
          </div>
        </div>
        <ChevronDown
          size={15}
          className={`shrink-0 text-[var(--accent-label)] transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open && (
        <div className="px-3.5 pb-3.5 flex flex-col gap-2.5 border-t border-[var(--c-border)] pt-3">
          {cat.sub.map((s) => (
            <div key={s.group}>
              <p className="text-[11px] text-[var(--c-text-3)] mb-1">{t(s.group)}</p>
              <div className="flex flex-wrap gap-1.5">
                {s.terms.map((term) => (
                  <span
                    key={term}
                    className="text-[12px] px-2.5 py-1 rounded-full bg-[var(--c-surface-2)] text-[var(--accent-muted)] border border-[var(--c-border)]"
                  >
                    {t(term)}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function FlavorWheelExplorer() {
  const [openCat, setOpenCat] = useState(null);
  return (
    <div className="flex flex-col gap-2">
      {FLAVOR_WHEEL_DATA.map((cat) => (
        <FlavorWheelCategory
          key={cat.en}
          cat={cat}
          open={openCat === cat.en}
          onToggle={() => setOpenCat(openCat === cat.en ? null : cat.en)}
        />
      ))}
    </div>
  );
}

export function FlavorWheelView({ hideHeading = false }) {
  const t = useT();
  return (
    <main className="px-5 py-5 flex flex-col gap-3 max-w-xl mx-auto">
      {!hideHeading && <SectionHeading en="Flavor Wheel" ja="フレーバーホイール" />}
      {IS_FLAVOR_WHEEL_PUBLISHED && (
        <>
          {prose("flavorwheel.intro") && <p className="text-[13px] text-[var(--c-text-3)]">{t(prose("flavorwheel.intro"))}</p>}
          <FlavorWheelExplorer />
          {prose("flavorwheel.note") && (
            <div className="text-[11px] text-[var(--c-text-3)] leading-relaxed border-t border-[var(--c-border)] pt-3 mt-1">
              <p>{t(prose("flavorwheel.note"))}</p>
            </div>
          )}
          <VerifiedSources
            keys={[FLAVOR_WHEEL_KEY, ...(prose("flavorwheel.intro") ? [proseKey("flavorwheel.intro")] : []), ...(prose("flavorwheel.note") ? [proseKey("flavorwheel.note")] : [])]}
          />
        </>
      )}
    </main>
  );
}
