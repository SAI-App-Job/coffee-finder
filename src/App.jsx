import { useState, useMemo, useEffect, useCallback } from "react";
import { Virtuoso } from "react-virtuoso";
import { Search, X, SlidersHorizontal, Coffee, Bell, Info, MapPin, Sparkles, Shuffle, LocateFixed, Heart } from "lucide-react";
import { MOCK_PRODUCTS } from "./data/products";
import { SHOPS } from "./data/shops";
import { EVENTS } from "./data/events";
import { TAB_ITEMS } from "./data/navigation";
import { ORIGIN_GUIDE } from "./data/originGuide";
import { categorizeFlavorNotes } from "./utils/flavor";
import { loadRemoteData } from "./data/remote";
import { sortByDistance, sortNewArrivalsFirst, sortByRecency, pickRandomDisplaySet, filterByFavoriteArea, shuffle } from "./utils/productSort";
import { buildPrefectureRank, sortByPrefecturePopularity } from "./utils/prefectureOrder";
import { useFavorites } from "./hooks/useFavorites";
import { useAccentTheme } from "./hooks/useAccentTheme";
import { usePremium } from "./hooks/usePremium";
import { useToast } from "./hooks/useToast";
import { useViewHistory } from "./hooks/useViewHistory";
import { useComparison } from "./hooks/useComparison";
import { useRatings } from "./hooks/useRatings";
import { useTastingLog } from "./hooks/useTastingLog";
import { useAlerts } from "./hooks/useAlerts";
import { useGeolocation } from "./hooks/useGeolocation";
import { useDisplayRadius } from "./hooks/useDisplayRadius";
import { useFavoriteArea } from "./hooks/useFavoriteArea";
import { ProductCard, DiscoveryFactCard } from "./components/ProductCard";
import { ProductDetailModal } from "./components/ProductDetailModal";
import { TastingLogModal } from "./components/TastingLogModal";
import { AlertsPanel } from "./components/AlertsPanel";
import { AboutView } from "./components/AboutView";
import { FilterSheet } from "./components/FilterSheet";
import { ShopListView, ShopDetailView } from "./components/ShopViews";
import { FavoritesTabView } from "./components/FavoritesTabView";
import { BuyingGuideView } from "./components/BuyingGuideView";
import { TriviaView } from "./components/TriviaView";
import { MyPageView } from "./components/MyPageView";
import { AdBannerPlaceholder } from "./components/AdBanner";
import { CompareTray, ComparisonModal } from "./components/Compare";
import { CopyrightFooter, MapLinkModal, Toast } from "./components/common";

const SORT_MODE_ITEMS = [
  { id: "distance", label: "近い順", icon: MapPin },
  { id: "favoriteArea", label: "登録エリア", icon: Heart },
  { id: "new", label: "新規掲載", icon: Sparkles },
  { id: "random", label: "ランダム", icon: Shuffle },
];

export default function CoffeeProductList() {
  // 初期値はローカルのモックデータ(=フォールバック)。GitHub上のJSONの取得に
  // 成功した場合のみ、下のuseEffectで実データに差し替える。
  const [products, setProducts] = useState(MOCK_PRODUCTS);
  const [shops, setShops] = useState(SHOPS);
  const [events, setEvents] = useState(EVENTS);
  const [remoteLoaded, setRemoteLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    loadRemoteData().then((data) => {
      if (cancelled || !data) return;
      setProducts(data.products);
      setShops(data.shops);
      setEvents(data.events);
      setRemoteLoaded(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const { themeId, setThemeId, themes } = useAccentTheme();
  const { isPremium, setPremium } = usePremium();
  const { message: toastMessage, showToast, dismissToast } = useToast();
  const { favoriteIds, isFavorite, toggleFavorite, importFavorites } = useFavorites(isPremium, showToast);
  const { history, recordView } = useViewHistory(isPremium);
  const {
    compareIds,
    isComparing,
    toggleCompare,
    removeFromCompare,
    clearCompare,
    limit: compareLimit,
  } = useComparison(isPremium, showToast);
  const { getRating, setRating } = useRatings();
  const { getLogs, addLog, deleteLog } = useTastingLog();

  const [tab, setTab] = useState("products"); // "products" | "favorites" | "shops" | "guide" | "trivia" | "mypage"
  const [detailProduct, setDetailProduct] = useState(null);
  const [tastingLogProduct, setTastingLogProduct] = useState(null);
  const [compareModalOpen, setCompareModalOpen] = useState(false);
  // country/prefectureは単一選択のプルダウンのため空文字列("")が未選択を表す。
  // flavorCategoryのみ複数選択(チップ)のままなのでSetで持つ。焙煎度フィルタは
  // 実データではほぼ機能しない(roastSelectable商品が62.5%を占め、どの焙煎度を
  // 選んでも同じ結果になっていた)ため廃止した。
  const [filters, setFilters] = useState({
    country: "",
    prefecture: "",
    flavorCategory: new Set(),
  });
  const [sheetOpen, setSheetOpen] = useState(false);
  const [mapTarget, setMapTarget] = useState(null);
  const [selectedShop, setSelectedShop] = useState(null);
  const [pendingOriginCountry, setPendingOriginCountry] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [showOutOfStock, setShowOutOfStock] = useState(false);

  // 商品タブの並べ替え軸。"distance"(近い順、初期表示)|"new"(新規掲載)|
  // "random"(ランダム)。端末内のセッション状態としてのみ保持し(再読み込みで
  // "distance"に戻る)、"random"の表示範囲設定のみマイページで永続化する。
  const [sortMode, setSortMode] = useState("distance");
  const geolocation = useGeolocation();
  const { displayRadiusId, setDisplayRadiusId, options: displayRadiusOptions } = useDisplayRadius();
  const { favoriteArea, setPrefecture: setFavoriteAreaPrefecture, setCity: setFavoriteAreaCity } = useFavoriteArea();
  // ランダム表示のシャッフル順は、無関係な再描画(お気に入り操作等)では
  // 変えたくないため、絞り込み結果や設定が実際に変わった時だけ再計算する。

  // 都道府県ごとの登録店舗数のランク(多い順、東京都が最多のため自然と先頭に
  // 来る)。全件表示(位置情報未取得時の商品タブ)と店舗一覧の並び順に使う。
  const prefectureRank = useMemo(() => buildPrefectureRank(shops), [shops]);

  // 絞り込みシートの都道府県プルダウン用の選択肢。実データ(products)に
  // 実在する都道府県のみを対象に、件数付きで同じ並び順(店舗数が多い順)で出す。
  // 以前はモックデータ由来の2県しか選べないバグがあったため、実データ基準に
  // 作り直した。
  const prefectureOptions = useMemo(() => {
    const counts = new Map();
    for (const p of products) {
      if (!p.prefecture) continue;
      counts.set(p.prefecture, (counts.get(p.prefecture) || 0) + 1);
    }
    const ordered = sortByPrefecturePopularity([...counts.keys()], prefectureRank, (pref) => pref);
    return ordered.map((prefecture) => ({ value: prefecture, count: counts.get(prefecture) }));
  }, [products, prefectureRank]);

  const learnAboutOrigin = useCallback(
    (country) => {
      // ORIGIN_GUIDEに実在しない国(産地タブに詳細ページが無い)の場合、
      // 以前はuseStateの初期値フォールバック(ORIGIN_GUIDE[0]=エチオピア)により
      // 誤ってエチオピアのページへ遷移してしまっていた。ここで事前に実在を
      // 確認し、無い場合はタブ遷移自体を行わずトーストで案内する。
      const matched = ORIGIN_GUIDE.some((o) => o.country === country);
      if (!matched) {
        showToast("この産地の情報は準備中です");
        return;
      }
      setPendingOriginCountry(country);
      setTab("guide");
      // タブ切り替えはページ遷移ではないため、直前のタブでのスクロール位置が
      // そのまま引き継がれてしまう。産地タブの先頭(国名見出し)が隠れて見えなく
      // なる不具合になっていたため、ジャンプ時は明示的に先頭へ戻す。
      window.scrollTo({ top: 0 });
    },
    [showToast]
  );

  const viewProductsForCountry = (country) => {
    setSearchQuery("");
    setFilters({
      country: new Set([country]),
      prefecture: new Set(),
      flavorCategory: new Set(),
      roast: new Set(),
    });
    setSelectedShop(null);
    setTab("products");
  };

  const activeCount =
    (filters.country ? 1 : 0) + (filters.prefecture ? 1 : 0) + filters.flavorCategory.size;

  const filtered = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return products.filter((p) => {
      // 在庫状態が不明な商品(モックデータ等)は隠さない。チェックボックスが
      // オフの間は「一時的に品切れ」「終売」のどちらも一覧から除外する。
      if (!showOutOfStock && p.stockStatus && p.stockStatus !== "販売中") return false;
      if (filters.country) {
        // ブレンド商品はorigin_countryを持たないため、blendComponentsの
        // いずれかの産地国が絞り込み条件に一致すればヒットさせる。
        const countries = p.blendComponents?.length
          ? p.blendComponents.map((c) => c.originCountry).filter(Boolean)
          : [p.originCountry];
        if (!countries.includes(filters.country)) return false;
      }
      if (filters.prefecture && p.prefecture !== filters.prefecture) return false;
      if (filters.flavorCategory.size) {
        const productCats = categorizeFlavorNotes(p.flavorNotes).map((c) => c.ja);
        const hasMatch = productCats.some((ja) => filters.flavorCategory.has(ja));
        if (!hasMatch) return false;
      }
      if (q) {
        const blendCountries = p.blendComponents?.length
          ? p.blendComponents.map((c) => c.originCountry)
          : [];
        const haystack = [
          p.rawName, p.originCountry, p.designatedBrand, p.processingMethod,
          p.grade, p.farmNote, p.shopName, p.shopAddress, p.prefecture,
          ...blendCountries,
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        if (!haystack.includes(q)) return false;
      }
      return true;
    });
  }, [products, filters, searchQuery, showOutOfStock]);

  // 並べ替え軸ごとの表示リスト。
  // - "distance": 位置情報の取得に成功していれば距離順。許可待ち・タイムアウト・
  //   拒否・非対応の間は「近い順」を騙らず、登録店舗数が多い都道府県順(東京都
  //   から)の全件表示にする(このボタンもその間は非選択状態にする。取得成功時
  //   に自動で距離順へ切り替わり、拒否時に自動再試行はしない)。
  // - "favoriteArea": マイページで手動登録した都道府県・市区町村(住所文字列の
  //   部分一致)に該当する商品のみ、新しい順に表示。郵便番号やジオコーディング
  //   は使わない(店舗網羅率が市区町村単位でも疎らなため、登録は手入力とし、
  //   0件になる場合はマイページでの再登録を促す)。
  // - "new": 新規掲載(30日以内)のみを対象に新しい順。表示範囲は全国固定。
  // - "random": マイページの表示範囲設定に応じた範囲内からランダムに表示。
  const displayed = useMemo(() => {
    if (sortMode === "favoriteArea") {
      // 都道府県が未登録の間は絞り込みようがないため、全国表示にフォール
      // バックせず空にする(マイページでの登録を促す)。
      if (!favoriteArea.prefecture) return [];
      return sortByRecency(filterByFavoriteArea(filtered, favoriteArea));
    }
    if (sortMode === "new") return sortNewArrivalsFirst(filtered);
    if (sortMode === "random") {
      const withinRange = pickRandomDisplaySet(filtered, {
        radiusId: displayRadiusId,
        coords: geolocation.coords,
      });
      return shuffle(withinRange);
    }
    // sortMode === "distance"
    if (geolocation.status === "success") return sortByDistance(filtered, geolocation.coords);
    return sortByPrefecturePopularity(filtered, prefectureRank, (p) => p.prefecture);
  }, [filtered, sortMode, geolocation.status, geolocation.coords, displayRadiusId, favoriteArea, prefectureRank]);

  const productsByShop = useMemo(() => {
    const map = {};
    products.forEach((p) => {
      map[p.shopName] = map[p.shopName] || [];
      map[p.shopName].push(p);
    });
    return map;
  }, [products]);

  // 店舗一覧も、全件表示の商品タブと同じ都道府県順(登録店舗数が多い順、
  // 東京都から)にする。
  const sortedShops = useMemo(
    () => sortByPrefecturePopularity(shops, prefectureRank, (s) => s.prefecture),
    [shops, prefectureRank]
  );

  const productsById = useMemo(() => new Map(products.map((p) => [String(p.id), p])), [products]);

  // 「お気に入り店舗」は独立した機能ではなく、お気に入り商品を扱う店舗を
  // 自動的に導出する派生値(マイマップ用)。店舗側に専用のお気に入りボタンは置かない。
  const favoriteShops = useMemo(() => {
    const favoriteShopNames = new Set(
      products.filter((p) => isFavorite(p.id)).map((p) => p.shopName)
    );
    return shops.filter((s) => favoriteShopNames.has(s.name));
  }, [products, isFavorite, shops]);

  const favoriteShopNameSet = useMemo(
    () => new Set(favoriteShops.map((s) => s.name)),
    [favoriteShops]
  );
  const { alerts, dismissAlerts } = useAlerts(products, favoriteIds, favoriteShopNameSet, remoteLoaded);
  const [alertsPanelOpen, setAlertsPanelOpen] = useState(false);
  const [aboutOpen, setAboutOpen] = useState(false);

  const compareProducts = useMemo(
    () => compareIds.map((id) => productsById.get(id)).filter(Boolean),
    [compareIds, productsById]
  );

  const historyItems = useMemo(
    () =>
      history
        .map((entry) => ({ product: productsById.get(entry.id), viewedAt: entry.viewedAt }))
        .filter((entry) => entry.product),
    [history, productsById]
  );

  const openProductDetail = useCallback(
    (product) => {
      setDetailProduct(product);
      recordView(product.id);
    },
    [recordView]
  );

  const removeFilter = (dim, value) => {
    setFilters((prev) => {
      if (dim === "country" || dim === "prefecture") return { ...prev, [dim]: "" };
      const next = new Set(prev[dim]);
      next.delete(value);
      return { ...prev, [dim]: next };
    });
  };

  const activeChips = [
    ...(filters.country ? [{ dim: "country", v: filters.country }] : []),
    ...(filters.prefecture ? [{ dim: "prefecture", v: filters.prefecture }] : []),
    ...[...filters.flavorCategory].map((v) => ({ dim: "flavorCategory", v })),
  ];

  const openMapForProduct = useCallback(
    (product) =>
      setMapTarget({ shopName: product.shopName, shopAddress: product.shopAddress, mapQuery: product.mapQuery }),
    []
  );
  const openMapForShop = (shop) =>
    setMapTarget({ shopName: shop.name, shopAddress: shop.address, mapQuery: shop.mapQuery });
  const openMapForLocation = (location) =>
    setMapTarget({ shopName: location.label, shopAddress: location.address, mapQuery: location.mapQuery });

  // 著作権表示は広告・比較トレイの有無に関わらず常時表示するため、下部固定バー
  // 自体は常にレンダリングする。パディングは、著作権表示に加えて広告・比較
  // トレイがいくつ重なるかで変える。
  const compareTrayVisible = compareIds.length > 0;
  const adVisible = !isPremium;
  const bottomBarPadding =
    compareTrayVisible && adVisible ? "pb-[152px]" : compareTrayVisible || adVisible ? "pb-[104px]" : "pb-[48px]";

  return (
    <div className={`min-h-full bg-[#231810] text-[#F2E9DD] ${bottomBarPadding}`}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600&family=Inter:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');
        :root {
          --accent: #D4A24E;
          --accent-soft: #E8C89A;
          --accent-muted: #C9A876;
          --accent-label: #8B5E2E;
          --accent-glow: rgba(212, 162, 78, 0.35);
        }
        .font-serif { font-family: 'Fraunces', serif; }
        * { font-family: 'Inter', sans-serif; }
        .font-mono { font-family: 'IBM Plex Mono', monospace; }
      `}</style>

      <header className="px-5 pt-6 pb-3 border-b border-[#4A3A2A] sticky top-0 bg-[#231810]/95 backdrop-blur-sm z-10">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[11px] tracking-[0.2em] text-[var(--accent-label)] uppercase">
              Coffee Finder
            </p>
            <h1 className="font-serif text-[26px] leading-tight mt-1">
              近くの自家焙煎豆を探す
            </h1>
            <p className="text-[12px] text-[#8B7361] mt-0.5">Find Local Roasters Near You</p>
          </div>
          <div className="flex items-center shrink-0 mt-1">
            <button
              onClick={() => setAboutOpen(true)}
              className="p-1.5 text-[#B8A891] hover:text-[#F2E9DD] transition-colors"
              aria-label="このアプリについて"
            >
              <Info size={20} strokeWidth={1.75} />
            </button>
            <button
              onClick={() => setAlertsPanelOpen(true)}
              className="relative p-1.5 text-[#B8A891] hover:text-[#F2E9DD] transition-colors"
              aria-label="お知らせ"
            >
              <Bell size={20} strokeWidth={1.75} />
              {alerts.length > 0 && (
                <span className="absolute top-0.5 right-0.5 min-w-[16px] h-4 px-1 rounded-full bg-[var(--accent)] text-[#231810] text-[10px] font-bold flex items-center justify-center">
                  {alerts.length > 9 ? "9+" : alerts.length}
                </span>
              )}
            </button>
          </div>
        </div>

        <div className="flex gap-1 mt-4 p-1 rounded-full bg-[#3B2211] w-fit overflow-x-auto max-w-full">
          {TAB_ITEMS.map(({ id, icon: Icon, ja, en }) => (
            <button
              key={id}
              onClick={() => { setTab(id); setSelectedShop(null); }}
              className={`flex items-center gap-1.5 shrink-0 px-3.5 py-1.5 rounded-full transition-colors ${
                tab === id ? "bg-[var(--accent)] text-[#231810]" : "text-[#B8A891]"
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
            {displayed.length}件の商品(産地・精選方法・グレードで正規化済み)
          </p>
          <div className="flex items-center gap-1.5 mt-3 overflow-x-auto scrollbar-hide">
            {SORT_MODE_ITEMS.map(({ id, label, icon: Icon }) => {
              // 「近い順」は、実際に距離順ソートが有効な(位置情報取得に成功した)
              // 場合のみ選択状態にする。許可待ち・拒否・エラー中は、実際には
              // 距離順になっていないため、どのボタンも選択していない状態にする。
              const isActive = id === "distance" ? sortMode === id && geolocation.status === "success" : sortMode === id;
              return (
                <button
                  key={id}
                  onClick={() => setSortMode(id)}
                  aria-pressed={isActive}
                  className={`flex items-center gap-1 shrink-0 text-[12px] px-3 py-1.5 rounded-full border transition-colors ${
                    isActive
                      ? "bg-[var(--accent)] text-[#231810] border-[var(--accent)]"
                      : "border-[#4A3A2A] text-[#B8A891]"
                  }`}
                >
                  <Icon size={12} strokeWidth={2} />
                  {label}
                </button>
              );
            })}
          </div>
          {sortMode === "distance" && geolocation.status !== "success" && (
            <div className="flex items-start gap-1 text-[11px] text-[#8B7361] mt-1.5">
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
            <p className="text-[11px] text-[#8B7361] mt-1.5">
              {favoriteArea.prefecture
                ? `登録エリア: ${favoriteArea.prefecture}${favoriteArea.city ? ` ${favoriteArea.city}` : ""}(マイページで変更できます)`
                : "登録エリアが未登録です(マイページで登録できます)"}
            </p>
          )}
          {sortMode === "random" && (
            <p className="text-[11px] text-[#8B7361] mt-1.5">
              表示範囲: {displayRadiusOptions.find((o) => o.id === displayRadiusId)?.label}
              (マイページで変更できます)
            </p>
          )}
          <div className="relative mt-3">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#8B7361]" strokeWidth={2} />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="商品名・産地・銘柄・店舗名・住所で検索"
              className="w-full pl-9 pr-9 py-2.5 rounded-xl bg-[#2F241A] border border-[#4A3A2A] text-[13px] text-[#F2E9DD] placeholder:text-[#8B7361] focus:outline-none focus:border-[var(--accent-label)]"
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
              className="flex items-center gap-1.5 shrink-0 text-[13px] px-3.5 py-1.5 rounded-full border border-[var(--accent-label)] text-[var(--accent)] hover:bg-[#3B2211] transition-colors"
            >
              <SlidersHorizontal size={13} strokeWidth={2} />
              絞り込み
              {activeCount > 0 && (
                <span className="ml-0.5 text-[11px] bg-[var(--accent)] text-[#231810] rounded-full w-4 h-4 flex items-center justify-center font-medium">
                  {activeCount}
                </span>
              )}
            </button>
            <div className="flex gap-1.5 overflow-x-auto pb-1 scrollbar-hide">
              {activeChips.map(({ dim, v }) => (
                <button
                  key={`${dim}-${v}`}
                  onClick={() => removeFilter(dim, v)}
                  className="shrink-0 flex items-center gap-1 text-[12px] pl-2.5 pr-1.5 py-1 rounded-full bg-[#3B2211] text-[var(--accent-muted)] border border-[#4A3A2A]"
                >
                  {v}
                  <X size={11} />
                </button>
              ))}
            </div>
          </div>
          <label className="flex items-center gap-1.5 mt-2.5 text-[12px] text-[#8B7361] cursor-pointer select-none w-fit">
            <input
              type="checkbox"
              checked={showOutOfStock}
              onChange={(e) => setShowOutOfStock(e.target.checked)}
              className="accent-[var(--accent)] w-3.5 h-3.5"
            />
            売り切れ商品も表示
          </label>
        </div>
      )}

      {tab === "products" && (
        <main className="px-5 py-5 max-w-xl mx-auto">
          <div className="mb-3">
            <DiscoveryFactCard />
          </div>
          {displayed.length === 0 ? (
            <div className="text-center py-16 text-[#8B7361]">
              <Coffee size={28} className="mx-auto mb-3 opacity-40" />
              {filtered.length === 0 ? (
                <p className="text-[14px]">該当する商品が見つかりませんでした</p>
              ) : sortMode === "random" ? (
                <p className="text-[14px]">この範囲には商品がありません。表示範囲を広げてみてください</p>
              ) : sortMode === "favoriteArea" ? (
                <p className="text-[14px]">
                  {favoriteArea.prefecture
                    ? "登録したエリアには該当する商品がありません。マイページでエリアを変更してみてください"
                    : "マイページで登録エリア(都道府県・市区町村)を登録してください"}
                </p>
              ) : (
                <p className="text-[14px]">現在30日以内に新規掲載された商品はありません</p>
              )}
            </div>
          ) : (
            // 商品数が数千件規模になっても軽く保つため、画面内(+前後バッファ)分
            // だけをDOMに描画する仮想スクロールを使う。ページ全体がスクロール
            // する構成(専用のスクロールコンテナが無い)ため useWindowScroll を使う。
            <Virtuoso
              useWindowScroll
              data={displayed}
              computeItemKey={(_, product) => product.id}
              itemContent={(_, product) => (
                <div className="pb-3">
                  <ProductCard
                    product={product}
                    onOpenMap={openMapForProduct}
                    onLearnOrigin={learnAboutOrigin}
                    isFavorite={isFavorite}
                    onToggleFavorite={toggleFavorite}
                    onOpenDetail={openProductDetail}
                  />
                </div>
              )}
            />
          )}
        </main>
      )}

      {tab === "favorites" && (
        <FavoritesTabView
          products={products}
          isFavorite={isFavorite}
          onToggleFavorite={toggleFavorite}
          onOpenMap={openMapForProduct}
          onLearnOrigin={learnAboutOrigin}
          onOpenDetail={openProductDetail}
          favoriteShops={favoriteShops}
        />
      )}

      {tab === "shops" && !selectedShop && (
        <ShopListView shops={sortedShops} productsByShop={productsByShop} onSelectShop={setSelectedShop} />
      )}

      {tab === "shops" && selectedShop && (
        <ShopDetailView
          shop={selectedShop}
          products={productsByShop[selectedShop.name] || []}
          onBack={() => setSelectedShop(null)}
          onOpenMap={() => openMapForShop(selectedShop)}
          onOpenLocationMap={openMapForLocation}
          isFavorite={isFavorite}
          onToggleFavorite={toggleFavorite}
          onOpenDetail={openProductDetail}
        />
      )}

      {tab === "guide" && (
        <BuyingGuideView pendingOriginCountry={pendingOriginCountry} onViewProducts={viewProductsForCountry} />
      )}
      {tab === "trivia" && <TriviaView onLearnOrigin={learnAboutOrigin} events={events} />}

      {tab === "mypage" && (
        <MyPageView
          themeId={themeId}
          setThemeId={setThemeId}
          themes={themes}
          isPremium={isPremium}
          setPremium={setPremium}
          favoriteIds={favoriteIds}
          importFavorites={importFavorites}
          historyItems={historyItems}
          products={products}
          getRating={getRating}
          onOpenDetail={openProductDetail}
          displayRadiusId={displayRadiusId}
          setDisplayRadiusId={setDisplayRadiusId}
          displayRadiusOptions={displayRadiusOptions}
          favoriteArea={favoriteArea}
          setFavoriteAreaPrefecture={setFavoriteAreaPrefecture}
          setFavoriteAreaCity={setFavoriteAreaCity}
        />
      )}

      <FilterSheet
        open={sheetOpen}
        onClose={() => setSheetOpen(false)}
        filters={filters}
        setFilters={setFilters}
        resultCount={filtered.length}
        prefectureOptions={prefectureOptions}
        favoriteAreaPrefecture={favoriteArea.prefecture}
      />
      <MapLinkModal target={mapTarget} onClose={() => setMapTarget(null)} />
      <ProductDetailModal
        product={detailProduct}
        onClose={() => setDetailProduct(null)}
        onOpenMap={openMapForProduct}
        isFavorite={isFavorite}
        onToggleFavorite={toggleFavorite}
        isComparing={isComparing}
        onToggleCompare={toggleCompare}
        rating={detailProduct ? getRating(detailProduct.id) : 0}
        onRate={setRating}
        logCount={detailProduct ? getLogs(detailProduct.id).length : 0}
        onOpenTastingLog={setTastingLogProduct}
      />
      <TastingLogModal
        product={tastingLogProduct}
        logs={tastingLogProduct ? getLogs(tastingLogProduct.id) : []}
        onAddLog={(entry) => addLog(tastingLogProduct.id, entry)}
        onDeleteLog={(entryId) => deleteLog(tastingLogProduct.id, entryId)}
        onClose={() => setTastingLogProduct(null)}
      />
      {compareModalOpen && (
        <ComparisonModal
          products={compareProducts}
          onClose={() => setCompareModalOpen(false)}
          onRemove={removeFromCompare}
          onClearAll={() => {
            clearCompare();
            setCompareModalOpen(false);
          }}
          isPremium={isPremium}
          limit={compareLimit}
        />
      )}
      <Toast message={toastMessage} onDismiss={dismissToast} />
      <AlertsPanel
        open={alertsPanelOpen}
        alerts={alerts}
        products={products}
        onOpenDetail={(product) => {
          setAlertsPanelOpen(false);
          dismissAlerts();
          openProductDetail(product);
        }}
        onClose={() => {
          setAlertsPanelOpen(false);
          dismissAlerts();
        }}
      />
      <AboutView open={aboutOpen} onClose={() => setAboutOpen(false)} />

      <div className="fixed bottom-0 inset-x-0 z-20 bg-[#1C140D]/95 backdrop-blur-sm">
        {compareTrayVisible && (
          <CompareTray
            count={compareIds.length}
            limit={compareLimit}
            isPremium={isPremium}
            onOpen={() => setCompareModalOpen(true)}
          />
        )}
        {adVisible && <AdBannerPlaceholder />}
        <CopyrightFooter />
      </div>
    </div>
  );
}
