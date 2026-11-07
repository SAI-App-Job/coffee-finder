import { useMemo, useState } from "react";
import { List, Map as MapIcon, Heart, Coffee } from "lucide-react";
import { SectionHeading } from "./common";
import { FavoritesView } from "./FavoritesView";
import { MyMapView } from "./MyMapView";
import { UserCollectionView } from "./UserCollectionView";
import { TasteProfile } from "./TasteProfile";
import { CollectionBackup } from "./CollectionBackup";

const SECTIONS = [
  { id: "favorites", icon: Heart, label: "保存した商品" },
  { id: "registered", icon: Coffee, label: "登録した商品" },
];

const VIEW_MODES = [
  { id: "list", icon: List, label: "リスト" },
  { id: "map", icon: MapIcon, label: "マップ" },
];

// 「コレクション」画面。2つの部分から成る。
// - お気に入り: ハートで保存した商品(リスト/マップの切り替えつき)
// - 登録した商品: ユーザーが手動で登録した 店舗 → 商品
// その下に「好みの傾向」と「コレクションのバックアップ」を置く。
export function CollectionView({
  products,
  isFavorite,
  onToggleFavorite,
  onOpenMap,
  onLearnOrigin,
  onOpenDetail,
  favoriteShops,
  favoriteDates,
  getRating,
  backup,
  registered,
}) {
  const [section, setSection] = useState("favorites");
  const [viewMode, setViewMode] = useState("list");

  const favoriteCount = useMemo(
    () => products.filter((p) => isFavorite(p.id)).length,
    [products, isFavorite]
  );
  const counts = { favorites: favoriteCount, registered: registered.userProducts.length };

  return (
    <div className="max-w-xl mx-auto">
      <div className="px-5 pt-5">
        <SectionHeading en="Collection" ja="コレクション" />
        <div className="grid grid-cols-2 gap-1 p-1 mt-4 rounded-full bg-[var(--c-surface-2)]">
          {SECTIONS.map(({ id, icon: Icon, label }) => (
            <button
              key={id}
              onClick={() => setSection(id)}
              aria-pressed={section === id}
              className={`flex items-center justify-center gap-1.5 py-2 rounded-full text-[12px] font-medium transition-colors ${
                section === id ? "bg-[var(--accent)] text-[var(--on-accent)]" : "text-[var(--c-text-2)]"
              }`}
            >
              <Icon size={13} strokeWidth={2} />
              {label}
              <span className={section === id ? "opacity-80" : "opacity-60"}>{counts[id]}</span>
            </button>
          ))}
        </div>
      </div>

      {section === "favorites" ? (
        <>
          <div className="px-5 pt-4 flex justify-end">
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
              favoriteDates={favoriteDates}
              isFavorite={isFavorite}
              onToggleFavorite={onToggleFavorite}
              onOpenMap={onOpenMap}
              onLearnOrigin={onLearnOrigin}
              onOpenDetail={onOpenDetail}
            />
          ) : (
            <MyMapView favoriteShops={favoriteShops} />
          )}
        </>
      ) : (
        <UserCollectionView getRating={getRating} {...registered} />
      )}

      <div className="px-5 pb-5 flex flex-col gap-6">
        <TasteProfile products={products} getRating={getRating} onOpenDetail={onOpenDetail} />
        <CollectionBackup {...backup} />
      </div>
    </div>
  );
}
