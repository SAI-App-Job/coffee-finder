import { ArrowRight, Trash2, X } from "lucide-react";
import { formatPrice } from "../utils/format";
import { analyzeProductFlavor } from "../utils/flavor";
import { useT } from "../i18n";

export function CompareTray({ count, limit, isPremium, onOpen }) {
  const t = useT();
  return (
    <div className="border-b border-[var(--c-border)] max-w-xl mx-auto w-full px-5 py-2.5 flex items-center justify-between">
      <p className="text-[12px] text-[var(--c-text-2)]">
        {t("比較リスト {count}件", { count: isPremium ? count : `${count}/${limit}` })}
      </p>
      <button
        onClick={onOpen}
        className="flex items-center gap-1.5 text-[12px] px-3.5 py-1.5 rounded-full bg-[var(--accent)] text-[var(--on-accent)] font-medium"
      >
        {t("比較する")}
        <ArrowRight size={13} strokeWidth={2} />
      </button>
    </div>
  );
}

function CompareField({ label, value }) {
  if (!value) return null;
  return (
    <div>
      <p className="text-[10px] text-[var(--c-text-3)] uppercase tracking-wide">{label}</p>
      <p className="text-[12px] text-[var(--c-text-2)] leading-snug mt-0.5">{value}</p>
    </div>
  );
}

export function ComparisonModal({ products, onClose, onRemove, onClearAll, isPremium, limit }) {
  const t = useT();
  if (products.length === 0) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full sm:w-[640px] max-h-[85vh] bg-[var(--c-surface)] border border-[var(--c-border)] rounded-t-2xl sm:rounded-2xl p-5 flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-3">
          <div>
            <p className="text-[11px] tracking-wider text-[var(--accent-label)] uppercase">Compare</p>
            <h3 className="font-serif text-[18px] text-[var(--c-text)] mt-0.5">{t("比較({n}件)", { n: products.length })}</h3>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={onClearAll}
              className="text-[11px] text-[var(--c-text-3)] hover:text-[var(--c-text)] transition-colors underline underline-offset-2"
            >
              {t("すべて解除")}
            </button>
            <button
              onClick={onClose}
              className="text-[var(--c-text-3)] hover:text-[var(--c-text)] transition-colors min-w-[36px] min-h-[36px] flex items-center justify-center -m-2"
              aria-label={t("閉じる")}
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {!isPremium && (
          <p className="text-[11px] text-[var(--c-text-3)] mb-3">
            {t("無料プランは{n}件まで比較できます。有料プランでは無制限です。", { n: limit })}
          </p>
        )}

        <div className="flex gap-3 overflow-x-auto pb-1 -mx-1 px-1">
          {products.map((p) => (
            <div
              key={p.id}
              className="shrink-0 w-[220px] rounded-xl bg-[var(--c-surface-2)] border border-[var(--c-border)] p-3 flex flex-col gap-2.5"
            >
              <div className="flex items-start justify-between gap-2">
                <p className="text-[11px] text-[var(--accent-label)] uppercase">{p.originCountry}</p>
                <button
                  onClick={() => onRemove(p.id)}
                  className="text-[var(--c-text-3)] hover:text-[var(--c-text)] transition-colors"
                  aria-label={t("比較から削除")}
                >
                  <Trash2 size={13} />
                </button>
              </div>
              <p className="font-serif text-[14px] text-[var(--c-text)] leading-snug">{p.rawName}</p>
              <p className="font-mono text-[var(--c-text)] text-[14px]">{formatPrice(p) ?? t("価格未確認")}</p>
              <CompareField label={t("精選方法")} value={p.processingMethod} />
              <CompareField label={t("グレード")} value={p.grade} />
              <CompareField label={t("焙煎度")} value={p.roast ? t(p.roast) : p.roastSelectable ? t("注文時選択") : null} />
              <CompareField label={t("フレーバー")} value={p.flavorNotes || analyzeProductFlavor(p).terms.map((x) => t(x.ja)).join("、") || null} />
              <CompareField label={t("店舗{ctx}", { ctx: "" })} value={p.shopName} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
