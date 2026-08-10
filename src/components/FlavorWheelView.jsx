import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { SectionHeading, SourceCredit } from "./common";
import { FLAVOR_WHEEL_DATA } from "../data/flavorWheel";

export function FlavorWheelCategory({ cat, open, onToggle }) {
  return (
    <div
      className="rounded-2xl bg-[#2F241A] border overflow-hidden"
      style={{ borderColor: open ? cat.color : "#4A3A2A" }}
    >
      <button onClick={onToggle} className="w-full flex items-center justify-between gap-3 p-3.5 text-left">
        <div className="flex items-center gap-2.5">
          <span className="w-3 h-3 rounded-full shrink-0" style={{ backgroundColor: cat.color }} />
          <div>
            <p className="text-[10px] tracking-[0.1em] uppercase" style={{ color: cat.color }}>{cat.en}</p>
            <p className="text-[14px] font-medium text-[#F2E9DD]">{cat.ja}</p>
          </div>
        </div>
        <ChevronDown
          size={15}
          className={`shrink-0 text-[#8B5E2E] transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open && (
        <div className="px-3.5 pb-3.5 flex flex-col gap-2.5 border-t border-[#4A3A2A] pt-3">
          {cat.sub.map((s) => (
            <div key={s.group}>
              <p className="text-[11px] text-[#8B7361] mb-1">{s.group}</p>
              <div className="flex flex-wrap gap-1.5">
                {s.terms.map((t) => (
                  <span
                    key={t}
                    className="text-[12px] px-2.5 py-1 rounded-full bg-[#3B2211] text-[#C9A876] border border-[#4A3A2A]"
                  >
                    {t}
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
  return (
    <main className="px-5 py-5 flex flex-col gap-3 max-w-xl mx-auto">
      {!hideHeading && <SectionHeading en="Flavor Wheel" ja="フレーバーホイール" />}
      <p className="text-[13px] text-[#8B7361]">
        SCA(スペシャルティコーヒー協会)とWCR(ワールドコーヒーリサーチ)が2016年に共同開発した、コーヒーの風味を語るための共通言語。9つの大分類をタップすると、含まれる具体的な表現が開きます。
      </p>
      <FlavorWheelExplorer />
      <div className="text-[11px] text-[#8B7361] leading-relaxed border-t border-[#4A3A2A] pt-3 mt-1">
        <p>
          円形の公式図(SCA/WCR著作物)はそのまま複製せず、公開されている用語データを独自のカード形式に再構成しています。実際の円形の図はSCAの公式サイトで確認・購入できます。
        </p>
      </div>
      <SourceCredit sources={["SCA(Specialty Coffee Association)", "WCR(World Coffee Research)Sensory Lexicon"]} />
    </main>
  );
}
