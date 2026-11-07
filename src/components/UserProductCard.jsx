import { useState } from "react";
import { Pencil, Trash2, NotebookPen } from "lucide-react";
import { StarRating } from "./common";
import { FlavorChips } from "./FlavorPicker";
import { PhotoThumb } from "./ProductPhoto";

import { formatDate } from "../utils/format";
import { useT } from "../i18n";

const formatYen = (n) => `¥${n.toLocaleString("ja-JP")}`;

export const ICON_BUTTON_CLASS =
  "p-1.5 rounded-lg text-[var(--c-text-3)] hover:text-[var(--c-text)] hover:bg-[var(--c-surface-2)] transition-colors";

// 削除は、1回目で確認表示に切り替え、2回目で実行する(誤タップで消さないため)
export function DeleteControl({ confirming, onAsk, onCancel, onConfirm, label, confirmText }) {
  const t = useT();
  if (!confirming) {
    return (
      <button onClick={onAsk} className={ICON_BUTTON_CLASS} aria-label={label}>
        <Trash2 size={14} strokeWidth={1.75} />
      </button>
    );
  }
  return (
    <span className="flex items-center gap-1.5 text-[11px]">
      <span className="text-[var(--c-danger)]">{confirmText}</span>
      <button onClick={onConfirm} className="px-2 py-1 rounded-md bg-[var(--c-danger)] text-white font-medium">
        {t("削除")}
      </button>
      <button onClick={onCancel} className="px-2 py-1 rounded-md border border-[var(--c-border)] text-[var(--c-text-2)]">
        {t("やめる")}
      </button>
    </span>
  );
}

function UserProductCard({
  product,
  photoUrl,
  rating,
  onRate,
  logCount,
  onOpenTastingLog,
  onEdit,
  confirming,
  onAskDelete,
  onCancelDelete,
  onConfirmDelete,
}) {
  const t = useT();
  const meta = [
    typeof product.price === "number" && formatYen(product.price),
    typeof product.weightG === "number" && `${product.weightG}g`,
  ].filter(Boolean);
  const tags = [product.originCountry, product.roast, product.processingMethod].filter(Boolean).map((v) => t(v));

  return (
    <div className="rounded-xl bg-[var(--c-surface-2)] border border-[var(--c-border)] p-3.5 flex flex-col gap-2">
      <div className="flex items-start gap-3">
        <PhotoThumb url={photoUrl} alt={t("{name}のパッケージ写真", { name: product.name })} />
        <div className="flex-1 min-w-0 flex items-start justify-between gap-3">
          <h4 className="text-[14px] font-medium text-[var(--c-text)] leading-snug min-w-0">{product.name}</h4>
          {meta.length > 0 && <p className="shrink-0 font-mono text-[12px] text-[var(--c-text-2)]">{meta.join(" / ")}</p>}
        </div>
      </div>

      {tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {tags.map((t) => (
            <span
              key={t}
              className="text-[11px] px-2 py-0.5 rounded-full bg-[var(--c-surface)] text-[var(--accent-muted)] border border-[var(--c-border)]"
            >
              {t}
            </span>
          ))}
        </div>
      )}

      <FlavorChips flavors={product.flavors} />
      {product.note && (
        <p className="text-[12px] text-[var(--c-text-2)] leading-relaxed whitespace-pre-line">{product.note}</p>
      )}

      {formatDate(product.createdAt) && (
        <p className="text-[11px] text-[var(--c-text-3)]">{t("登録日 {date}", { date: formatDate(product.createdAt) })}</p>
      )}

      <div className="flex items-center justify-between gap-3 pt-2 mt-0.5 border-t border-[var(--c-border)]">
        <StarRating value={rating} onChange={onRate} size={16} />
        <div className="flex items-center gap-0.5">
          <button
            onClick={onOpenTastingLog}
            className="flex items-center gap-1 px-2 py-1.5 rounded-lg text-[11px] text-[var(--accent-on-glow)] hover:bg-[var(--c-surface)] transition-colors"
          >
            <NotebookPen size={13} strokeWidth={1.75} />
            {t("ログ")}{logCount > 0 ? `(${logCount})` : ""}
          </button>
          {!confirming && (
            <button onClick={onEdit} className={ICON_BUTTON_CLASS} aria-label={t("商品を編集")}>
              <Pencil size={14} strokeWidth={1.75} />
            </button>
          )}
          <DeleteControl
            confirming={confirming}
            onAsk={onAskDelete}
            onCancel={onCancelDelete}
            onConfirm={onConfirmDelete}
            label={t("商品を削除")}
            confirmText={t("削除しますか?")}
          />
        </div>
      </div>
    </div>
  );
}

// 手動登録した商品のカード一覧(コレクションの店舗ごと / 店舗画面の「店頭の商品」で共通)。
// 削除の確認表示は、一覧の中で1件ずつ管理する。
export function UserProductList({ products, getPhotoUrl, getRating, onRate, getLogCount, onOpenTastingLog, onEdit, onDelete }) {
  const [confirmingId, setConfirmingId] = useState(null);

  return products.map((product) => (
    <UserProductCard
      key={product.id}
      product={product}
      photoUrl={getPhotoUrl?.(product.id)}
      rating={getRating(product.id)}
      onRate={(stars) => onRate(product.id, stars)}
      logCount={getLogCount(product.id)}
      onOpenTastingLog={() => onOpenTastingLog(product)}
      onEdit={() => onEdit(product)}
      confirming={confirmingId === product.id}
      onAskDelete={() => setConfirmingId(product.id)}
      onCancelDelete={() => setConfirmingId(null)}
      onConfirmDelete={() => {
        setConfirmingId(null);
        onDelete(product.id);
      }}
    />
  ));
}
