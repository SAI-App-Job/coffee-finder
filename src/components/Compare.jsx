import { ArrowRight, Trash2, X } from "lucide-react";
import { formatPrice } from "../utils/format";

export function CompareTray({ count, limit, isPremium, onOpen }) {
  return (
    <div className="border-b border-[#4A3A2A] max-w-xl mx-auto w-full px-5 py-2.5 flex items-center justify-between">
      <p className="text-[12px] text-[#B8A891]">
        比較リスト {count}
        {isPremium ? "" : `/${limit}`}件
      </p>
      <button
        onClick={onOpen}
        className="flex items-center gap-1.5 text-[12px] px-3.5 py-1.5 rounded-full bg-[var(--accent)] text-[#231810] font-medium"
      >
        比較する
        <ArrowRight size={13} strokeWidth={2} />
      </button>
    </div>
  );
}

function CompareField({ label, value }) {
  if (!value) return null;
  return (
    <div>
      <p className="text-[10px] text-[#8B7361] uppercase tracking-wide">{label}</p>
      <p className="text-[12px] text-[#B8A891] leading-snug mt-0.5">{value}</p>
    </div>
  );
}

export function ComparisonModal({ products, onClose, onRemove, onClearAll, isPremium, limit }) {
  if (products.length === 0) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full sm:w-[640px] max-h-[85vh] bg-[#2F241A] border border-[#4A3A2A] rounded-t-2xl sm:rounded-2xl p-5 flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-3">
          <div>
            <p className="text-[11px] tracking-wider text-[var(--accent-label)] uppercase">Compare</p>
            <h3 className="font-serif text-[18px] text-[#F2E9DD] mt-0.5">比較({products.length}件)</h3>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={onClearAll}
              className="text-[11px] text-[#8B7361] hover:text-[#F2E9DD] transition-colors underline underline-offset-2"
            >
              すべて解除
            </button>
            <button
              onClick={onClose}
              className="text-[#8B7361] hover:text-[#F2E9DD] transition-colors min-w-[36px] min-h-[36px] flex items-center justify-center -m-2"
              aria-label="閉じる"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {!isPremium && (
          <p className="text-[11px] text-[#8B7361] mb-3">
            無料プランは{limit}件まで比較できます。有料プランでは無制限です。
          </p>
        )}

        <div className="flex gap-3 overflow-x-auto pb-1 -mx-1 px-1">
          {products.map((p) => (
            <div
              key={p.id}
              className="shrink-0 w-[220px] rounded-xl bg-[#3B2211] border border-[#4A3A2A] p-3 flex flex-col gap-2.5"
            >
              <div className="flex items-start justify-between gap-2">
                <p className="text-[11px] text-[var(--accent-label)] uppercase">{p.originCountry}</p>
                <button
                  onClick={() => onRemove(p.id)}
                  className="text-[#8B7361] hover:text-[#F2E9DD] transition-colors"
                  aria-label="比較から削除"
                >
                  <Trash2 size={13} />
                </button>
              </div>
              <p className="font-serif text-[14px] text-[#F2E9DD] leading-snug">{p.rawName}</p>
              <p className="font-mono text-[#F2E9DD] text-[14px]">{formatPrice(p) ?? "価格未確認"}</p>
              <CompareField label="精選方法" value={p.processingMethod} />
              <CompareField label="グレード" value={p.grade} />
              <CompareField label="焙煎度" value={p.roast ?? (p.roastSelectable ? "注文時選択" : null)} />
              <CompareField label="フレーバー" value={p.flavorNotes} />
              <CompareField label="店舗" value={p.shopName} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
