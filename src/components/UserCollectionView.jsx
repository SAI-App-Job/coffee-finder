import { useState } from "react";
import { Plus, Pencil, Trash2, MapPin, NotebookPen, Store } from "lucide-react";
import { StarRating } from "./common";
import { FlavorChips } from "./FlavorPicker";
import { PRIMARY_BUTTON_CLASS } from "./formStyles";

const formatYen = (n) => `¥${n.toLocaleString("ja-JP")}`;

const ICON_BUTTON_CLASS =
  "p-1.5 rounded-lg text-[var(--c-text-3)] hover:text-[var(--c-text)] hover:bg-[var(--c-surface-2)] transition-colors";

// 削除は、1回目で確認表示に切り替え、2回目で実行する(誤タップで消さないため)
function DeleteControl({ confirming, onAsk, onCancel, onConfirm, label, confirmText }) {
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
      <button
        onClick={onConfirm}
        className="px-2 py-1 rounded-md bg-[var(--c-danger)] text-white font-medium"
      >
        削除
      </button>
      <button onClick={onCancel} className="px-2 py-1 rounded-md border border-[var(--c-border)] text-[var(--c-text-2)]">
        やめる
      </button>
    </span>
  );
}

function UserProductCard({
  product,
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
  const meta = [
    typeof product.price === "number" && formatYen(product.price),
    typeof product.weightG === "number" && `${product.weightG}g`,
  ].filter(Boolean);
  const tags = [product.originCountry, product.roast, product.processingMethod].filter(Boolean);

  return (
    <div className="rounded-xl bg-[var(--c-surface-2)] border border-[var(--c-border)] p-3.5 flex flex-col gap-2">
      <div className="flex items-start justify-between gap-3">
        <h4 className="text-[14px] font-medium text-[var(--c-text)] leading-snug min-w-0">{product.name}</h4>
        {meta.length > 0 && (
          <p className="shrink-0 font-mono text-[12px] text-[var(--c-text-2)]">{meta.join(" / ")}</p>
        )}
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
      {product.note && <p className="text-[12px] text-[var(--c-text-2)] leading-relaxed whitespace-pre-line">{product.note}</p>}

      <div className="flex items-center justify-between gap-3 pt-2 mt-0.5 border-t border-[var(--c-border)]">
        <StarRating value={rating} onChange={onRate} size={16} />
        <div className="flex items-center gap-0.5">
          <button
            onClick={onOpenTastingLog}
            className="flex items-center gap-1 px-2 py-1.5 rounded-lg text-[11px] text-[var(--accent-on-glow)] hover:bg-[var(--c-surface)] transition-colors"
          >
            <NotebookPen size={13} strokeWidth={1.75} />
            ログ{logCount > 0 ? `(${logCount})` : ""}
          </button>
          {!confirming && (
            <button onClick={onEdit} className={ICON_BUTTON_CLASS} aria-label="商品を編集">
              <Pencil size={14} strokeWidth={1.75} />
            </button>
          )}
          <DeleteControl
            confirming={confirming}
            onAsk={onAskDelete}
            onCancel={onCancelDelete}
            onConfirm={onConfirmDelete}
            label="商品を削除"
            confirmText="削除しますか?"
          />
        </div>
      </div>
    </div>
  );
}

// コレクション画面の「登録した商品」。ユーザーが手動で登録した 店舗 → 商品 を、店舗ごとにまとめて表示する。
export function UserCollectionView({
  userShops,
  userProducts,
  getRating,
  onRate,
  getLogCount,
  onAddShop,
  onEditShop,
  onDeleteShop,
  onAddProduct,
  onEditProduct,
  onDeleteProduct,
  onOpenTastingLog,
  onOpenShopMap,
}) {
  const [confirming, setConfirming] = useState(null); // "shop:<id>" | "product:<id>"

  const shops = [...userShops].sort((a, b) => b.createdAt.localeCompare(a.createdAt));

  return (
    <div className="px-5 py-5 flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[13px] text-[var(--c-text-3)]">
          {userShops.length}店舗・{userProducts.length}商品
        </p>
        <button onClick={onAddShop} className={`${PRIMARY_BUTTON_CLASS} px-3.5`}>
          <Plus size={14} strokeWidth={2.2} />
          店舗を登録
        </button>
      </div>

      {shops.length === 0 ? (
        <div className="text-center py-14 text-[var(--c-text-3)]">
          <Store size={28} className="mx-auto mb-3 opacity-40" />
          <p className="text-[14px]">まだ登録した商品がありません</p>
          <p className="text-[12px] mt-1 leading-relaxed">
            お店で買った豆を、「店舗 → 商品」の順に登録して、
            <br />
            評価やテイスティングの記録と一緒に残せます
          </p>
        </div>
      ) : (
        shops.map((shop) => {
          const products = userProducts.filter((p) => p.shopId === shop.id);
          const shopConfirming = confirming === `shop:${shop.id}`;
          return (
            <section
              key={shop.id}
              className="rounded-2xl bg-[var(--c-surface)] border border-[var(--c-border)] p-4 flex flex-col gap-3"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="font-serif text-[17px] leading-snug text-[var(--c-text)]">{shop.name}</h3>
                  {shop.address && <p className="text-[12px] text-[var(--c-text-3)] mt-0.5">{shop.address}</p>}
                </div>
                <div className="flex items-center gap-0.5 shrink-0">
                  {shop.address && !shopConfirming && (
                    <button onClick={() => onOpenShopMap(shop)} className={ICON_BUTTON_CLASS} aria-label="地図で開く">
                      <MapPin size={14} strokeWidth={1.75} />
                    </button>
                  )}
                  {!shopConfirming && (
                    <button onClick={() => onEditShop(shop)} className={ICON_BUTTON_CLASS} aria-label="店舗を編集">
                      <Pencil size={14} strokeWidth={1.75} />
                    </button>
                  )}
                  <DeleteControl
                    confirming={shopConfirming}
                    onAsk={() => setConfirming(`shop:${shop.id}`)}
                    onCancel={() => setConfirming(null)}
                    onConfirm={() => {
                      setConfirming(null);
                      onDeleteShop(shop.id);
                    }}
                    label="店舗を削除"
                    confirmText={products.length > 0 ? `商品${products.length}件も消えます` : "削除しますか?"}
                  />
                </div>
              </div>

              {products.map((product) => (
                <UserProductCard
                  key={product.id}
                  product={product}
                  rating={getRating(product.id)}
                  onRate={(stars) => onRate(product.id, stars)}
                  logCount={getLogCount(product.id)}
                  onOpenTastingLog={() => onOpenTastingLog(product)}
                  onEdit={() => onEditProduct(shop, product)}
                  confirming={confirming === `product:${product.id}`}
                  onAskDelete={() => setConfirming(`product:${product.id}`)}
                  onCancelDelete={() => setConfirming(null)}
                  onConfirmDelete={() => {
                    setConfirming(null);
                    onDeleteProduct(product.id);
                  }}
                />
              ))}

              <button
                onClick={() => onAddProduct(shop)}
                className="flex items-center justify-center gap-1.5 py-2.5 rounded-xl border border-dashed border-[var(--accent-label)] text-[var(--accent-on-glow)] text-[13px] font-medium hover:bg-[var(--c-surface-2)] transition-colors"
              >
                <Plus size={14} strokeWidth={2.2} />
                この店舗の商品を登録
              </button>
            </section>
          );
        })
      )}
    </div>
  );
}
