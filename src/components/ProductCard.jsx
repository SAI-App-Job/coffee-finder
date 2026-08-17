import { useState } from "react";
import { Sparkles, Coffee, MapPin, ExternalLink, Heart } from "lucide-react";
import { DISCOVERY_FACTS } from "../data/discoveryFacts";
import { PROCESSING_EXPLANATIONS, DESIGNATED_BRAND_EXPLANATIONS } from "../data/explanations";
import { getGradeExplanation } from "../utils/grade";
import { categorizeFlavorNotes } from "../utils/flavor";
import { roastColor, cityFromAddress, formatPrice } from "../utils/format";

export function DiscoveryFactCard() {
  const [index, setIndex] = useState(() => Math.floor(Math.random() * DISCOVERY_FACTS.length));
  const fact = DISCOVERY_FACTS[index];

  const showAnother = () => {
    setIndex((prev) => {
      if (DISCOVERY_FACTS.length <= 1) return prev;
      let next = Math.floor(Math.random() * DISCOVERY_FACTS.length);
      while (next === prev) next = Math.floor(Math.random() * DISCOVERY_FACTS.length);
      return next;
    });
  };

  return (
    <div className="rounded-2xl bg-[#2F241A] border border-[#4A3A2A] p-4 flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <Sparkles size={13} className="text-[var(--accent)]" strokeWidth={1.75} />
          <p className="text-[11px] tracking-[0.15em] text-[var(--accent-label)] uppercase">Discovery</p>
        </div>
        <button
          onClick={showAnother}
          className="text-[11px] text-[#8B7361] hover:text-[var(--accent)] transition-colors"
        >
          別の話を見る
        </button>
      </div>
      <h3 className="font-serif text-[16px] text-[#F2E9DD]">{fact.title}</h3>
      <p className="text-[13px] leading-relaxed text-[#B8A891]">{fact.text}</p>
    </div>
  );
}

export function HoverExplainTag({ label, category, detail }) {
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
        className="text-[11px] px-2 py-0.5 rounded-full bg-[#3B2211] text-[var(--accent-muted)] border border-[#4A3A2A] border-dashed hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors"
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
            border: "1px solid #4A3A2A",
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
              borderTop: "6px solid #4A3A2A",
            }}
          />
        </div>
      )}
    </span>
  );
}

export function ProductCard({ product, onOpenMap, onLearnOrigin, isFavorite, onToggleFavorite, onOpenDetail }) {
  const processingDetail = product.processingMethod
    ? PROCESSING_EXPLANATIONS[product.processingMethod]
    : null;
  const gradeDetail = getGradeExplanation(product.grade, product.originCountry, product.designatedBrand);
  const flavorCategories = categorizeFlavorNotes(product.flavorNotes);

  const staticTags = [product.farmNote].filter(Boolean);
  const favorited = isFavorite?.(product.id) ?? false;
  // ブレンドは単一のoriginCountryを持たないため、構成国をタグとして
  // 表示する(ストレート商品の産地表示と同じ見た目=既存のタグpillスタイルを流用)
  const blendCountries = product.blendComponents?.length
    ? [...new Set(product.blendComponents.map((c) => c.originCountry).filter(Boolean))]
    : [];

  return (
    <div
      className={`relative rounded-2xl bg-[#2F241A] border border-[#4A3A2A] flex ${onOpenDetail ? "cursor-pointer" : ""}`}
      onClick={() => onOpenDetail?.(product)}
      role={onOpenDetail ? "button" : undefined}
      tabIndex={onOpenDetail ? 0 : undefined}
    >
      {/* 焙煎度カラーバー(未選択=注文時選択の場合はストライプで示す)
          カード側のoverflow-hiddenは、ホバーで飛び出すツールチップまで
          切り取ってしまうため使わず、カラーバー自体の左端だけを丸めている */}
      <div
        className="w-1.5 shrink-0 rounded-l-2xl"
        style={
          product.roast
            ? { backgroundColor: roastColor(product.roast) }
            : {
                backgroundImage:
                  "repeating-linear-gradient(135deg, var(--accent-soft) 0 4px, #24140A 4px 8px)",
              }
        }
        aria-hidden="true"
      />

      <div className="flex-1 p-4 flex flex-col gap-2.5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-1.5 flex-wrap">
              {blendCountries.length > 0 ? (
                blendCountries.map((country) => (
                  <span
                    key={country}
                    className="text-[11px] px-2 py-0.5 rounded-full bg-[#3B2211] text-[var(--accent-muted)] border border-[#4A3A2A]"
                  >
                    {country}
                  </span>
                ))
              ) : (
                <p className="text-[11px] tracking-wider text-[var(--accent-label)] font-medium uppercase">
                  {product.originCountry}
                </p>
              )}
              {product.stockStatus && product.stockStatus !== "販売中" && (
                <span
                  className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium leading-none ${
                    product.stockStatus === "終売"
                      ? "bg-[#3B2211] text-[#8B7361] border border-[#4A3A2A]"
                      : "bg-[#4A2E12] text-[#E8B86D] border border-[#6B4A22]"
                  }`}
                >
                  {product.stockStatus === "終売" ? "終売" : "売り切れ"}
                </span>
              )}
            </div>
            <h3 className="font-serif text-[17px] leading-snug text-[#F2E9DD] mt-0.5">
              {product.rawName}
            </h3>
          </div>
          <div className="text-right shrink-0 flex flex-col items-end gap-1">
            <button
              onClick={(e) => {
                e.stopPropagation();
                onToggleFavorite?.(product.id);
              }}
              aria-label={favorited ? "お気に入りから削除" : "お気に入りに追加"}
              aria-pressed={favorited}
              className="p-1 -m-1 text-[#8B7361] hover:text-[var(--accent)] transition-colors"
            >
              <Heart
                size={17}
                strokeWidth={2}
                className={favorited ? "fill-[var(--accent)] text-[var(--accent)]" : ""}
              />
            </button>
            <p className="font-mono text-[#F2E9DD] text-[15px]">
              {formatPrice(product) ?? product.priceNote ?? "価格未確認"}
            </p>
            {typeof product.weightG === "number" && (
              <p className="font-mono text-[11px] text-[#8B7361]">{product.weightG}g</p>
            )}
          </div>
        </div>

        {(product.designatedBrand || staticTags.length > 0 || product.processingMethod || product.grade || flavorCategories.length > 0) && (
          <div className="flex flex-wrap gap-1.5">
            {product.designatedBrand && (
              <HoverExplainTag
                label={product.designatedBrand}
                category="特定銘柄"
                detail={
                  DESIGNATED_BRAND_EXPLANATIONS[product.designatedBrand] ||
                  "この銘柄についての解説はまだ用意されていません。"
                }
              />
            )}
            {product.processingMethod && (
              <HoverExplainTag
                label={product.processingMethod}
                category="精選方法"
                detail={processingDetail || "この精選方法についての解説はまだ用意されていません。"}
              />
            )}
            {product.grade && (
              <HoverExplainTag label={product.grade} category="グレード" detail={gradeDetail} />
            )}
            {flavorCategories.map((cat) => (
              <HoverExplainTag
                key={cat.en}
                label={
                  <span className="flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: cat.color }} />
                    {cat.ja}
                  </span>
                }
                category="フレーバーホイール"
                detail={`テイスティングノート「${product.flavorNotes}」から、SCA/WCRフレーバーホイールの「${cat.en}」カテゴリに該当すると自動分類。`}
              />
            ))}
            {staticTags.map((tag) => (
              <span
                key={tag}
                className="text-[11px] px-2 py-0.5 rounded-full bg-[#3B2211] text-[var(--accent-muted)] border border-[#4A3A2A]"
              >
                {tag}
              </span>
            ))}
            {product.roastSelectable && (
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-transparent text-[#8B7361] border border-dashed border-[#4A3A2A]">
                焙煎度は注文時に選択
              </span>
            )}
          </div>
        )}

        <div className="flex items-center justify-between pt-1.5 mt-auto border-t border-[#4A3A2A]">
          <div className="flex items-center gap-1 text-[12px] text-[#8B7361]">
            <Coffee size={13} strokeWidth={1.75} />
            <span>{product.shopName}</span>
            {product.shopAddress && (
              <span className="text-[#8B7361]/70">・{cityFromAddress(product.shopAddress)}</span>
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
            <span>地図で開く</span>
            <ExternalLink size={11} strokeWidth={1.75} />
          </button>
        </div>

        {onLearnOrigin && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onLearnOrigin(product.originCountry);
            }}
            className="flex items-center justify-center gap-1.5 text-[12px] text-[var(--accent-label)] hover:text-[var(--accent)] transition-colors py-1"
          >
            <Sparkles size={12} strokeWidth={1.75} />
            <span>{product.originCountry}という産地をもっと知る</span>
          </button>
        )}
      </div>
    </div>
  );
}
