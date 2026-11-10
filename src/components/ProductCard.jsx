import { memo, useState } from "react";
import { Sparkles, Coffee, MapPin, ExternalLink, Heart } from "lucide-react";
import { PUBLISHED_FACTS, factKey } from "../data/published";
import { SourceLinks } from "./common";
import { brandName, designatedBrandExplanation, localizeFact, processingExplanation } from "../data/localize";
import { ORIGIN_GUIDE } from "../data/originGuide";
import { getGradeExplanation } from "../utils/grade";
import { analyzeFlavorNotes, flavorTagItems } from "../utils/flavor";
import { cityFromAddress, formatDate, formatPrice } from "../utils/format";
import { isNewArrival } from "../utils/productSort";
import { useT } from "../i18n";
import { useAppNavigation } from "../hooks/useAppNavigation";

export function DiscoveryFactCard() {
  const t = useT();
  const [index, setIndex] = useState(() => Math.floor(Math.random() * PUBLISHED_FACTS.length));
  // 出典を確認できた豆知識だけを出す。1話も無ければ、カード自体を出さない。
  if (PUBLISHED_FACTS.length === 0) return null;
  const rawFact = PUBLISHED_FACTS[index % PUBLISHED_FACTS.length];
  const fact = localizeFact(rawFact);

  const showAnother = () => {
    setIndex((prev) => {
      if (PUBLISHED_FACTS.length <= 1) return prev;
      let next = Math.floor(Math.random() * PUBLISHED_FACTS.length);
      while (next === prev) next = Math.floor(Math.random() * PUBLISHED_FACTS.length);
      return next;
    });
  };

  return (
    <div className="rounded-2xl bg-[var(--c-surface)] border border-[var(--c-border)] p-4 flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <Sparkles size={13} className="text-[var(--accent)]" strokeWidth={1.75} />
          <p className="text-[11px] tracking-[0.15em] text-[var(--accent-label)] uppercase">Discovery</p>
        </div>
        <button
          onClick={showAnother}
          className="text-[11px] text-[var(--c-text-3)] hover:text-[var(--accent)] transition-colors"
        >
          {t("別の話を見る")}
        </button>
      </div>
      <h3 className="font-serif text-[16px] text-[var(--c-text)]">{fact.title}</h3>
      <p className="text-[13px] leading-relaxed text-[var(--c-text-2)]">{fact.text}</p>
      <p className="text-[11px] text-[var(--c-text-3)] leading-relaxed">
        <SourceLinks keys={[factKey(rawFact)]} />
      </p>
    </div>
  );
}

// onMore: 渡すと、ふきだしの下に「用語解説で詳しく見る」のリンクを出す(出典の一覧は、移動先で見る)
export function HoverExplainTag({ label, category, detail, sourceKeys, moreLabel, onMore }) {
  const t = useT();
  // マウスホバーで解説をポップ表示するタグ。タッチ端末では代わりにタップで
  // 開閉できるよう、ホバーとクリックの両方をトリガーにしている。
  //
  // ふきだしの配置・背景色はTailwindクラスに頼らずインラインstyleで指定している。
  // 以前、Tailwindの任意値クラスが環境によって解釈されない不具合が発生したため、
  // 見た目の根幹に関わる部分(背景の不透明度・重なり順)は確実な方法を優先した。
  const [open, setOpen] = useState(false);

  return (
    <span
      style={{ position: "relative", display: "inline-block" }}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        onClick={(e) => {
          e.stopPropagation();
          setOpen((o) => !o);
        }}
        className="text-[11px] px-2 py-0.5 rounded-full bg-[var(--c-surface-2)] text-[var(--accent-muted)] border border-[var(--c-border)] border-dashed hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors"
      >
        {label}
      </button>

      {open && detail && (
        <div
          style={{
            position: "absolute",
            zIndex: 50,
            bottom: "calc(100% + 8px)",
            left: "50%",
            transform: "translateX(-50%)",
            width: 224,
            borderRadius: 12,
            backgroundColor: "#100b07",
            border: "1px solid var(--c-border)",
            padding: 12,
            boxShadow: "0 8px 24px rgba(0,0,0,0.55)",
          }}
        >
          <p
            style={{
              margin: 0,
              fontSize: 10,
              color: "#C99A5B",
              textTransform: "uppercase",
              letterSpacing: "0.05em",
            }}
          >
            {category}
          </p>
          <p
            style={{
              marginTop: 4,
              marginBottom: 0,
              fontSize: 12,
              lineHeight: 1.6,
              color: "#E8DCC8",
            }}
          >
            {detail}
          </p>
          {onMore ? (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onMore();
              }}
              style={{ marginTop: 8, padding: 0, background: "none", border: "none", fontSize: 11, color: "#C99A5B", textDecoration: "underline", textUnderlineOffset: 2, cursor: "pointer" }}
            >
              {moreLabel ?? t("用語解説で詳しく見る")} →
            </button>
          ) : (
            sourceKeys && sourceKeys.length > 0 && (
              <p style={{ marginTop: 6, marginBottom: 0, fontSize: 10, lineHeight: 1.5, color: "#A89880" }}>
                <SourceLinks keys={sourceKeys} collapse={false} />
              </p>
            )
          )}
          {/* ふきだしの三角形 */}
          <div
            style={{
              position: "absolute",
              left: "50%",
              transform: "translateX(-50%)",
              top: "100%",
              width: 0,
              height: 0,
              borderLeft: "6px solid transparent",
              borderRight: "6px solid transparent",
              borderTop: "6px solid var(--c-border)",
            }}
          />
        </div>
      )}
    </span>
  );
}

// 一覧カードに出す風味タグの最大数(残りは詳細画面で見られる)
const FLAVOR_TAG_LIMIT = 6;

// savedAt: コレクションに保存した日時(コレクション画面でだけ渡す)
function ProductCardImpl({ product, onOpenMap, onLearnOrigin, isFavorite, onToggleFavorite, onOpenDetail, savedAt }) {
  const t = useT();
  const navigate = useAppNavigation();
  const processingDetail = product.processingMethod
    ? processingExplanation(product.processingMethod)
    : null;
  const gradeDetail = getGradeExplanation(product.grade, product.originCountry, product.designatedBrand);
  const brandExplanation = product.designatedBrand ? designatedBrandExplanation(product.designatedBrand) : null;
  const flavorTags = flavorTagItems(analyzeFlavorNotes(product.flavorNotes));
  const flavorTagsShown = flavorTags.slice(0, FLAVOR_TAG_LIMIT);
  // 産地タブに詳細ページが無い国は、ボタン自体は表示したままグレーアウトする
  // (非表示にすると「情報が無いこと」自体が伝わらないため)。実際の遷移可否・
  // 未収録時のトースト表示はApp.jsxのlearnAboutOrigin側で一元的に判定する。
  const hasOriginGuide = ORIGIN_GUIDE.some((o) => o.country === product.originCountry);

  const staticTags = [product.farmNote].filter(Boolean);
  // 焙煎度がわかっている商品は文字のタグで示す(「注文時に選択」の商品は、専用のタグが別にある)
  const roastTag = product.roast && !product.roastSelectable ? product.roast : null;
  const favorited = isFavorite?.(product.id) ?? false;
  // ブレンドは単一のoriginCountryを持たないため、構成国をタグとして
  // 表示する(ストレート商品の産地表示と同じ見た目=既存のタグpillスタイルを流用)
  const blendCountries = product.blendComponents?.length
    ? [...new Set(product.blendComponents.map((c) => c.originCountry).filter(Boolean))]
    : [];

  return (
    <div
      className={`relative rounded-2xl bg-[var(--c-surface)] border border-[var(--c-border)] flex ${onOpenDetail ? "cursor-pointer" : ""}`}
      onClick={() => onOpenDetail?.(product)}
      role={onOpenDetail ? "button" : undefined}
      tabIndex={onOpenDetail ? 0 : undefined}
    >
      <div className="flex-1 p-4 flex flex-col gap-2.5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-1.5 flex-wrap">
              {blendCountries.length > 0 ? (
                blendCountries.map((country) => (
                  <span
                    key={country}
                    className="text-[11px] px-2 py-0.5 rounded-full bg-[var(--c-surface-2)] text-[var(--accent-muted)] border border-[var(--c-border)]"
                  >
                    {t(country)}
                  </span>
                ))
              ) : (
                <p className="text-[11px] tracking-wider text-[var(--accent-label)] font-medium uppercase">
                  {t(product.originCountry)}
                </p>
              )}
              {product.stockStatus && product.stockStatus !== "販売中" && (
                <span
                  className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium leading-none ${
                    product.stockStatus === "終売"
                      ? "bg-[var(--c-surface-2)] text-[var(--c-text-3)] border border-[var(--c-border)]"
                      : "bg-[#4A2E12] text-[#E8B86D] border border-[#6B4A22]"
                  }`}
                >
                  {product.stockStatus === "終売" ? t("終売") : t("売り切れ")}
                </span>
              )}
              {isNewArrival(product) && (
                <span className="text-[10px] px-1.5 py-0.5 rounded-full font-medium leading-none bg-[var(--accent-glow)] text-[var(--accent-on-glow)] border border-[var(--accent-label)]">
                  {t("新規掲載")}
                </span>
              )}
            </div>
            <h3 className="font-serif text-[17px] leading-snug text-[var(--c-text)] mt-0.5">
              {product.rawName}
            </h3>
          </div>
          <div className="text-right shrink-0 flex flex-col items-end gap-1">
            <button
              onClick={(e) => {
                e.stopPropagation();
                onToggleFavorite?.(product.id);
              }}
              aria-label={favorited ? t("コレクションから削除") : t("コレクションに追加")}
              aria-pressed={favorited}
              className="p-1 -m-1 text-[var(--c-text-3)] hover:text-[var(--accent)] transition-colors"
            >
              <Heart
                size={17}
                strokeWidth={2}
                className={favorited ? "fill-[var(--accent)] text-[var(--accent)]" : ""}
              />
            </button>
            <p className="font-mono text-[var(--c-text)] text-[15px] max-w-[100px] whitespace-normal break-words">
              {formatPrice(product) ?? (product.priceNote ? t("要問合せ") : t("価格未確認"))}
            </p>
            {typeof product.weightG === "number" && (
              <p className="font-mono text-[11px] text-[var(--c-text-3)]">{product.weightG}g</p>
            )}
          </div>
        </div>

        {(product.designatedBrand || staticTags.length > 0 || product.processingMethod || product.grade || roastTag || product.roastSelectable || flavorTags.length > 0) && (
          <div className="flex flex-wrap gap-1.5">
            {product.designatedBrand && (
              <HoverExplainTag
                label={brandName(product.designatedBrand)}
                category={t("特定銘柄")}
                detail={brandExplanation || t("この銘柄についての解説はまだ用意されていません。")}
                moreLabel={t("特定銘柄の解説で詳しく見る")}
                onMore={() => navigate({ page: "trivia", sub: "brands" })}
              />
            )}
            {product.processingMethod && (
              <HoverExplainTag
                label={t(product.processingMethod)}
                category={t("精選方法")}
                detail={processingDetail || t("この精選方法についての解説はまだ用意されていません。")}
                onMore={() => navigate({ page: "trivia", sub: "glossary" })}
              />
            )}
            {product.grade && (
              <HoverExplainTag
                label={product.grade}
                category={t("グレード")}
                detail={gradeDetail}
                onMore={() => navigate({ page: "trivia", sub: "glossary" })}
              />
            )}
            {roastTag && (
              <span
                title={t("焙煎度: {roast}", { roast: t(roastTag) })}
                className="text-[11px] px-2 py-0.5 rounded-full bg-[var(--c-surface-2)] text-[var(--accent-muted)] border border-[var(--c-border)] max-w-[220px] truncate whitespace-nowrap"
              >
                {t("焙煎 {roast}", { roast: t(roastTag) })}
              </span>
            )}
            {flavorTagsShown.map((item) => (
              <HoverExplainTag
                key={item.key}
                label={
                  <span className="flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: item.cat.color }} />
                    {t(item.label)}
                  </span>
                }
                category={t(item.cat.ja)}
                detail={
                  item.word
                    ? t("テイスティングノート「{notes}」に「{word}」の記載があるため、アプリ独自の風味カテゴリ「{cat}」の「{term}」に自動分類。", { notes: product.flavorNotes, word: item.word, cat: t(item.cat.ja), term: t(item.label) })
                    : t("テイスティングノート「{notes}」から、アプリ独自の風味カテゴリ「{cat}」に該当すると自動分類。", { notes: product.flavorNotes, cat: t(item.cat.ja) })
                }
              />
            ))}
            {flavorTags.length > flavorTagsShown.length && (
              <span className="text-[11px] px-1 py-0.5 text-[var(--c-text-3)]">
                {t("ほか{n}件", { n: flavorTags.length - flavorTagsShown.length })}
              </span>
            )}
            {staticTags.map((tag) => (
              // farmNoteは店舗によって数百字の自由記述になり得るため(例:
              // COFFEE ROASTERY MEGUROの産地解説)、一覧カードでは1行に
              // truncateして簡潔に表示する。全文は商品詳細モーダル
              // (ProductDetailModalのDetailRow)側で省略せず表示する。
              <span
                key={tag}
                title={tag}
                className="text-[11px] px-2 py-0.5 rounded-full bg-[var(--c-surface-2)] text-[var(--accent-muted)] border border-[var(--c-border)] max-w-[220px] truncate whitespace-nowrap"
              >
                {tag}
              </span>
            ))}
            {product.roastSelectable && (
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-transparent text-[var(--c-text-3)] border border-dashed border-[var(--c-border)]">
                {t("焙煎度は注文時に選択")}
              </span>
            )}
          </div>
        )}

        <div className="flex items-center justify-between pt-1.5 mt-auto border-t border-[var(--c-border)]">
          <div className="flex items-center gap-1 text-[12px] text-[var(--c-text-3)]">
            <Coffee size={13} strokeWidth={1.75} />
            <span>{product.shopName}</span>
            {product.shopAddress && (
              <span className="text-[var(--c-text-3)]/70">・{cityFromAddress(product.shopAddress)}</span>
            )}
          </div>
          <button
            onClick={(e) => {
              e.stopPropagation();
              onOpenMap(product);
            }}
            className="flex items-center gap-1 text-[12px] text-[var(--accent)] hover:text-[var(--accent-soft)] transition-colors"
          >
            <MapPin size={13} strokeWidth={1.75} />
            <span>{t("地図で開く")}</span>
            <ExternalLink size={11} strokeWidth={1.75} />
          </button>
        </div>

        {savedAt && formatDate(savedAt) && (
          <p className="text-[11px] text-[var(--c-text-3)]">{t("登録日 {date}", { date: formatDate(savedAt) })}</p>
        )}

        {onLearnOrigin && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onLearnOrigin(product.originCountry);
            }}
            className={`flex items-center justify-center gap-1.5 text-[12px] py-1 transition-colors ${
              hasOriginGuide
                ? "text-[var(--accent-label)] hover:text-[var(--accent)]"
                : "text-[var(--c-text-3)] opacity-60"
            }`}
          >
            <Sparkles size={12} strokeWidth={1.75} />
            <span>{t("{country}という産地をもっと知る", { country: t(product.originCountry) })}</span>
          </button>
        )}
      </div>
    </div>
  );
}

// 仮想化リスト(Virtuoso)配下で使われるため、isFavorite/onToggleFavorite等の
// 関数propsが呼び出し側で再生成されない限り、無関係な状態変化での再描画を
// 避けるためmemo化している。
export const ProductCard = memo(ProductCardImpl);
