import { useState } from "react";
import { List, Map as MapIcon } from "lucide-react";
import { FavoritesView } from "./FavoritesView";
import { MyMapView } from "./MyMapView";
import { TasteProfile } from "./TasteProfile";
import { FavoritesBackup } from "./FavoritesBackup";

const VIEW_MODES = [
  { id: "list", icon: List, label: "リスト" },
  { id: "map", icon: MapIcon, label: "マップ" },
];

// 「お気に入り」画面の入れ物。リスト表示(FavoritesView)とマップ表示(MyMapView)を
// 内部トグルで切り替え、その下に「好みの傾向」と「お気に入りのバックアップ」を置く。
export function FavoritesTabView({
  products,
  isFavorite,
  onToggleFavorite,
  onOpenMap,
  onLearnOrigin,
  onOpenDetail,
  favoriteShops,
  favoriteIds,
  importFavorites,
  isPremium,
  getRating,
}) {
  const [viewMode, setViewMode] = useState("list");

  return (
    <div className="max-w-xl mx-auto">
      <div className="px-5 pt-5 flex justify-end">
        <div className="flex gap-1 p-1 rounded-full bg-[var(--c-surface-2)]">
          {VIEW_MODES.map(({ id, icon: Icon, label }) => (
            <button
              key={id}
              onClick={() => setViewMode(id)}
              aria-pressed={viewMode === id}
              className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-[12px] font-medium transition-colors ${
                viewMode === id ? "bg-[var(--accent)] text-[var(--on-accent)]" : "text-[var(--c-text-2)]"
              }`}
            >
              <Icon size={13} strokeWidth={2} />
              {label}
            </button>
          ))}
        </div>
      </div>

      {viewMode === "list" ? (
        <FavoritesView
          products={products}
          isFavorite={isFavorite}
          onToggleFavorite={onToggleFavorite}
          onOpenMap={onOpenMap}
          onLearnOrigin={onLearnOrigin}
          onOpenDetail={onOpenDetail}
        />
      ) : (
        <MyMapView favoriteShops={favoriteShops} />
      )}

      <div className="px-5 pb-5 flex flex-col gap-6">
        <TasteProfile products={products} getRating={getRating} onOpenDetail={onOpenDetail} />
        <FavoritesBackup favoriteIds={favoriteIds} importFavorites={importFavorites} isPremium={isPremium} />
      </div>
    </div>
  );
}
