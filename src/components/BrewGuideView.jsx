import { Coffee, Thermometer, Timer, Award, SlidersHorizontal } from "lucide-react";
import { SectionHeading, VerifiedSources } from "./common";
import {
  PUBLISHED_BREW_METHODS,
  PUBLISHED_EXTRACTION_VARIABLES,
  PUBLISHED_EXTRACTION_DIAGNOSIS,
  brewKey,
  extractionKey,
  diagnosisKey,
  prose,
  proseKey,
} from "../data/published";
import { localizeBrewMethod, localizeExtractionDiagnosis, localizeExtractionVariable } from "../data/localize";
import { useT } from "../i18n";

export function BrewMethodCard({ brew: rawBrew }) {
  const t = useT();
  const brew = localizeBrewMethod(rawBrew);
  return (
    <div className="rounded-2xl bg-[var(--c-surface)] border border-[var(--c-border)] p-4 flex flex-col gap-3">
      <div>
        <p className="text-[11px] tracking-[0.15em] text-[var(--accent-label)] uppercase">{brew.english}</p>
        <h3 className="font-serif text-[19px] text-[var(--c-text)] mt-0.5">{brew.method}</h3>
        {brew.tagline && <p className="text-[13px] text-[var(--accent)] mt-1">{brew.tagline}</p>}
      </div>

      <div className="grid grid-cols-3 gap-2">
        {brew.ratio && (
          <div className="bg-[var(--c-surface-2)] rounded-lg p-2 flex flex-col items-center gap-1 text-center">
            <Coffee size={13} className="text-[var(--accent-label)]" strokeWidth={1.75} />
            <span className="text-[11px] text-[var(--c-text-2)] leading-tight">{brew.ratio}</span>
          </div>
        )}
        {brew.temp && (
          <div className="bg-[var(--c-surface-2)] rounded-lg p-2 flex flex-col items-center gap-1 text-center">
            <Thermometer size={13} className="text-[var(--accent-label)]" strokeWidth={1.75} />
            <span className="text-[11px] text-[var(--c-text-2)] leading-tight">{brew.temp}</span>
          </div>
        )}
        {brew.time && (
          <div className="bg-[var(--c-surface-2)] rounded-lg p-2 flex flex-col items-center gap-1 text-center">
            <Timer size={13} className="text-[var(--accent-label)]" strokeWidth={1.75} />
            <span className="text-[11px] text-[var(--c-text-2)] leading-tight">{brew.time}</span>
          </div>
        )}
      </div>

      {brew.grindSize && (
        <p className="text-[12px] text-[var(--c-text-2)]">
          <span className="text-[var(--accent-label)]">{t("粒度:")}</span> {brew.grindSize}
        </p>
      )}

      <ol className="flex flex-col gap-2">
        {brew.steps.map((step, i) => (
          <li key={i} className="flex gap-2.5 text-[13px] text-[var(--c-text-2)] leading-relaxed">
            <span className="shrink-0 w-5 h-5 rounded-full bg-[var(--c-surface-2)] border border-[var(--c-border)] text-[var(--accent)] text-[11px] flex items-center justify-center font-mono">
              {i + 1}
            </span>
            {step}
          </li>
        ))}
      </ol>

      {brew.pairing && (
        <div className="flex items-start gap-1.5 text-[12px] text-[var(--c-text-3)] bg-[var(--c-surface-2)] rounded-lg p-2.5">
          <Award size={13} className="shrink-0 mt-0.5 text-[var(--accent-label)]" strokeWidth={1.75} />
          <span>{brew.pairing}</span>
        </div>
      )}
      {brew.calibration && (
        <div className="flex items-start gap-1.5 text-[12px] text-[var(--c-text-3)] border-t border-[var(--c-border)] pt-2.5">
          <SlidersHorizontal size={13} className="shrink-0 mt-0.5 text-[var(--accent-label)]" strokeWidth={1.75} />
          <span>{brew.calibration}</span>
        </div>
      )}
      <VerifiedSources keys={[brewKey(rawBrew)]} />
    </div>
  );
}

export function ExtractionVariableCard({ v: rawV }) {
  const v = localizeExtractionVariable(rawV);
  return (
    <div className="rounded-xl bg-[var(--c-surface-2)] border border-[var(--c-border)] p-3">
      <p className="text-[13px] text-[var(--c-text)] font-medium">{v.title}</p>
      {v.summary && <p className="text-[12px] text-[var(--accent)] mt-0.5">{v.summary}</p>}
      {v.detail && <p className="text-[12px] text-[var(--c-text-2)] leading-relaxed mt-1.5">{v.detail}</p>}
    </div>
  );
}

export function ExtractionScienceSection() {
  const t = useT();
  const intro = prose("brew.extractionIntro");
  // 出典を確認できた項目が1つも無ければ、この枠ごと出さない
  if (!intro && PUBLISHED_EXTRACTION_VARIABLES.length === 0 && PUBLISHED_EXTRACTION_DIAGNOSIS.length === 0) return null;
  const sourceKeys = [
    ...(intro ? [proseKey("brew.extractionIntro")] : []),
    ...PUBLISHED_EXTRACTION_VARIABLES.map(extractionKey),
    ...PUBLISHED_EXTRACTION_DIAGNOSIS.map(diagnosisKey),
  ];
  return (
    <div className="rounded-2xl bg-[var(--c-surface)] border border-[var(--c-border)] p-4 flex flex-col gap-3">
      <div>
        <p className="text-[11px] tracking-[0.15em] text-[var(--accent-label)] uppercase">Extraction Science</p>
        <h3 className="font-serif text-[19px] text-[var(--c-text)] mt-0.5">{t("抽出理論:なぜ濃さ・酸味・苦味が変わるのか")}</h3>
        {intro && <p className="text-[13px] text-[var(--c-text-2)] mt-1.5 leading-relaxed">{t(intro)}</p>}
      </div>

      <div className="flex flex-col gap-2.5">
        {PUBLISHED_EXTRACTION_VARIABLES.map((v) => (
          <ExtractionVariableCard key={v.key} v={v} />
        ))}
      </div>

      <div>
        <p className="text-[11px] tracking-wide text-[var(--accent-label)] uppercase mb-2">{t("未抽出・適正・過抽出の見分け方")}</p>
        <div className="flex flex-col gap-2">
          {PUBLISHED_EXTRACTION_DIAGNOSIS.map((raw) => {
            const d = localizeExtractionDiagnosis(raw);
            return (
            <div key={raw.label} className="bg-[var(--c-surface-2)] rounded-lg p-2.5">
              <p className="text-[13px] text-[var(--c-text)] font-medium">{d.label}</p>
              {d.cause && <p className="text-[12px] text-[var(--c-text-3)] mt-0.5">{t("原因: {v}", { v: d.cause })}</p>}
              {d.taste && <p className="text-[12px] text-[var(--c-text-2)] mt-0.5">{t("味わい: {v}", { v: d.taste })}</p>}
            </div>
            );
          })}
        </div>
      </div>

      <VerifiedSources keys={sourceKeys} />
    </div>
  );
}

export function BrewGuideView({ hideHeading = false }) {
  const t = useT();
  return (
    <main className="px-5 py-5 flex flex-col gap-3 max-w-xl mx-auto">
      {!hideHeading && <SectionHeading en="Brewing Guide" ja="コーヒーの淹れ方" />}
      <p className="text-[13px] text-[var(--c-text-3)] mb-1">
        {t("代表的な4つの抽出方法を、製造元や協会の公式の説明に基づいてまとめました。")}
      </p>
      {PUBLISHED_BREW_METHODS.map((brew) => (
        <BrewMethodCard key={brew.method} brew={brew} />
      ))}
      <ExtractionScienceSection />
    </main>
  );
}
