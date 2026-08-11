import { Package, Clock, ArrowLeft, MapPin, ExternalLink } from "lucide-react";
import { SectionHeading } from "./common";
import { ProductCard } from "./ProductCard";

export function ShopCard({ shop, productCount, onSelect }) {
  return (
    <button
      onClick={onSelect}
      className="w-full text-left rounded-2xl bg-[#2F241A] border border-[#4A3A2A] p-4 flex flex-col gap-2 hover:border-[#8B5E2E] transition-colors"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] tracking-wider text-[#8B5E2E] font-medium uppercase">
            {shop.prefecture}
          </p>
          <h3 className="font-serif text-[18px] leading-snug text-[#F2E9DD] mt-0.5">
            {shop.name}
          </h3>
        </div>
        <span className="shrink-0 text-[11px] px-2 py-0.5 rounded-full bg-[#3B2211] text-[#C9A876] border border-[#4A3A2A] flex items-center gap-1">
          <Package size={11} />
          {productCount}件
        </span>
      </div>
      <p className="text-[13px] text-[#8B7361]">{shop.address}</p>
      <div className="flex items-center gap-1.5 text-[12px] text-[#8B7361] pt-1 mt-1 border-t border-[#4A3A2A]">
        <Clock size={12} strokeWidth={1.75} />
        <span>{shop.hours}</span>
      </div>
    </button>
  );
}

export function ShopListView({ shops, productsByShop, onSelectShop }) {
  return (
    <main className="px-5 py-5 flex flex-col gap-3 max-w-xl mx-auto">
      <SectionHeading en="Shops" ja="店舗一覧" className="mb-1" />
      {shops.map((shop) => (
        <ShopCard
          key={shop.name}
          shop={shop}
          productCount={(productsByShop[shop.name] || []).length}
          onSelect={() => onSelectShop(shop)}
        />
      ))}
    </main>
  );
}

export function LocationCard({ location, onOpenMap }) {
  return (
    <div className="rounded-xl bg-[#3B2211] border border-[#4A3A2A] p-3 flex flex-col gap-1.5">
      <p className="text-[14px] font-medium text-[#F2E9DD]">{location.label}</p>
      <p className="text-[12px] text-[#B8A891]">{location.address}</p>
      {(location.hours || location.tel || location.email) && (
        <div className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[12px] text-[#8B7361]">
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
              className="text-[#D4A24E] hover:text-[#E8C89A] transition-colors"
            >
              {location.hours || location.tel ? "・" : ""}{location.email}
            </a>
          )}
        </div>
      )}
      <button
        onClick={() => onOpenMap(location)}
        className="mt-1 self-start flex items-center gap-1.5 text-[12px] text-[#D4A24E] hover:text-[#E8C89A] transition-colors"
      >
        <MapPin size={12} strokeWidth={2} />
        この店舗をGoogleマップで開く
      </button>
    </div>
  );
}

export function ShopDetailView({ shop, products, onBack, onOpenMap, onOpenLocationMap }) {
  const hasMultipleLocations = shop.locations && shop.locations.length > 0;

  return (
    <div className="max-w-xl mx-auto">
      <div className="px-5 pt-4">
        <button
          onClick={onBack}
          className="flex items-center gap-1 text-[13px] text-[#8B7361] hover:text-[#F2E9DD] transition-colors mb-4"
        >
          <ArrowLeft size={14} />
          店舗一覧に戻る
        </button>

        <p className="text-[11px] tracking-wider text-[#8B5E2E] font-medium uppercase">
          {shop.prefecture} ・ {shop.platform}
        </p>
        <h2 className="font-serif text-[24px] text-[#F2E9DD] mt-1">{shop.name}</h2>
        <p className="text-[13px] text-[#8B7361] mt-1.5">{shop.address}</p>

        {!hasMultipleLocations && (
          <div className="flex items-center gap-1.5 text-[13px] text-[#B8A891] mt-2">
            <Clock size={13} strokeWidth={1.75} />
            <span>{shop.hours}</span>
          </div>
        )}

        <div className="flex gap-2 mt-4">
          {!hasMultipleLocations && (
            <button
              onClick={onOpenMap}
              className="flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-xl bg-[#D4A24E] text-[#231810] text-[13px] font-medium"
            >
              <MapPin size={14} strokeWidth={2} />
              Googleマップで開く
            </button>
          )}
          <a
            href={shop.url}
            target="_blank"
            rel="noopener noreferrer"
            className={`flex items-center justify-center gap-1.5 py-2.5 rounded-xl border border-[#4A3A2A] text-[#B8A891] text-[13px] ${
              hasMultipleLocations ? "flex-1" : "flex-1"
            }`}
          >
            公式サイト
            <ExternalLink size={12} />
          </a>
        </div>

        {hasMultipleLocations && (
          <div className="mt-4">
            <p className="text-[12px] text-[#8B7361] mb-2">
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
        <p className="text-[12px] text-[#8B7361]">取扱商品 {products.length}件</p>
        {products.map((product) => (
          <ProductCard key={product.id} product={product} onOpenMap={onOpenMap} />
        ))}
      </div>
    </div>
  );
}
