import { useState, useRef } from "react";
import { Globe2, Clock, Dna, Package, BookOpen, MapPin, Coffee, Award, Gauge } from "lucide-react";
import { SectionHeading, VerifiedSources } from "./common";
import { OriginMapView } from "./OriginMapView";
import { ORIGIN_GUIDE } from "../data/originGuide";
import { PUBLISHED_DESIGNATED_BRANDS, publishedOrigin, gateLocalizedOrigin } from "../data/published";
import { brandName, localizeBrand, localizeOrigin } from "../data/localize";
import { useT } from "../i18n";

export function OriginSection({ icon: Icon, label, children }) {
  if (!children) return null;
  return (
    <div>
      <div className="flex items-center gap-1.5 mb-1">
        <Icon size={12} className="text-[var(--accent-label)]" strokeWidth={1.75} />
        <span className="text-[11px] tracking-wide text-[var(--accent-label)] uppercase">{label}</span>
      </div>
      <p className="text-[13px] leading-relaxed text-[var(--c-text-2)]">{children}</p>
    </div>
  );
}

export function OriginGuideCard({ origin: rawOrigin, onViewProducts }) {
  const t = useT();
  // 出典を確認できた項目だけを出す(判定は日本語の原文。台帳: origin:<国>:<項目>)
  const published = publishedOrigin(rawOrigin);
  const origin = gateLocalizedOrigin(localizeOrigin(rawOrigin), rawOrigin);
  const relatedBrands = PUBLISHED_DESIGNATED_BRANDS.filter((b) => b.country === origin.country);
  const hasDetail = published.keys.length > 0;

  return (
    <div className="rounded-2xl bg-[var(--c-surface)] border border-[var(--c-border)] p-4 flex flex-col gap-2.5">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Globe2 size={15} className="text-[var(--accent-label)]" strokeWidth={1.75} />
          <h3 className="font-serif text-[18px] text-[var(--c-text)]">{t(origin.country)}</h3>
        </div>
        {onViewProducts && (
          <button
            onClick={() => onViewProducts(origin.country)}
            className="flex items-center gap-1 shrink-0 text-[11px] px-2.5 py-1.5 rounded-full bg-[var(--accent)] text-[var(--on-accent)] font-medium hover:bg-[var(--accent-soft)] transition-colors"
          >
            <Coffee size={11} strokeWidth={2} />
            {t("この産地の商品を見る")}
          </button>
        )}
      </div>
      {origin.tagline && <p className="text-[13px] text-[var(--accent)]">{origin.tagline}</p>}
      {origin.regions && <p className="text-[12px] text-[var(--c-text-3)]">{t("代表地域: {regions}", { regions: origin.regions })}</p>}

      {relatedBrands.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 pt-1">
          <span className="text-[11px] text-[var(--c-text-3)]">{t("この産地の特定銘柄:")}</span>
          {relatedBrands.map((b) => (
            <span
              key={b.name}
              className="text-[12px] px-2.5 py-1 rounded-full bg-[var(--accent)] text-[var(--on-accent)] font-medium"
              title={localizeBrand(b).note ?? undefined}
            >
              {brandName(b.name)}
            </span>
          ))}
        </div>
      )}

      {hasDetail ? (
        <div className="pt-2 mt-1 border-t border-[var(--c-border)] flex flex-col gap-3.5">
          <OriginSection icon={Globe2} label={t("Terroir / テロワール")}>{origin.terroir}</OriginSection>
          <OriginSection icon={Clock} label={t("Harvest / 収穫時期")}>{origin.harvestSeason}</OriginSection>
          <OriginSection icon={Dna} label={t("Varieties / 栽培品種")}>{origin.varietiesDetail}</OriginSection>
          <OriginSection icon={Package} label={t("Farm Structure / 農園規模")}>{origin.farmStructure}</OriginSection>
          <OriginSection icon={BookOpen} label={t("History / 歴史")}>{origin.history}</OriginSection>
          <OriginSection icon={Gauge} label={t("Grade System / グレード基準")}>{origin.gradeSystem}</OriginSection>

          {origin.subRegions && origin.subRegions.length > 0 && (
            <div>
              <div className="flex items-center gap-1.5 mb-2">
                <MapPin size={12} className="text-[var(--accent-label)]" strokeWidth={1.75} />
                <span className="text-[11px] tracking-wide text-[var(--accent-label)] uppercase">{t("Sub-Regions / サブリージョン")}</span>
              </div>
              <div className="flex flex-col gap-2">
                {origin.subRegions.map((sr) => (
                  <div key={sr.name} className="bg-[var(--c-surface-2)] rounded-lg p-2.5">
                    <p className="text-[13px] text-[var(--c-text)] font-medium mb-0.5">{sr.name}</p>
                    <p className="text-[12px] text-[var(--c-text-2)] leading-relaxed">{sr.detail}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {origin.officialBody && (
            <div className="flex items-start gap-1.5 text-[12px] text-[var(--c-text-3)] bg-[var(--c-surface-2)] rounded-lg p-2.5">
              <Award size={13} className="shrink-0 mt-0.5 text-[var(--accent-label)]" strokeWidth={1.75} />
              <span>{origin.officialBody}</span>
            </div>
          )}

          <VerifiedSources keys={published.keys} />
        </div>
      ) : (
        <div className="pt-2 mt-1 border-t border-[var(--c-border)] flex flex-col gap-2">
          <p className="text-[13px] leading-relaxed text-[var(--c-text-2)]">
            {t("この国の解説は、出典の確認が済み次第、公開します。")}
          </p>
        </div>
      )}
    </div>
  );
}

export function BuyingGuideView({ pendingOriginCountry, onViewProducts }) {
  const t = useT();
  // 商品一覧の「産地をもっと知る」から遷移してきた場合、その産地国を初期選択にする。
  // このビューはタブ切り替えのたびにアンマウント/再マウントされるため、
  // useStateの初期値関数だけで最新のpendingOriginCountryを反映できる。
  const [selected, setSelected] = useState(() => {
    if (pendingOriginCountry) {
      const matched = ORIGIN_GUIDE.find((o) => o.country === pendingOriginCountry);
      if (matched) return matched;
    }
    return ORIGIN_GUIDE[0];
  });

  // ピン(国名)をタップした際、下の詳細カードまで自動でスクロールする。
  // 初期表示時(pendingOriginCountryによる自動選択)ではスクロールさせたくないため、
  // このハンドラは地図からのタップ操作(onSelect)からのみ呼ばれるようにしている。
  //
  // scroll-margin-top + scrollIntoView() で試したところ、詳細カード上部の
  // 国名が隠れるほどスクロールしすぎる不具合が実機で発生した。原因切り分けの
  // ためscroll-margin-topには頼らず、スティッキーヘッダーの実際の高さを
  // getBoundingClientRectで測定し、その分だけ差し引いた位置へ
  // window.scrollToで直接スクロールする、より確実な方式に変更している。
  const detailRef = useRef(null);
  const handleSelect = (origin) => {
    setSelected(origin);
    // 選択直後はカードの内容量が変わりレイアウトが変化する途中のため、
    // rAFを2段階挟んでレイアウトが確定してから位置を測定する。
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        const el = detailRef.current;
        const header = document.querySelector("header");
        if (!el) return;
        const headerHeight = header ? header.getBoundingClientRect().height : 0;
        const targetTop = el.getBoundingClientRect().top + window.scrollY - headerHeight - 12;
        window.scrollTo({ top: Math.max(targetTop, 0), behavior: "smooth" });
      });
    });
  };

  return (
    <main className="px-5 py-5 flex flex-col gap-5 max-w-xl mx-auto">
      <SectionHeading en="Origin" ja="産地" />
      <div>
        <p className="text-[13px] text-[var(--c-text-3)] mb-3">
          {t("マップ上のピンをタップすると、その産地の解説が表示されます。解説には、確認した出典を付けています。")}
        </p>
        <OriginMapView origins={ORIGIN_GUIDE} selected={selected} onSelect={handleSelect} />
        <div ref={detailRef} className="mt-3">
          {selected ? (
            <OriginGuideCard origin={selected} onViewProducts={onViewProducts} />
          ) : (
            <p className="text-[13px] text-[var(--c-text-3)] text-center py-8">
              {t("マップから産地を選んでください")}
            </p>
          )}
        </div>
      </div>
    </main>
  );
}
