import { X, MapPin, ExternalLink, Heart, ArrowLeftRight, Check, Coffee, Sparkles } from "lucide-react";
import { PROCESSING_EXPLANATIONS, DESIGNATED_BRAND_EXPLANATIONS } from "../data/explanations";
import { getGradeExplanation } from "../utils/grade";
import { categorizeFlavorNotes } from "../utils/flavor";
import { cityFromAddress, formatPrice } from "../utils/format";
import { StarRating } from "./common";

function DetailRow({ label, value, detail }) {
  if (!value) return null;
  return (
    <div>
      <p className="text-[11px] tracking-wide text-[var(--accent-label)] uppercase mb-1">{label}</p>
      <p className="text-[13px] text-[#F2E9DD]">{value}</p>
      {detail && <p className="text-[12px] text-[#B8A891] leading-relaxed mt-1">{detail}</p>}
    </div>
  );
}

// 商品カードをタップすると開く軽量な詳細モーダル。新しいデータは持たず、
// 既存のProductCardが扱っているフィールドをそのまま並べて表示するだけの画面。
// この画面を開いた時点を「閲覧」として履歴に記録し、比較への追加もここから行う。
export function ProductDetailModal({
  product,
  onClose,
  onOpenMap,
  isFavorite,
  onToggleFavorite,
  isComparing,
  onToggleCompare,
  rating,
  onRate,
}) {
  if (!product) return null;

  const processingDetail = product.processingMethod ? PROCESSING_EXPLANATIONS[product.processingMethod] : null;
  const gradeDetail = product.grade
    ? getGradeExplanation(product.grade, product.originCountry, product.designatedBrand)
    : null;
  const flavorCategories = categorizeFlavorNotes(product.flavorNotes);
  const favorited = isFavorite?.(product.id) ?? false;
  const comparing = isComparing?.(product.id) ?? false;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full sm:w-[440px] max-h-[85vh] overflow-y-auto bg-[#2F241A] border border-[#4A3A2A] rounded-t-2xl sm:rounded-2xl p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 mb-3">
          <div>
            <p className="text-[11px] tracking-wider text-[var(--accent-label)] font-medium uppercase">
              {product.originCountry}
            </p>
            <h3 className="font-serif text-[19px] leading-snug text-[#F2E9DD] mt-0.5">{product.rawName}</h3>
          </div>
          <button
            onClick={onClose}
            className="shrink-0 text-[#8B7361] hover:text-[#F2E9DD] transition-colors min-w-[36px] min-h-[36px] flex items-center justify-center -m-2"
            aria-label="閉じる"
          >
            <X size={18} />
          </button>
        </div>

        <div className="flex items-center justify-between mb-3">
          <p className="font-mono text-[#F2E9DD] text-[18px]">{formatPrice(product) ?? "価格未確認"}</p>
          {typeof product.weightG === "number" && (
            <p className="font-mono text-[12px] text-[#8B7361]">{product.weightG}g</p>
          )}
        </div>

        <div className="flex items-center justify-between gap-3 mb-4 pb-4 border-b border-[#4A3A2A]">
          <p className="text-[12px] text-[#8B7361]">この商品を評価</p>
          <StarRating value={rating} onChange={(stars) => onRate?.(product.id, stars)} />
        </div>

        <div className="flex flex-col gap-3.5 mb-4">
          <DetailRow
            label="特定銘柄"
            value={product.designatedBrand}
            detail={
              product.designatedBrand &&
              (DESIGNATED_BRAND_EXPLANATIONS[product.designatedBrand] || "この銘柄についての解説はまだ用意されていません。")
            }
          />
          <DetailRow
            label="精選方法"
            value={product.processingMethod}
            detail={product.processingMethod && (processingDetail || "この精選方法についての解説はまだ用意されていません。")}
          />
          <DetailRow label="グレード" value={product.grade} detail={gradeDetail} />
          <DetailRow
            label="焙煎度"
            value={product.roast ?? (product.roastSelectable ? "注文時に選択" : null)}
          />
          {flavorCategories.length > 0 && (
            <div>
              <p className="text-[11px] tracking-wide text-[var(--accent-label)] uppercase mb-1">フレーバーノート</p>
              <p className="text-[13px] text-[#F2E9DD] mb-1.5">{product.flavorNotes}</p>
              <div className="flex flex-wrap gap-1.5">
                {flavorCategories.map((cat) => (
                  <span
                    key={cat.en}
                    className="flex items-center gap-1.5 text-[11px] px-2 py-0.5 rounded-full bg-[#3B2211] text-[var(--accent-muted)] border border-[#4A3A2A]"
                  >
                    <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: cat.color }} />
                    {cat.ja}
                  </span>
                ))}
              </div>
            </div>
          )}
          <DetailRow label="農園情報" value={product.farmNote} />
        </div>

        <div className="flex items-center gap-1.5 text-[12px] text-[#8B7361] pt-3 border-t border-[#4A3A2A] mb-4">
          <Coffee size={13} strokeWidth={1.75} />
          <span>{product.shopName}</span>
          {product.shopAddress && <span className="text-[#8B7361]/70">・{cityFromAddress(product.shopAddress)}</span>}
        </div>

        <div className="flex flex-col gap-2">
          <button
            onClick={() => onOpenMap(product)}
            className="flex items-center justify-center gap-1.5 py-2.5 rounded-xl bg-[var(--accent)] text-[#231810] text-[13px] font-medium hover:bg-[var(--accent-soft)] transition-colors"
          >
            <MapPin size={14} strokeWidth={2} />
            地図で開く
            <ExternalLink size={11} strokeWidth={1.75} />
          </button>
          <div className="flex gap-2">
            <button
              onClick={() => onToggleFavorite?.(product.id)}
              className={`flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-xl border text-[13px] transition-colors ${
                favorited ? "border-[var(--accent)] text-[var(--accent)]" : "border-[#4A3A2A] text-[#B8A891]"
              }`}
            >
              <Heart size={14} strokeWidth={2} className={favorited ? "fill-[var(--accent)]" : ""} />
              {favorited ? "お気に入り済み" : "お気に入りに追加"}
            </button>
            <button
              onClick={() => onToggleCompare?.(product.id)}
              className={`flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-xl border text-[13px] transition-colors ${
                comparing ? "border-[var(--accent)] text-[var(--accent)]" : "border-[#4A3A2A] text-[#B8A891]"
              }`}
            >
              {comparing ? <Check size={14} strokeWidth={2} /> : <ArrowLeftRight size={14} strokeWidth={2} />}
              {comparing ? "比較に追加済み" : "比較に追加"}
            </button>
          </div>
        </div>

        {product.originCountry && (
          <p className="flex items-center justify-center gap-1.5 text-[11px] text-[#8B7361] mt-3">
            <Sparkles size={11} strokeWidth={1.75} />
            産地タブから{product.originCountry}についてさらに詳しく見られます
          </p>
        )}
      </div>
    </div>
  );
}
