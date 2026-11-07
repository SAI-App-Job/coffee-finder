import { useState } from "react";
import { Plus, Pencil, MapPin, Store, Sparkles } from "lucide-react";
import { PRIMARY_BUTTON_CLASS } from "./formStyles";
import { DeleteControl, ICON_BUTTON_CLASS, UserProductList } from "./UserProductCard";
import { isSampleId } from "../data/sampleCollection";

// コレクション画面の「登録した商品」。ユーザーが手動で登録した商品を、店舗ごとにまとめて表示する。
// 店舗は2種類ある: アプリに載っている店舗(appShopName あり。店頭だけで売っている豆の登録など)と、
// アプリに載っていない店舗(手動で作ったもの)。
export function UserCollectionView({
  userShops,
  userProducts,
  getPhotoUrl,
  getRating,
  onRate,
  getLogCount,
  onRegisterProduct,
  hasSamples,
  onAddSamples,
  onRemoveSamples,
  onEditShop,
  onDeleteShop,
  onAddProduct,
  onEditProduct,
  onDeleteProduct,
  onOpenTastingLog,
  onOpenShopMap,
}) {
  const [confirmingShopId, setConfirmingShopId] = useState(null);
  const [confirmingSamples, setConfirmingSamples] = useState(false);
  const [addingSamples, setAddingSamples] = useState(false);

  // アプリの店舗に紐づく登録先は、商品が1件も無いときは表示しない(登録の途中経過を見せないため)
  const shops = userShops
    .filter((s) => !s.appShopName || userProducts.some((p) => p.shopId === s.id))
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt));

  return (
    <div className="px-5 py-5 flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[13px] text-[var(--c-text-3)]">
          {shops.length}店舗・{userProducts.length}商品
        </p>
        <button onClick={onRegisterProduct} className={`${PRIMARY_BUTTON_CLASS} px-3.5`}>
          <Plus size={14} strokeWidth={2.2} />
          商品を登録
        </button>
      </div>

      {hasSamples && (
        <div className="rounded-xl bg-[var(--c-surface-2)] border border-[var(--c-border)] px-3.5 py-3 flex items-center justify-between gap-3">
          <p className="text-[12px] text-[var(--c-text-2)] leading-relaxed min-w-0">
            サンプルが入っています(架空の店舗・商品)。写真・★評価・テイスティングログも付いています。
          </p>
          <DeleteControl
            confirming={confirmingSamples}
            onAsk={() => setConfirmingSamples(true)}
            onCancel={() => setConfirmingSamples(false)}
            onConfirm={() => {
              setConfirmingSamples(false);
              onRemoveSamples();
            }}
            label="サンプルを削除"
            confirmText="サンプルを削除しますか?"
          />
        </div>
      )}

      {shops.length === 0 ? (
        <div className="text-center py-14 text-[var(--c-text-3)]">
          <Store size={28} className="mx-auto mb-3 opacity-40" />
          <p className="text-[14px]">まだ登録した商品がありません</p>
          <p className="text-[12px] mt-1 leading-relaxed">
            お店を選んで、買った豆を登録できます。
            <br />
            ネットでは売っていない店頭の豆や、アプリに載っていないお店も登録できます
          </p>
          <button
            onClick={async () => {
              setAddingSamples(true);
              try {
                await onAddSamples();
              } finally {
                setAddingSamples(false);
              }
            }}
            disabled={addingSamples}
            className="mt-5 inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl border border-[var(--accent-label)] text-[var(--accent-on-glow)] text-[13px] font-medium hover:bg-[var(--c-surface-2)] transition-colors disabled:opacity-50"
          >
            <Sparkles size={14} strokeWidth={2} />
            {addingSamples ? "サンプルを作成中…" : "サンプルを追加して使い方を見る"}
          </button>
        </div>
      ) : (
        shops.map((shop) => {
          const products = userProducts.filter((p) => p.shopId === shop.id);
          const shopConfirming = confirmingShopId === shop.id;
          const linked = Boolean(shop.appShopName);
          return (
            <section
              key={shop.id}
              className="rounded-2xl bg-[var(--c-surface)] border border-[var(--c-border)] p-4 flex flex-col gap-3"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  {linked && (
                    <span className="inline-block text-[10px] px-1.5 py-0.5 mb-1 rounded-full bg-[var(--c-surface-2)] text-[var(--accent-muted)] border border-[var(--c-border)]">
                      アプリ掲載店
                    </span>
                  )}
                  {isSampleId(shop.id) && (
                    <span className="inline-block text-[10px] px-1.5 py-0.5 mb-1 rounded-full bg-[var(--c-surface-2)] text-[var(--accent-muted)] border border-[var(--c-border)]">
                      サンプル
                    </span>
                  )}
                  <h3 className="font-serif text-[17px] leading-snug text-[var(--c-text)]">{shop.name}</h3>
                  {shop.address && <p className="text-[12px] text-[var(--c-text-3)] mt-0.5">{shop.address}</p>}
                </div>
                <div className="flex items-center gap-0.5 shrink-0">
                  {shop.address && !shopConfirming && (
                    <button onClick={() => onOpenShopMap(shop)} className={ICON_BUTTON_CLASS} aria-label="地図で開く">
                      <MapPin size={14} strokeWidth={1.75} />
                    </button>
                  )}
                  {/* アプリ掲載店の名前・住所はアプリ側のデータなので、ここでは編集しない */}
                  {!linked && !shopConfirming && (
                    <button onClick={() => onEditShop(shop)} className={ICON_BUTTON_CLASS} aria-label="店舗を編集">
                      <Pencil size={14} strokeWidth={1.75} />
                    </button>
                  )}
                  <DeleteControl
                    confirming={shopConfirming}
                    onAsk={() => setConfirmingShopId(shop.id)}
                    onCancel={() => setConfirmingShopId(null)}
                    onConfirm={() => {
                      setConfirmingShopId(null);
                      onDeleteShop(shop.id);
                    }}
                    label={linked ? "この店舗の登録商品をすべて削除" : "店舗を削除"}
                    confirmText={products.length > 0 ? `商品${products.length}件も消えます` : "削除しますか?"}
                  />
                </div>
              </div>

              <UserProductList
                products={products}
                getPhotoUrl={getPhotoUrl}
                getRating={getRating}
                onRate={onRate}
                getLogCount={getLogCount}
                onOpenTastingLog={onOpenTastingLog}
                onEdit={(product) => onEditProduct(shop, product)}
                onDelete={onDeleteProduct}
              />

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
