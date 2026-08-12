import { Heart } from "lucide-react";
import { ProductCard } from "./ProductCard";

export function FavoritesView({ products, isFavorite, onToggleFavorite, onOpenMap, onLearnOrigin }) {
  const favorites = products.filter((p) => isFavorite(p.id));

  return (
    <main className="px-5 py-5 flex flex-col gap-3 max-w-xl mx-auto">
      <p className="text-[13px] text-[#8B7361]">{favorites.length}件のお気に入り</p>
      {favorites.length === 0 ? (
        <div className="text-center py-16 text-[#8B7361]">
          <Heart size={28} className="mx-auto mb-3 opacity-40" />
          <p className="text-[14px]">まだお気に入りがありません</p>
          <p className="text-[12px] mt-1">商品カードのハートアイコンをタップして追加できます</p>
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
          />
        ))
      )}
    </main>
  );
}
