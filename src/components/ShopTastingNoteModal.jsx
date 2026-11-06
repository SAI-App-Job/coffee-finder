import { useEffect, useState } from "react";
import { X, NotebookPen } from "lucide-react";
import { FlavorPicker } from "./FlavorPicker";
import { StarRating } from "./common";

const EMPTY_FORM = { productName: "", rating: 0, note: "", flavors: [] };

// 店舗画面の「テイスティングノートを作成」から開く、店舗だけで出会った豆の記録フォーム。
// 項目は 商品名・5段階評価・テイスティングノート・風味。
export function ShopTastingNoteModal({ shop, onAddNote, onClose }) {
  const [form, setForm] = useState(EMPTY_FORM);

  useEffect(() => {
    setForm(EMPTY_FORM);
  }, [shop?.name]);

  if (!shop) return null;

  const productName = form.productName.trim();

  const handleSubmit = () => {
    if (!productName) return;
    onAddNote({
      productName,
      rating: form.rating || null,
      note: form.note.trim() || null,
      flavors: form.flavors,
    });
    setForm(EMPTY_FORM);
    onClose();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full sm:w-[440px] max-h-[85vh] overflow-y-auto bg-[var(--c-surface)] border border-[var(--c-border)] rounded-t-2xl sm:rounded-2xl p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 mb-4">
          <div className="min-w-0">
            <p className="text-[11px] tracking-wider text-[var(--accent-label)] uppercase">Tasting Note</p>
            <h3 className="font-serif text-[17px] text-[var(--c-text)] mt-0.5 leading-snug truncate">{shop.name}</h3>
          </div>
          <button
            onClick={onClose}
            className="shrink-0 text-[var(--c-text-3)] hover:text-[var(--c-text)] transition-colors min-w-[36px] min-h-[36px] flex items-center justify-center -m-2"
            aria-label="閉じる"
          >
            <X size={18} />
          </button>
        </div>

        <div className="flex flex-col gap-4">
          <div>
            <label className="text-[11px] tracking-wide text-[var(--accent-label)] uppercase mb-1 block">
              商品名
            </label>
            <input
              type="text"
              value={form.productName}
              onChange={(e) => setForm((f) => ({ ...f, productName: e.target.value }))}
              placeholder="例: エチオピア イルガチェフェ"
              className="w-full px-3 py-2 rounded-lg bg-[var(--c-surface-2)] border border-[var(--c-border)] text-[13px] text-[var(--c-text)] placeholder:text-[var(--c-text-3)] focus:outline-none focus:border-[var(--accent)]"
            />
          </div>

          <div>
            <label className="text-[11px] tracking-wide text-[var(--accent-label)] uppercase mb-1.5 block">
              評価
            </label>
            <StarRating
              value={form.rating}
              size={26}
              onChange={(rating) => setForm((f) => ({ ...f, rating }))}
            />
          </div>

          <div>
            <label className="text-[11px] tracking-wide text-[var(--accent-label)] uppercase mb-1 block">
              テイスティングノート
            </label>
            <textarea
              value={form.note}
              onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))}
              rows={4}
              placeholder="香り・酸味・甘み・後味など、感じたことを自由に"
              className="w-full px-3 py-2 rounded-lg bg-[var(--c-surface-2)] border border-[var(--c-border)] text-[13px] text-[var(--c-text)] placeholder:text-[var(--c-text-3)] focus:outline-none focus:border-[var(--accent)] resize-none"
            />
          </div>

          <div>
            <label className="text-[11px] tracking-wide text-[var(--accent-label)] uppercase mb-1 block">
              風味
            </label>
            <p className="text-[11px] text-[var(--c-text-3)] mb-2">感じた風味を複数選べます(分類をタップすると詳細が開きます)</p>
            <FlavorPicker value={form.flavors} onChange={(flavors) => setForm((f) => ({ ...f, flavors }))} />
          </div>

          <button
            onClick={handleSubmit}
            disabled={!productName}
            className="flex items-center justify-center gap-1.5 py-2.5 rounded-xl bg-[var(--accent)] text-[var(--on-accent)] text-[13px] font-medium hover:bg-[var(--accent-soft)] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <NotebookPen size={14} strokeWidth={2} />
            この記録を保存
          </button>
        </div>
      </div>
    </div>
  );
}
