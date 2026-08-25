import { useState } from "react";
import { List, Map as MapIcon } from "lucide-react";
import { FavoritesView } from "./FavoritesView";
import { MyMapView } from "./MyMapView";

const VIEW_MODES = [
  { id: "list", icon: List, label: "リスト" },
  { id: "map", icon: MapIcon, label: "マップ" },
];

// 「お気に入り」タブの入れ物。リスト表示(FavoritesView)とマップ表示(MyMapView)を
// 内部トグルで切り替える。両ビューの中身には手を加えず、切り替えの器だけを新設した。
export function FavoritesTabView({
  products,
  isFavorite,
  onToggleFavorite,
  onOpenMap,
  onLearnOrigin,
  onOpenDetail,
  favoriteShops,
}) {
  const [viewMode, setViewMode] = useState("list");

  return (
    <div className="max-w-xl mx-auto">
      <div className="px-5 pt-5 flex justify-end">
        <div className="flex gap-1 p-1 rounded-full bg-[#3B2211]">
          {VIEW_MODES.map(({ id, icon: Icon, label }) => (
            <button
              key={id}
              onClick={() => setViewMode(id)}
              aria-pressed={viewMode === id}
              className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-[12px] font-medium transition-colors ${
                viewMode === id ? "bg-[var(--accent)] text-[#231810]" : "text-[#B8A891]"
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
    </div>
  );
}
