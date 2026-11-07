import { Heart } from "lucide-react";
import { ProductCard } from "./ProductCard";
import { useT } from "../i18n";

export function FavoritesView({ products, favoriteDates, isFavorite, onToggleFavorite, onOpenMap, onLearnOrigin, onOpenDetail }) {
  const t = useT();
  const favorites = products.filter((p) => isFavorite(p.id));

  return (
    <main className="px-5 py-5 flex flex-col gap-3 max-w-xl mx-auto">
      <p className="text-[13px] text-[var(--c-text-3)]">{t("保存した商品 {n}件", { n: favorites.length })}</p>
      {favorites.length === 0 ? (
        <div className="text-center py-16 text-[var(--c-text-3)]">
          <Heart size={28} className="mx-auto mb-3 opacity-40" />
          <p className="text-[14px]">{t("まだ保存した商品がありません")}</p>
          <p className="text-[12px] mt-1">{t("商品カードのハートアイコンをタップして、コレクションに追加できます")}</p>
        </div>
      ) : (
        favorites.map((product) => (
          <ProductCard
            key={product.id}
            product={product}
            onOpenMap={onOpenMap}
            onLearnOrigin={onLearnOrigin}
            isFavorite={isFavorite}
            onToggleFavorite={onToggleFavorite}
            onOpenDetail={onOpenDetail}
            savedAt={favoriteDates?.[String(product.id)]}
          />
        ))
      )}
    </main>
  );
}
