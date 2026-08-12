import { Coffee, Thermometer, Timer, Award, SlidersHorizontal } from "lucide-react";
import { SectionHeading, SourceCredit } from "./common";
import { BREW_METHODS, EXTRACTION_VARIABLES, EXTRACTION_DIAGNOSIS } from "../data/brewGuide";

export function BrewMethodCard({ brew }) {
  return (
    <div className="rounded-2xl bg-[#2F241A] border border-[#4A3A2A] p-4 flex flex-col gap-3">
      <div>
        <p className="text-[11px] tracking-[0.15em] text-[var(--accent-label)] uppercase">{brew.english}</p>
        <h3 className="font-serif text-[19px] text-[#F2E9DD] mt-0.5">{brew.method}</h3>
        <p className="text-[13px] text-[var(--accent)] mt-1">{brew.tagline}</p>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <div className="bg-[#3B2211] rounded-lg p-2 flex flex-col items-center gap-1 text-center">
          <Coffee size={13} className="text-[var(--accent-label)]" strokeWidth={1.75} />
          <span className="text-[11px] text-[#B8A891] leading-tight">{brew.ratio}</span>
        </div>
        <div className="bg-[#3B2211] rounded-lg p-2 flex flex-col items-center gap-1 text-center">
          <Thermometer size={13} className="text-[var(--accent-label)]" strokeWidth={1.75} />
          <span className="text-[11px] text-[#B8A891] leading-tight">{brew.temp}</span>
        </div>
        <div className="bg-[#3B2211] rounded-lg p-2 flex flex-col items-center gap-1 text-center">
          <Timer size={13} className="text-[var(--accent-label)]" strokeWidth={1.75} />
          <span className="text-[11px] text-[#B8A891] leading-tight">{brew.time}</span>
        </div>
      </div>

      {brew.grindSize && (
        <p className="text-[12px] text-[#B8A891]">
          <span className="text-[var(--accent-label)]">粒度:</span> {brew.grindSize}
        </p>
      )}

      <ol className="flex flex-col gap-2">
        {brew.steps.map((step, i) => (
          <li key={i} className="flex gap-2.5 text-[13px] text-[#B8A891] leading-relaxed">
            <span className="shrink-0 w-5 h-5 rounded-full bg-[#3B2211] border border-[#4A3A2A] text-[var(--accent)] text-[11px] flex items-center justify-center font-mono">
              {i + 1}
            </span>
            {step}
          </li>
        ))}
      </ol>

      <div className="flex items-start gap-1.5 text-[12px] text-[#8B7361] bg-[#3B2211] rounded-lg p-2.5">
        <Award size={13} className="shrink-0 mt-0.5 text-[var(--accent-label)]" strokeWidth={1.75} />
        <span>{brew.pairing}</span>
      </div>
      {brew.calibration && (
        <div className="flex items-start gap-1.5 text-[12px] text-[#8B7361] border-t border-[#4A3A2A] pt-2.5">
          <SlidersHorizontal size={13} className="shrink-0 mt-0.5 text-[var(--accent-label)]" strokeWidth={1.75} />
          <span>{brew.calibration}</span>
        </div>
      )}
    </div>
  );
}

export function ExtractionVariableCard({ v }) {
  return (
    <div className="rounded-xl bg-[#3B2211] border border-[#4A3A2A] p-3">
      <p className="text-[13px] text-[#F2E9DD] font-medium">{v.title}</p>
      <p className="text-[12px] text-[var(--accent)] mt-0.5">{v.summary}</p>
      <p className="text-[12px] text-[#B8A891] leading-relaxed mt-1.5">{v.detail}</p>
    </div>
  );
}

export function ExtractionScienceSection() {
  return (
    <div className="rounded-2xl bg-[#2F241A] border border-[#4A3A2A] p-4 flex flex-col gap-3">
      <div>
        <p className="text-[11px] tracking-[0.15em] text-[var(--accent-label)] uppercase">Extraction Science</p>
        <h3 className="font-serif text-[19px] text-[#F2E9DD] mt-0.5">抽出理論:なぜ濃さ・酸味・苦味が変わるのか</h3>
        <p className="text-[13px] text-[#B8A891] mt-1.5 leading-relaxed">
          SCA(スペシャルティコーヒー協会)の「ゴールデンカップ基準」は、抽出強度(TDS)1.15〜1.35%・抽出収率18〜22%を適正抽出の目安として定めている。粒度・焙煎度・湯温・時間は、すべてこの「どこまで成分が溶け出したか」を左右する変数として連動している。
        </p>
      </div>

      <div className="flex flex-col gap-2.5">
        {EXTRACTION_VARIABLES.map((v) => (
          <ExtractionVariableCard key={v.key} v={v} />
        ))}
      </div>

      <div>
        <p className="text-[11px] tracking-wide text-[var(--accent-label)] uppercase mb-2">未抽出・適正・過抽出の見分け方</p>
        <div className="flex flex-col gap-2">
          {EXTRACTION_DIAGNOSIS.map((d) => (
            <div key={d.label} className="bg-[#3B2211] rounded-lg p-2.5">
              <p className="text-[13px] text-[#F2E9DD] font-medium">{d.label}</p>
              <p className="text-[12px] text-[#8B7361] mt-0.5">原因: {d.cause}</p>
              <p className="text-[12px] text-[#B8A891] mt-0.5">味わい: {d.taste}</p>
            </div>
          ))}
        </div>
      </div>

      <SourceCredit
        sources={[
          "SCA(Specialty Coffee Association)Golden Cup Standard",
          "科学論文(ScienceDirect, Nature Scientific Reports 等)の抽出動態研究",
        ]}
      />
    </div>
  );
}

export function BrewGuideView({ hideHeading = false }) {
  return (
    <main className="px-5 py-5 flex flex-col gap-3 max-w-xl mx-auto">
      {!hideHeading && <SectionHeading en="Brewing Guide" ja="コーヒーの淹れ方" />}
      <p className="text-[13px] text-[#8B7361] mb-1">
        代表的な4つの抽出方法と、豆の焙煎度との相性をまとめました。
      </p>
      {BREW_METHODS.map((brew) => (
        <BrewMethodCard key={brew.method} brew={brew} />
      ))}
      <ExtractionScienceSection />
    </main>
  );
}
