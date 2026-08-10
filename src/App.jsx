import { useState, useMemo, useEffect } from "react";
import { Search, X, SlidersHorizontal, Coffee } from "lucide-react";
import { MOCK_PRODUCTS } from "./data/products";
import { SHOPS } from "./data/shops";
import { EVENTS } from "./data/events";
import { TAB_ITEMS } from "./data/navigation";
import { categorizeFlavorNotes } from "./utils/flavor";
import { loadRemoteData } from "./data/remote";
import { ProductCard, DiscoveryFactCard } from "./components/ProductCard";
import { FilterSheet } from "./components/FilterSheet";
import { ShopListView, ShopDetailView } from "./components/ShopViews";
import { BuyingGuideView } from "./components/BuyingGuideView";
import { TriviaView } from "./components/TriviaView";
import { MapLinkModal } from "./components/common";

export default function CoffeeProductList() {
  // 初期値はローカルのモックデータ(=フォールバック)。GitHub上のJSONの取得に
  // 成功した場合のみ、下のuseEffectで実データに差し替える。
  const [products, setProducts] = useState(MOCK_PRODUCTS);
  const [shops, setShops] = useState(SHOPS);
  const [events, setEvents] = useState(EVENTS);

  useEffect(() => {
    let cancelled = false;
    loadRemoteData().then((data) => {
      if (cancelled || !data) return;
      setProducts(data.products);
      setShops(data.shops);
      setEvents(data.events);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const [tab, setTab] = useState("products"); // "products" | "shops"
  const [filters, setFilters] = useState({
    country: new Set(),
    prefecture: new Set(),
    shop: new Set(),
    flavorCategory: new Set(),
    roast: new Set(),
  });
  const [sheetOpen, setSheetOpen] = useState(false);
  const [mapTarget, setMapTarget] = useState(null);
  const [selectedShop, setSelectedShop] = useState(null);
  const [pendingOriginCountry, setPendingOriginCountry] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");

  const learnAboutOrigin = (country) => {
    setPendingOriginCountry(country);
    setTab("guide");
  };

  const viewProductsForCountry = (country) => {
    setSearchQuery("");
    setFilters({
      country: new Set([country]),
      prefecture: new Set(),
      shop: new Set(),
      flavorCategory: new Set(),
      roast: new Set(),
    });
    setSelectedShop(null);
    setTab("products");
  };

  const activeCount =
    filters.country.size + filters.prefecture.size + filters.shop.size + filters.flavorCategory.size + filters.roast.size;

  const filtered = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return products.filter((p) => {
      if (filters.country.size && !filters.country.has(p.originCountry)) return false;
      if (filters.prefecture.size && !filters.prefecture.has(p.prefecture)) return false;
      if (filters.shop.size && !filters.shop.has(p.shopName)) return false;
      if (filters.flavorCategory.size) {
        const productCats = categorizeFlavorNotes(p.flavorNotes).map((c) => c.ja);
        const hasMatch = productCats.some((ja) => filters.flavorCategory.has(ja));
        if (!hasMatch) return false;
      }
      if (filters.roast.size) {
        // 焙煎度が固定の商品はその値で判定。注文時に焙煎度を選べる商品
        // (roastSelectable)は、どの焙煎度で選んでも実現できるため、
        // 焙煎度での絞り込みでは除外しない(選択肢として常に該当させる)。
        const matchesFixedRoast = p.roast && filters.roast.has(p.roast);
        if (!matchesFixedRoast && !p.roastSelectable) return false;
      }
      if (q) {
        const haystack = [
          p.rawName, p.originCountry, p.designatedBrand, p.processingMethod,
          p.grade, p.farmNote, p.shopName, p.shopAddress, p.prefecture,
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        if (!haystack.includes(q)) return false;
      }
      return true;
    });
  }, [products, filters, searchQuery]);

  const productsByShop = useMemo(() => {
    const map = {};
    products.forEach((p) => {
      map[p.shopName] = map[p.shopName] || [];
      map[p.shopName].push(p);
    });
    return map;
  }, [products]);

  const removeFilter = (dim, value) => {
    setFilters((prev) => {
      const next = new Set(prev[dim]);
      next.delete(value);
      return { ...prev, [dim]: next };
    });
  };

  const activeChips = [
    ...[...filters.country].map((v) => ({ dim: "country", v })),
    ...[...filters.prefecture].map((v) => ({ dim: "prefecture", v })),
    ...[...filters.shop].map((v) => ({ dim: "shop", v })),
    ...[...filters.flavorCategory].map((v) => ({ dim: "flavorCategory", v })),
    ...[...filters.roast].map((v) => ({ dim: "roast", v })),
  ];

  const openMapForProduct = (product) =>
    setMapTarget({ shopName: product.shopName, shopAddress: product.shopAddress, mapQuery: product.mapQuery });
  const openMapForShop = (shop) =>
    setMapTarget({ shopName: shop.name, shopAddress: shop.address, mapQuery: shop.mapQuery });
  const openMapForLocation = (location) =>
    setMapTarget({ shopName: location.label, shopAddress: location.address, mapQuery: location.mapQuery });

  return (
    <div className="min-h-full bg-[#231810] text-[#F2E9DD]">
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600&family=Inter:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');
        .font-serif { font-family: 'Fraunces', serif; }
        * { font-family: 'Inter', sans-serif; }
        .font-mono { font-family: 'IBM Plex Mono', monospace; }
      `}</style>

      <header className="px-5 pt-6 pb-3 border-b border-[#4A3A2A] sticky top-0 bg-[#231810]/95 backdrop-blur-sm z-10">
        <p className="text-[11px] tracking-[0.2em] text-[#8B5E2E] uppercase">
          Coffee Finder
        </p>
        <h1 className="font-serif text-[26px] leading-tight mt-1">
          近くの自家焙煎豆を探す
        </h1>
        <p className="text-[12px] text-[#8B7361] mt-0.5">Find Local Roasters Near You</p>

        <div className="flex gap-1 mt-4 p-1 rounded-full bg-[#3B2211] w-fit overflow-x-auto max-w-full">
          {TAB_ITEMS.map(({ id, icon: Icon, ja, en }) => (
            <button
              key={id}
              onClick={() => { setTab(id); setSelectedShop(null); }}
              className={`flex items-center gap-1.5 shrink-0 px-3.5 py-1.5 rounded-full transition-colors ${
                tab === id ? "bg-[#D4A24E] text-[#231810]" : "text-[#B8A891]"
              }`}
            >
              <Icon size={13} strokeWidth={2} />
              <span className="flex flex-col items-start leading-none">
                <span className="text-[13px] font-medium">{ja}</span>
                <span
                  className={`text-[9px] tracking-wide uppercase mt-0.5 ${
                    tab === id ? "text-[#231810]/70" : "text-[#B8A891]/60"
                  }`}
                >
                  {en}
                </span>
              </span>
            </button>
          ))}
        </div>
      </header>

      {tab === "products" && !selectedShop && (
        <div className="px-5 pt-4 max-w-xl mx-auto">
          <p className="text-[13px] text-[#8B7361]">
            {filtered.length}件の商品(産地・精選方法・グレードで正規化済み)
          </p>
          <div className="relative mt-3">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#8B7361]" strokeWidth={2} />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="商品名・産地・銘柄・店舗名・住所で検索"
              className="w-full pl-9 pr-9 py-2.5 rounded-xl bg-[#2F241A] border border-[#4A3A2A] text-[13px] text-[#F2E9DD] placeholder:text-[#8B7361] focus:outline-none focus:border-[#8B5E2E]"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery("")}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-[#8B7361] hover:text-[#F2E9DD]"
                aria-label="検索をクリア"
              >
                <X size={14} />
              </button>
            )}
          </div>
          <div className="flex items-center gap-2 mt-3">
            <button
              onClick={() => setSheetOpen(true)}
              className="flex items-center gap-1.5 shrink-0 text-[13px] px-3.5 py-1.5 rounded-full border border-[#8B5E2E] text-[#D4A24E] hover:bg-[#3B2211] transition-colors"
            >
              <SlidersHorizontal size={13} strokeWidth={2} />
              絞り込み
              {activeCount > 0 && (
                <span className="ml-0.5 text-[11px] bg-[#D4A24E] text-[#231810] rounded-full w-4 h-4 flex items-center justify-center font-medium">
                  {activeCount}
                </span>
              )}
            </button>
            <div className="flex gap-1.5 overflow-x-auto pb-1 scrollbar-hide">
              {activeChips.map(({ dim, v }) => (
                <button
                  key={`${dim}-${v}`}
                  onClick={() => removeFilter(dim, v)}
                  className="shrink-0 flex items-center gap-1 text-[12px] pl-2.5 pr-1.5 py-1 rounded-full bg-[#3B2211] text-[#C9A876] border border-[#4A3A2A]"
                >
                  {v}
                  <X size={11} />
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {tab === "products" && (
        <main className="px-5 py-5 flex flex-col gap-3 max-w-xl mx-auto">
          <DiscoveryFactCard />
          {filtered.length === 0 ? (
            <div className="text-center py-16 text-[#8B7361]">
              <Coffee size={28} className="mx-auto mb-3 opacity-40" />
              <p className="text-[14px]">該当する商品が見つかりませんでした</p>
            </div>
          ) : (
            filtered.map((product) => (
              <ProductCard
                key={product.id}
                product={product}
                onOpenMap={openMapForProduct}
                onLearnOrigin={learnAboutOrigin}
              />
            ))
          )}
        </main>
      )}

      {tab === "shops" && !selectedShop && (
        <ShopListView shops={shops} productsByShop={productsByShop} onSelectShop={setSelectedShop} />
      )}

      {tab === "shops" && selectedShop && (
        <ShopDetailView
          shop={selectedShop}
          products={productsByShop[selectedShop.name] || []}
          onBack={() => setSelectedShop(null)}
          onOpenMap={() => openMapForShop(selectedShop)}
          onOpenLocationMap={openMapForLocation}
        />
      )}

      {tab === "guide" && (
        <BuyingGuideView pendingOriginCountry={pendingOriginCountry} onViewProducts={viewProductsForCountry} />
      )}
      {tab === "trivia" && <TriviaView onLearnOrigin={learnAboutOrigin} events={events} />}

      <FilterSheet
        open={sheetOpen}
        onClose={() => setSheetOpen(false)}
        filters={filters}
        setFilters={setFilters}
        resultCount={filtered.length}
      />
      <MapLinkModal target={mapTarget} onClose={() => setMapTarget(null)} />
    </div>
  );
}
