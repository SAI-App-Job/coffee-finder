import { useMemo, useState } from "react";
import {
  Package,
  Clock,
  ArrowLeft,
  MapPin,
  ExternalLink,
  Search,
  X,
  Heart,
  LocateFixed,
  NotebookPen,
  Trash2,
  Plus,
} from "lucide-react";
import { SectionHeading, StarRating } from "./common";
import { ProductCard } from "./ProductCard";
import { FlavorChips } from "./FlavorPicker";
import { UserProductList } from "./UserProductCard";
import { formatDateTime } from "../utils/format";

const SHOP_SORT_MODE_ITEMS = [
  { id: "distance", label: "近い順", icon: MapPin },
  { id: "favoriteArea", label: "登録エリア", icon: Heart },
];

export function ShopCard({ shop, productCount, onSelect }) {
  return (
    <button
      onClick={onSelect}
      className="w-full text-left rounded-2xl bg-[var(--c-surface)] border border-[var(--c-border)] p-4 flex flex-col gap-2 hover:border-[var(--accent-label)] transition-colors"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] tracking-wider text-[var(--accent-label)] font-medium uppercase">
            {shop.prefecture}
          </p>
          <h3 className="font-serif text-[18px] leading-snug text-[var(--c-text)] mt-0.5">
            {shop.name}
          </h3>
        </div>
        <span className="shrink-0 text-[11px] px-2 py-0.5 rounded-full bg-[var(--c-surface-2)] text-[var(--accent-muted)] border border-[var(--c-border)] flex items-center gap-1">
          <Package size={11} />
          {productCount}件
        </span>
      </div>
      <p className="text-[13px] text-[var(--c-text-3)]">
        {shop.address}
        {shop.nearestStation?.name && (
          <span className="text-[var(--c-text-3)]/70">
            ・{shop.nearestStation.name}駅
            {typeof shop.nearestStation.walkMin === "number" && ` 徒歩${shop.nearestStation.walkMin}分`}
          </span>
        )}
      </p>
      <div className="flex items-center gap-1.5 text-[12px] text-[var(--c-text-3)] pt-1 mt-1 border-t border-[var(--c-border)]">
        <Clock size={12} strokeWidth={1.75} />
        <span>{shop.hours}</span>
      </div>
    </button>
  );
}

export function ShopListView({
  shops,
  productsByShop,
  onSelectShop,
  sortMode,
  onSortModeChange,
  geolocation,
  favoriteArea,
}) {
  const [searchQuery, setSearchQuery] = useState("");

  const filteredShops = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return shops;
    return shops.filter((shop) =>
      [shop.name, shop.prefecture, shop.address, shop.nearestStation?.name]
        .filter(Boolean)
        .some((v) => v.toLowerCase().includes(q))
    );
  }, [shops, searchQuery]);

  return (
    <main className="px-5 py-5 flex flex-col gap-3 max-w-xl mx-auto">
      <SectionHeading en="Shops" ja="店舗一覧" className="mb-1" />
      <div className="flex items-center gap-1.5 overflow-x-auto scrollbar-hide">
        {SHOP_SORT_MODE_ITEMS.map(({ id, label, icon: Icon }) => {
          // 「近い順」は、実際に距離順ソートが有効な(位置情報取得に成功した)
          // 場合のみ選択状態にする。商品タブと同じ方針。
          const isActive =
            id === "distance" ? sortMode === id && geolocation.status === "success" : sortMode === id;
          return (
            <button
              key={id}
              onClick={() => onSortModeChange(id)}
              aria-pressed={isActive}
              className={`flex items-center gap-1 shrink-0 text-[12px] px-3 py-1.5 rounded-full border transition-colors ${
                isActive
                  ? "bg-[var(--accent)] text-[var(--on-accent)] border-[var(--accent)]"
                  : "border-[var(--c-border)] text-[var(--c-text-2)]"
              }`}
            >
              <Icon size={12} strokeWidth={2} />
              {label}
            </button>
          );
        })}
      </div>
      {sortMode === "distance" && geolocation.status !== "success" && (
        <div className="flex items-start gap-1 text-[11px] text-[var(--c-text-3)]">
          <LocateFixed size={11} strokeWidth={1.75} className="shrink-0 mt-0.5" />
          <p>
            {geolocation.status === "pending" && "位置情報を取得中です(取得できるまで全件表示しています)"}
            {geolocation.status === "denied" && (
              <>
                位置情報が許可されていないため、全件表示しています。ブラウザの拒否設定はアプリからは解除できないため、ブラウザのアドレスバー付近のアイコンから位置情報の許可を変更したうえで、
                <button
                  onClick={geolocation.retry}
                  className="text-[var(--accent)] underline underline-offset-2"
                >
                  再試行
                </button>
                してください
              </>
            )}
            {geolocation.status === "error" && (
              <>
                位置情報を取得できなかったため、全件表示しています。
                <button
                  onClick={geolocation.retry}
                  className="text-[var(--accent)] underline underline-offset-2"
                >
                  位置情報を取得
                </button>
              </>
            )}
            {geolocation.status === "unsupported" &&
              "この端末・ブラウザは位置情報に対応していないため、全件表示しています"}
          </p>
        </div>
      )}
      {sortMode === "favoriteArea" && (
        <p className="text-[11px] text-[var(--c-text-3)]">
          {favoriteArea.prefecture
            ? `登録エリア: ${favoriteArea.prefecture}${favoriteArea.city ? ` ${favoriteArea.city}` : ""}(設定で変更できます)`
            : "登録エリアが未登録です(設定で登録できます)"}
        </p>
      )}
      <div className="relative mb-1">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--c-text-3)]" strokeWidth={2} />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="店舗名・都道府県・住所・駅名で検索"
          className="w-full pl-9 pr-9 py-2.5 rounded-xl bg-[var(--c-surface)] border border-[var(--c-border)] text-[13px] text-[var(--c-text)] placeholder:text-[var(--c-text-3)] focus:outline-none focus:border-[var(--accent-label)]"
        />
        {searchQuery && (
          <button
            onClick={() => setSearchQuery("")}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--c-text-3)] hover:text-[var(--c-text)]"
            aria-label="検索をクリア"
          >
            <X size={14} />
          </button>
        )}
      </div>
      {shops.length === 0 ? (
        <p className="text-center py-12 text-[13px] text-[var(--c-text-3)]">
          {sortMode === "favoriteArea"
            ? favoriteArea.prefecture
              ? "登録したエリアには該当する店舗がありません。設定でエリアを変更してみてください"
              : "設定で登録エリア(都道府県・市区町村)を登録してください"
            : "該当する店舗が見つかりませんでした"}
        </p>
      ) : filteredShops.length === 0 ? (
        <p className="text-center py-12 text-[13px] text-[var(--c-text-3)]">
          該当する店舗が見つかりませんでした
        </p>
      ) : (
        filteredShops.map((shop) => (
          <ShopCard
            key={shop.name}
            shop={shop}
            productCount={(productsByShop[shop.name] || []).length}
            onSelect={() => onSelectShop(shop)}
          />
        ))
      )}
    </main>
  );
}

export function LocationCard({ location, onOpenMap }) {
  return (
    <div className="rounded-xl bg-[var(--c-surface-2)] border border-[var(--c-border)] p-3 flex flex-col gap-1.5">
      <p className="text-[14px] font-medium text-[var(--c-text)]">{location.label}</p>
      <p className="text-[12px] text-[var(--c-text-2)]">{location.address}</p>
      {(location.hours || location.tel || location.email) && (
        <div className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[12px] text-[var(--c-text-3)]">
          {location.hours && (
            <span className="flex items-center gap-1.5">
              <Clock size={12} strokeWidth={1.75} />
              {location.hours}
            </span>
          )}
          {location.tel && <span>{location.hours ? "・" : ""}{location.tel}</span>}
          {location.email && (
            <a
              href={`mailto:${location.email}`}
              className="text-[var(--accent)] hover:text-[var(--accent-soft)] transition-colors"
            >
              {location.hours || location.tel ? "・" : ""}{location.email}
            </a>
          )}
        </div>
      )}
      <button
        onClick={() => onOpenMap(location)}
        className="mt-1 self-start flex items-center gap-1.5 text-[12px] text-[var(--accent)] hover:text-[var(--accent-soft)] transition-colors"
      >
        <MapPin size={12} strokeWidth={2} />
        この店舗をGoogleマップで開く
      </button>
    </div>
  );
}

function ShopNoteCard({ note, onDelete }) {
  return (
    <div className="rounded-xl bg-[var(--c-surface-2)] border border-[var(--c-border)] p-3.5 flex flex-col gap-2">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[14px] font-medium text-[var(--c-text)] leading-snug">{note.productName}</p>
          {note.rating > 0 && (
            <div className="mt-1">
              <StarRating value={note.rating} size={13} readOnly />
            </div>
          )}
          <p className="text-[11px] text-[var(--c-text-3)] mt-1">登録日 {formatDateTime(note.recordedAt)}</p>
        </div>
        <button
          onClick={() => onDelete(note.id)}
          className="shrink-0 text-[var(--c-text-3)] hover:text-[var(--c-text)] transition-colors -m-1 p-1"
          aria-label="このノートを削除"
        >
          <Trash2 size={13} />
        </button>
      </div>
      {note.note && <p className="text-[12px] text-[var(--c-text-2)] leading-relaxed">{note.note}</p>}
      <FlavorChips flavors={note.flavors} />
    </div>
  );
}

export function ShopDetailView({
  shop,
  products,
  onBack,
  onOpenMap,
  onOpenLocationMap,
  isFavorite,
  onToggleFavorite,
  onOpenDetail,
  tastingNotes = [],
  onCreateTastingNote,
  onDeleteTastingNote,
  registered,
}) {
  const hasMultipleLocations = shop.locations && shop.locations.length > 0;

  return (
    <div className="max-w-xl mx-auto">
      <div className="px-5 pt-4">
        <button
          onClick={onBack}
          className="flex items-center gap-1 text-[13px] text-[var(--c-text-3)] hover:text-[var(--c-text)] transition-colors mb-4"
        >
          <ArrowLeft size={14} />
          店舗一覧に戻る
        </button>

        <p className="text-[11px] tracking-wider text-[var(--accent-label)] font-medium uppercase">
          {shop.prefecture} ・ {shop.platform}
        </p>
        <h2 className="font-serif text-[24px] text-[var(--c-text)] mt-1">{shop.name}</h2>
        <p className="text-[13px] text-[var(--c-text-3)] mt-1.5">{shop.address}</p>

        {!hasMultipleLocations && (
          <div className="flex items-center gap-1.5 text-[13px] text-[var(--c-text-2)] mt-2">
            <Clock size={13} strokeWidth={1.75} />
            <span>{shop.hours}</span>
          </div>
        )}

        <div className="flex gap-2 mt-4">
          {!hasMultipleLocations && (
            <button
              onClick={onOpenMap}
              className="flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-xl bg-[var(--accent)] text-[var(--on-accent)] text-[13px] font-medium"
            >
              <MapPin size={14} strokeWidth={2} />
              Googleマップで開く
            </button>
          )}
          {(shop.url || shop.instagramUrl) && (
            <a
              href={shop.url || shop.instagramUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-xl border border-[var(--c-border)] text-[var(--c-text-2)] text-[13px]"
            >
              {shop.url ? "公式サイト" : "公式Instagram"}
              <ExternalLink size={12} />
            </a>
          )}
        </div>

        {/* 店頭でしか買えない豆など、アプリに載っていない商品を、この店舗の商品として手動で登録する */}
        {registered && (
          <button
            onClick={registered.onRegister}
            className="w-full mt-2 flex items-center justify-center gap-1.5 py-2.5 rounded-xl bg-[var(--accent)] text-[var(--on-accent)] text-[13px] font-medium hover:bg-[var(--accent-soft)] transition-colors"
          >
            <Plus size={14} strokeWidth={2.2} />
            店頭の商品を登録
          </button>
        )}

        {registered && registered.products.length > 0 && (
          <div className="mt-4">
            <p className="text-[12px] text-[var(--c-text-3)] mb-2">
              店頭の商品(手動登録) {registered.products.length}件
            </p>
            <div className="flex flex-col gap-2">
              <UserProductList
                products={registered.products}
                getPhotoUrl={registered.getPhotoUrl}
                getRating={registered.getRating}
                onRate={registered.onRate}
                getLogCount={registered.getLogCount}
                onOpenTastingLog={registered.onOpenTastingLog}
                onEdit={registered.onEdit}
                onDelete={registered.onDelete}
              />
            </div>
          </div>
        )}

        <button
          onClick={onCreateTastingNote}
          className="w-full mt-2 flex items-center justify-center gap-1.5 py-2.5 rounded-xl border border-[var(--accent)] text-[var(--accent)] text-[13px] font-medium hover:bg-[var(--accent)] hover:text-[var(--on-accent)] transition-colors"
        >
          <NotebookPen size={14} strokeWidth={2} />
          テイスティングノートを作成
        </button>

        {tastingNotes.length > 0 && (
          <div className="mt-4">
            <p className="text-[12px] text-[var(--c-text-3)] mb-2">この店のテイスティングノート {tastingNotes.length}件</p>
            <div className="flex flex-col gap-2">
              {tastingNotes.map((n) => (
                <ShopNoteCard key={n.id} note={n} onDelete={onDeleteTastingNote} />
              ))}
            </div>
          </div>
        )}

        {hasMultipleLocations && (
          <div className="mt-4">
            <p className="text-[12px] text-[var(--c-text-3)] mb-2">
              実店舗 {shop.locations.length}箇所
            </p>
            <div className="flex flex-col gap-2">
              {shop.locations.map((loc) => (
                <LocationCard key={loc.label} location={loc} onOpenMap={onOpenLocationMap} />
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="px-5 py-5 flex flex-col gap-3">
        <p className="text-[12px] text-[var(--c-text-3)]">取扱商品 {products.length}件</p>
        {products.map((product) => (
          <ProductCard
            key={product.id}
            product={product}
            onOpenMap={onOpenMap}
            isFavorite={isFavorite}
            onToggleFavorite={onToggleFavorite}
            onOpenDetail={onOpenDetail}
          />
        ))}
      </div>
    </div>
  );
}
