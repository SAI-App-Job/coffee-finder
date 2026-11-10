import { useState, useMemo, useEffect, useCallback, useRef } from "react";
import { Virtuoso } from "react-virtuoso";
import { Search, X, SlidersHorizontal, Coffee, MapPin, Sparkles, Shuffle, LocateFixed, Heart } from "lucide-react";
import { MOCK_PRODUCTS } from "./data/products";
import { SHOPS } from "./data/shops";
import { EVENTS } from "./data/events";
import { TRIVIA_SUB_TABS } from "./data/navigation";
import { ORIGIN_GUIDE } from "./data/originGuide";
import { analyzeFlavorNotes } from "./utils/flavor";
import { loadRemoteData } from "./data/remote";
import { sortByDistance, sortNewArrivalsFirst, sortByRecency, pickRandomDisplaySet, filterByFavoriteArea, shuffle, sortShopsByDistance, filterShopsByFavoriteArea } from "./utils/productSort";
import { buildPrefectureRank, sortByPrefecturePopularity } from "./utils/prefectureOrder";
import { useFavorites } from "./hooks/useFavorites";
import { useColorTheme } from "./hooks/useColorTheme";
import { usePremium } from "./hooks/usePremium";
import { useToast } from "./hooks/useToast";
import { useViewHistory } from "./hooks/useViewHistory";
import { useComparison } from "./hooks/useComparison";
import { useRatings } from "./hooks/useRatings";
import { useTastingLog } from "./hooks/useTastingLog";
import { useProductPhotos } from "./hooks/useProductPhotos";
import { buildSampleCollection, isSampleId, renderSamplePackage } from "./data/sampleCollection";
import { useUserCollection } from "./hooks/useUserCollection";
import { useMyTools } from "./hooks/useMyTools";
import { useShopTastingNotes } from "./hooks/useShopTastingNotes";
import { useAlerts } from "./hooks/useAlerts";
import { useGeolocation } from "./hooks/useGeolocation";
import { useDisplayRadius } from "./hooks/useDisplayRadius";
import { useFavoriteArea } from "./hooks/useFavoriteArea";
import { ProductCard, DiscoveryFactCard } from "./components/ProductCard";
import { ProductDetailModal } from "./components/ProductDetailModal";
import { TastingLogModal } from "./components/TastingLogModal";
import { ShopTastingNoteModal } from "./components/ShopTastingNoteModal";
import { AlertsPanel } from "./components/AlertsPanel";
import { AboutView } from "./components/AboutView";
import { FilterSheet } from "./components/FilterSheet";
import { ShopListView, ShopDetailView } from "./components/ShopViews";
import { CollectionView } from "./components/CollectionView";
import { UserShopFormModal } from "./components/UserShopFormModal";
import { UserShopPickerModal } from "./components/UserShopPickerModal";
import { UserProductFormModal } from "./components/UserProductFormModal";
import { BuyingGuideView } from "./components/BuyingGuideView";
import { TriviaView } from "./components/TriviaView";
import { SettingsView } from "./components/SettingsView";
import { DiaryView } from "./components/DiaryView";
import { AchievementsView } from "./components/AchievementsView";
import { buildDiaryEvents } from "./utils/diary";
import { achievementParams } from "./utils/achievements";
import { useAchievements } from "./hooks/useAchievements";
import { AppNavigationContext } from "./hooks/useAppNavigation";
import { BottomNav } from "./components/BottomNav";
import { AdBannerPlaceholder } from "./components/AdBanner";
import { CompareTray, ComparisonModal } from "./components/Compare";
import { CopyrightFooter, MapLinkModal, Toast, JaOnlyNote } from "./components/common";
import { Trans, getLang, useT } from "./i18n";

const SORT_MODE_ITEMS = [
  { id: "distance", label: "近い順", icon: MapPin },
  { id: "favoriteArea", label: "登録エリア", icon: Heart },
  { id: "new", label: "新規掲載", icon: Sparkles },
  { id: "random", label: "ランダム", icon: Shuffle },
];

export default function CoffeeProductList() {
  const t = useT();
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

  const { themeId, setThemeId, themes } = useColorTheme();
  const { isPremium, setPremium } = usePremium();
  const { message: toastMessage, showToast, dismissToast } = useToast();
  const { favoriteIds, favoriteDates, isFavorite, toggleFavorite, importFavorites } = useFavorites(isPremium, showToast);
  const { history, recordView } = useViewHistory(isPremium);
  const {
    compareIds,
    isComparing,
    toggleCompare,
    removeFromCompare,
    clearCompare,
    limit: compareLimit,
  } = useComparison(isPremium, showToast);
  const { ratings, getRating, setRating } = useRatings();
  const { logsByProduct, getLogs, addLog, deleteLog, clearLogs } = useTastingLog();
  const userCollection = useUserCollection();
  const myTools = useMyTools();
  // 商品のパッケージ写真(端末内のIndexedDBに保存。商品IDがキー)
  const {
    getPhotoUrl,
    setPhoto,
    removePhoto,
    removePhotos,
    photoIds,
    photoDates,
    photoCount,
    exportPhotos,
    getPhotoBytes,
    importPhotos,
  } = useProductPhotos();
  // コレクションの「登録した商品」: 店舗フォーム({}=新規 / {shop}=編集)と商品フォーム({shop, product?})
  const [userShopPickerOpen, setUserShopPickerOpen] = useState(false);
  const [userShopForm, setUserShopForm] = useState(null);
  const [userProductForm, setUserProductForm] = useState(null);
  const { notesByShop, getNotes: getShopNotes, addNote: addShopNote, deleteNote: deleteShopNote } = useShopTastingNotes();
  const [noteFormShop, setNoteFormShop] = useState(null);

  // いま開いている画面。下部メニュー(BottomNav)から切り替える。
  // "products" | "shops" | "guide" | "collection" | "diary" | "achievements" | "settings" | "trivia"
  const [tab, setTab] = useState("products");
  const [triviaSub, setTriviaSub] = useState(TRIVIA_SUB_TABS[0].id);
  const [detailProduct, setDetailProduct] = useState(null);
  const [tastingLogProduct, setTastingLogProduct] = useState(null);
  const [compareModalOpen, setCompareModalOpen] = useState(false);
  // country/prefectureは単一選択のプルダウンのため空文字列("")が未選択を表す。
  // flavor(風味の大分類・詳細分類。どちらも名前をそのまま入れる)のみ複数選択(チップ)のままなのでSetで持つ。焙煎度フィルタは
  // 実データではほぼ機能しない(roastSelectable商品が62.5%を占め、どの焙煎度を
  // 選んでも同じ結果になっていた)ため廃止した。
  const [filters, setFilters] = useState({
    country: "",
    prefecture: "",
    flavor: new Set(),
    // 自分がつけた★評価の下限(0=指定なし、1〜5=★N以上)
    minRating: 0,
  });
  const [sheetOpen, setSheetOpen] = useState(false);
  const [mapTarget, setMapTarget] = useState(null);
  const [selectedShop, setSelectedShop] = useState(null);
  const [pendingOriginCountry, setPendingOriginCountry] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [showOutOfStock, setShowOutOfStock] = useState(false);

  // 商品タブの並べ替え軸。"distance"(近い順、初期表示)|"new"(新規掲載)|
  // "random"(ランダム)。端末内のセッション状態としてのみ保持し(再読み込みで
  // "distance"に戻る)、"random"の表示範囲設定のみ設定で永続化する。
  const [sortMode, setSortMode] = useState("distance");
  // 店舗タブの並べ替え軸。商品タブと違い「新規掲載」「ランダム」は対象外
  // (店舗自体に新着・ランダム表示の概念が無いため)、"distance"|"favoriteArea"|
  // "default"(登録店舗数が多い都道府県順)の3種のみ。
  const [shopSortMode, setShopSortMode] = useState("distance");
  const geolocation = useGeolocation();
  const { displayRadiusId, setDisplayRadiusId, options: displayRadiusOptions } = useDisplayRadius();
  const { favoriteArea, setPrefecture: setFavoriteAreaPrefecture, setCity: setFavoriteAreaCity } = useFavoriteArea();
  // ランダム表示のシャッフル順は、無関係な再描画(お気に入り操作等)では
  // 変えたくないため、絞り込み結果や設定が実際に変わった時だけ再計算する。
  // 「ランダム」ボタンを選択中に再タップした時だけ増分し、displayedのuseMemoの
  // 依存配列に含めることで、絞り込み条件を変えずに明示的な再シャッフルを可能にする。
  const [randomNonce, setRandomNonce] = useState(0);

  // 「登録エリア」「新規掲載」は、選択中に同じボタンを再タップすると全件表示
  // ("distance"、位置情報未取得時は都道府県順の全件)に戻す(=トグル式)。
  // 「ランダム」は再タップのたびに再シャッフルする。「近い順」はトグル対象外。
  const handleSortModeClick = (id) => {
    if (id === "random") {
      setSortMode("random");
      setRandomNonce((n) => n + 1);
      return;
    }
    if (id === "favoriteArea" || id === "new") {
      setSortMode((prev) => (prev === id ? "distance" : id));
      return;
    }
    setSortMode(id);
  };

  // 店舗タブの「登録エリア」も同様に、再タップで全件表示("distance")に戻す
  // トグル式にする。
  const handleShopSortModeClick = (id) => {
    if (id === "favoriteArea") {
      setShopSortMode((prev) => (prev === id ? "distance" : id));
      return;
    }
    setShopSortMode(id);
  };

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
        showToast(t("この産地の情報は準備中です"));
        return;
      }
      setPendingOriginCountry(country);
      setTab("guide");
      // タブ切り替えはページ遷移ではないため、直前のタブでのスクロール位置が
      // そのまま引き継がれてしまう。産地タブの先頭(国名見出し)が隠れて見えなく
      // なる不具合になっていたため、ジャンプ時は明示的に先頭へ戻す。
      window.scrollTo({ top: 0 });
    },
    [showToast, t]
  );

  // 下部メニューからの画面移動。店舗詳細は開いたままにせず、移動先の先頭から表示する。
  const navigateTo = useCallback(({ page, sub }) => {
    setTab(page);
    if (page === "trivia" && sub) setTriviaSub(sub);
    setSelectedShop(null);
    window.scrollTo({ top: 0 });
  }, []);

  const viewProductsForCountry = (country) => {
    setSearchQuery("");
    setFilters({
      country,
      prefecture: "",
      flavor: new Set(),
      minRating: 0,
    });
    setSelectedShop(null);
    setTab("products");
  };

  const activeCount =
    (filters.country ? 1 : 0) +
    (filters.prefecture ? 1 : 0) +
    filters.flavor.size +
    (filters.minRating ? 1 : 0);

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
      if (filters.minRating && getRating(p.id) < filters.minRating) return false;
      if (filters.flavor.size) {
        // 大分類(カテゴリ名)・詳細分類(語)のどれかに該当すればヒット
        const analysis = analyzeFlavorNotes(p.flavorNotes);
        const hasMatch =
          analysis.categories.some((c) => filters.flavor.has(c.ja)) || analysis.terms.some((x) => filters.flavor.has(x.ja));
        if (!hasMatch) return false;
      }
      if (q) {
        const blendCountries = p.blendComponents?.length
          ? p.blendComponents.map((c) => c.originCountry)
          : [];
        const haystack = [
          p.rawName, p.originCountry, p.designatedBrand, p.processingMethod,
          p.grade, p.farmNote, p.shopName, p.shopAddress, p.prefecture,
          p.nearestStation,
          ...blendCountries,
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        if (!haystack.includes(q)) return false;
      }
      return true;
    });
  }, [products, filters, searchQuery, showOutOfStock, getRating]);

  // 並べ替え軸ごとの表示リスト。
  // - "distance": 位置情報の取得に成功していれば距離順。許可待ち・タイムアウト・
  //   拒否・非対応の間は「近い順」を騙らず、登録店舗数が多い都道府県順(東京都
  //   から)の全件表示にする(このボタンもその間は非選択状態にする。取得成功時
  //   に自動で距離順へ切り替わり、拒否時に自動再試行はしない)。
  // - "favoriteArea": 設定で手動登録した都道府県・市区町村(住所文字列の
  //   部分一致)に該当する商品のみ、新しい順に表示。郵便番号やジオコーディング
  //   は使わない(店舗網羅率が市区町村単位でも疎らなため、登録は手入力とし、
  //   0件になる場合は設定での再登録を促す)。
  // - "new": 新規掲載(30日以内)のみを対象に新しい順。表示範囲は全国固定。
  // - "random": 設定の表示範囲に応じた範囲内からランダムに表示。
  const displayed = useMemo(() => {
    if (sortMode === "favoriteArea") {
      // 都道府県が未登録の間は絞り込みようがないため、全国表示にフォール
      // バックせず空にする(設定での登録を促す)。
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
    // randomNonceは値自体を使わないが、「ランダム」再タップ時に明示的に
    // 再シャッフルさせるためだけに依存配列に含めている。
  }, [filtered, sortMode, geolocation.status, geolocation.coords, displayRadiusId, favoriteArea, prefectureRank, randomNonce]);

  const productsByShop = useMemo(() => {
    const map = {};
    products.forEach((p) => {
      map[p.shopName] = map[p.shopName] || [];
      map[p.shopName].push(p);
    });
    return map;
  }, [products]);

  // 店舗一覧のデフォルト表示順(登録店舗数が多い都道府県順、東京都から)。
  // 位置情報未取得時の「近い順」フォールバック、および「登録エリア」選択時の
  // 並び順にも流用する。
  const sortedShops = useMemo(
    () => sortByPrefecturePopularity(shops, prefectureRank, (s) => s.prefecture),
    [shops, prefectureRank]
  );

  // 店舗タブの表示リスト。商品タブのdisplayedと同じ考え方で、
  // - "distance": 位置情報取得に成功していれば店舗自身のlat/lngで距離順。
  //   失敗・未取得の間はデフォルト順にフォールバックする。
  // - "favoriteArea": 設定の登録エリアに該当する店舗のみ(デフォルト順)。
  //   都道府県が未登録の間は0件にする(商品タブと同じ方針)。
  const displayedShops = useMemo(() => {
    if (shopSortMode === "favoriteArea") {
      if (!favoriteArea.prefecture) return [];
      return filterShopsByFavoriteArea(sortedShops, favoriteArea);
    }
    if (shopSortMode === "distance" && geolocation.status === "success") {
      return sortShopsByDistance(shops, geolocation.coords);
    }
    return sortedShops;
  }, [shops, sortedShops, shopSortMode, geolocation.status, geolocation.coords, favoriteArea]);

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
      if (dim === "minRating") return { ...prev, minRating: 0 };
      const next = new Set(prev[dim]);
      next.delete(value);
      return { ...prev, [dim]: next };
    });
  };

  const activeChips = [
    ...(filters.country ? [{ dim: "country", v: filters.country }] : []),
    ...(filters.prefecture ? [{ dim: "prefecture", v: filters.prefecture }] : []),
    ...[...filters.flavor].map((v) => ({ dim: "flavor", v })),
    ...(filters.minRating ? [{ dim: "minRating", v: t("★{n}以上", { n: filters.minRating }) }] : []),
  ];

  const openMapForProduct = useCallback(
    (product) =>
      setMapTarget({ shopName: product.shopName, shopAddress: product.shopAddress, mapQuery: product.mapQuery }),
    []
  );
  // 店舗フォームの候補(アプリに収録済みの店舗。選ぶと住所が自動で入る)
  const appShopSuggestions = useMemo(
    () => shops.map((s) => ({ name: s.name, address: s.address ?? "" })),
    [shops]
  );

  // 新規の店舗を登録したら、続けてその店舗の商品登録フォームを開く(店舗 → 商品の流れ)
  const saveUserShop = (data, editing) => {
    if (editing) {
      userCollection.updateShop(editing.id, data);
      setUserShopForm(null);
      return;
    }
    const id = userCollection.addShop(data);
    setUserShopForm(null);
    if (id) setUserProductForm({ shop: { id, ...data } });
  };

  // アプリ掲載店はまだ登録先(店舗の記録)が無いことがあるので、保存するときに探して、無ければ作る
  // photoChange: undefined=写真は変更なし / Blob=新しい写真 / null=写真を削除
  const saveUserProduct = async (data, shop, editing, photoChange) => {
    const productId = editing
      ? (userCollection.updateProduct(editing.id, data), editing.id)
      : userCollection.addProduct(shop.id ?? userCollection.findOrCreateAppShop(shop), data);
    setUserProductForm(null);
    if (!productId || photoChange === undefined) return;
    if (photoChange === null) removePhoto(productId);
    else if (!(await setPhoto(productId, photoChange))) showToast(t("商品は登録しましたが、写真を保存できませんでした"));
  };

  // 商品登録の最初のステップ「どのお店?」の選択結果 → 商品フォームを開く
  const pickAppShopForProduct = (appShop) => {
    const linked = userCollection.userShops.find((s) => s.appShopName === appShop.name);
    setUserShopPickerOpen(false);
    setUserProductForm({
      shop: linked ?? { name: appShop.name, address: appShop.address, appShopName: appShop.name },
    });
  };
  const pickUserShopForProduct = (shop) => {
    setUserShopPickerOpen(false);
    setUserProductForm({ shop });
  };

  // 削除した商品の評価(★)も一緒に消す。テイスティングログは履歴として端末に残る。
  // (サンプルの商品だけは、使い方を見せるためのデータなので、ログも一緒に消す)
  const deleteUserShop = (shopId) => {
    const removedIds = userCollection.deleteShop(shopId);
    removedIds.forEach((productId) => setRating(productId, 0));
    removePhotos(removedIds);
    clearLogs(removedIds.filter(isSampleId));
  };
  const deleteUserProduct = (productId) => {
    userCollection.deleteProduct(productId);
    setRating(productId, 0);
    removePhoto(productId);
    if (isSampleId(productId)) clearLogs([productId]);
  };

  // 「登録した商品」のサンプル(架空の店舗・商品+パッケージ写真・★評価・テイスティングログ)
  const hasSamples = userCollection.userShops.some((s) => isSampleId(s.id));
  const addSamples = async () => {
    if (hasSamples) return;
    const sample = buildSampleCollection(new Date(), getLang());
    userCollection.importCollection({ shops: sample.shops, products: sample.products });
    Object.entries(sample.ratings).forEach(([id, stars]) => setRating(id, stars));
    Object.entries(sample.logs).forEach(([id, entries]) => {
      // 削除したサンプルのログが残っていても、同じものを重複して入れない
      const existing = new Set(getLogs(id).map((l) => l.id));
      entries.filter((l) => !existing.has(l.id)).forEach((l) => addLog(id, l));
    });
    // 写真はその場で描く。失敗しても、商品などは登録済みのままにする
    const results = await Promise.all(
      sample.products.map(async (p) => {
        try {
          return await setPhoto(p.id, await renderSamplePackage(p.id, getLang()));
        } catch {
          return false;
        }
      })
    );
    if (results.some((ok) => ok === false)) showToast(t("サンプルの写真を一部作成できませんでした"));
  };
  const removeSamples = () => {
    userCollection.userShops.filter((s) => isSampleId(s.id)).forEach((s) => deleteUserShop(s.id));
  };

  // 店舗画面の「店頭の商品(手動登録)」: 選んだアプリ掲載店に紐づく、手動登録した商品
  const linkedUserShop = selectedShop
    ? userCollection.userShops.find((s) => s.appShopName === selectedShop.name)
    : undefined;
  const registeredForSelectedShop = selectedShop && {
    products: linkedUserShop ? userCollection.userProducts.filter((p) => p.shopId === linkedUserShop.id) : [],
    onRegister: () =>
      setUserProductForm({
        shop: linkedUserShop ?? {
          name: selectedShop.name,
          address: selectedShop.address ?? "",
          appShopName: selectedShop.name,
        },
      }),
    onEdit: (product) => setUserProductForm({ shop: linkedUserShop, product }),
    onDelete: deleteUserProduct,
    getPhotoUrl,
    getRating,
    onRate: setRating,
    getLogCount: (id) => getLogs(id).length,
    onOpenTastingLog: (product) => setTastingLogProduct({ id: product.id, rawName: product.name }),
  };

  // コーヒー日記・実績の元になる記録(ログ・ノート・商品登録・写真)と、★評価の時刻
  const shopsByName = useMemo(() => new Map(shops.map((s) => [s.name, s])), [shops]);
  const diaryEvents = useMemo(
    () =>
      buildDiaryEvents({
        logsByProduct,
        notesByShop,
        userProducts: userCollection.userProducts,
        userShops: userCollection.userShops,
        photoIds,
        photoDates,
        productsById,
        shopsByName,
      }),
    [logsByProduct, notesByShop, userCollection.userProducts, userCollection.userShops, photoIds, photoDates, productsById, shopsByName]
  );
  const ratingTimes = useMemo(
    () =>
      Object.entries(ratings)
        .filter(([id]) => !isSampleId(id))
        .map(([, r]) => Date.parse(r.ratedAt))
        .filter((t0) => !Number.isNaN(t0)),
    [ratings]
  );
  const achievements = useAchievements({ events: diaryEvents, ratingTimes });
  const { freshItems, consumeFresh } = achievements;
  useEffect(() => {
    if (freshItems.length === 0) return;
    const name = (item) => t(item.title, achievementParams(item));
    showToast(
      freshItems.length === 1
        ? t("実績を獲得しました: {title}", { title: name(freshItems[0]) })
        : t("実績を獲得しました: {title} ほか{n}件", { title: name(freshItems[0]), n: freshItems.length - 1 })
    );
    consumeFresh();
  }, [freshItems, consumeFresh, showToast, t]);

  // 「ディスプレイ」: パッケージ写真のある豆(手動登録した商品+アプリの商品)。新しい写真が先頭
  const shelfItems = useMemo(() => {
    const userById = new Map(userCollection.userProducts.map((p) => [p.id, p]));
    const items = [];
    for (const id of photoIds) {
      const url = getPhotoUrl(id);
      if (!url) continue;
      const user = userById.get(id);
      if (user) {
        items.push({ id, kind: "user", name: user.name, url, rating: getRating(id), t: Date.parse(photoDates[id] ?? user.createdAt) || 0 });
        continue;
      }
      const product = productsById.get(String(id));
      if (product) items.push({ id, kind: "app", name: product.rawName, url, rating: getRating(id), t: Date.parse(photoDates[id] ?? "") || 0, product });
    }
    return items.sort((a, b) => b.t - a.t);
  }, [photoIds, photoDates, getPhotoUrl, getRating, userCollection.userProducts, productsById]);
  const openShelfItem = (item) =>
    item.kind === "user" ? setTastingLogProduct({ id: item.id, rawName: item.name }) : openProductDetail(item.product);

  // 手動登録した店舗: 店舗名+住所でGoogleマップを検索する(座標は持たないため)
  const openMapForUserShop = (shop) =>
    setMapTarget({
      shopName: shop.name,
      shopAddress: shop.address,
      mapQuery: `${shop.name} ${shop.address}`.trim(),
    });
  const openMapForShop = (shop) =>
    setMapTarget({ shopName: shop.name, shopAddress: shop.address, mapQuery: shop.mapQuery });
  const openMapForLocation = (location) =>
    setMapTarget({ shopName: location.label, shopAddress: location.address, mapQuery: location.mapQuery });

  // 下部固定バーは、メインメニュー(タブバー)と著作権表示を常に表示し、その上に
  // 比較トレイが条件つきで重なる。段数で高さが変わる(安全領域の余白も加わる)ため、
  // 実際の高さを測って、ページ末尾が固定バーに隠れないよう下余白に反映する。
  // 広告はメニューの誤タップを避けるため、下部ではなくページ最上部に置く。
  const compareTrayVisible = compareIds.length > 0;
  const adVisible = !isPremium;
  const bottomBarRef = useRef(null);
  const [bottomBarHeight, setBottomBarHeight] = useState(140);
  useEffect(() => {
    const el = bottomBarRef.current;
    if (!el) return;
    const update = () => setBottomBarHeight(el.offsetHeight);
    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <AppNavigationContext.Provider value={navigateTo}>
    <div className="min-h-full bg-[var(--c-bg)] text-[var(--c-text)]" style={{ paddingBottom: bottomBarHeight }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600&family=Inter:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');
        .font-serif { font-family: 'Fraunces', serif; }
        * { font-family: 'Inter', sans-serif; }
        .font-mono { font-family: 'IBM Plex Mono', monospace; }
      `}</style>

      {/* 広告: ページ最上部。固定せず、スクロールで流れる(直後のヘッダーは上に固定される)。 */}
      {adVisible && <AdBannerPlaceholder />}

      <header className="px-5 pt-6 pb-3 border-b border-[var(--c-border)] sticky top-0 bg-[var(--c-bg)]/95 backdrop-blur-sm z-10">
        <p className="text-[11px] tracking-[0.2em] text-[var(--accent-label)] uppercase">Coffee Finder</p>
        <h1 className="font-serif text-[26px] leading-tight mt-1 text-balance">{t("近くの自家焙煎豆を探す")}</h1>
        {getLang() === "ja" && <p className="text-[12px] text-[var(--c-text-3)] mt-0.5">Find Local Roasters Near You</p>}
      </header>

      {tab === "products" && !selectedShop && (
        <div className="px-5 pt-4 max-w-xl mx-auto">
          <JaOnlyNote className="mb-1.5" />
          <p className="text-[13px] text-[var(--c-text-3)]">
            {t("{n}件の商品(産地・精選方法・グレードで正規化済み)", { n: displayed.length })}
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
                  onClick={() => handleSortModeClick(id)}
                  aria-pressed={isActive}
                  className={`flex items-center gap-1 shrink-0 text-[12px] px-3 py-1.5 rounded-full border transition-colors ${
                    isActive
                      ? "bg-[var(--accent)] text-[var(--on-accent)] border-[var(--accent)]"
                      : "border-[var(--c-border)] text-[var(--c-text-2)]"
                  }`}
                >
                  <Icon size={12} strokeWidth={2} />
                  {t(label)}
                </button>
              );
            })}
          </div>
          {sortMode === "distance" && geolocation.status !== "success" && (
            <div className="flex items-start gap-1 text-[11px] text-[var(--c-text-3)] mt-1.5">
              <LocateFixed size={11} strokeWidth={1.75} className="shrink-0 mt-0.5" />
              <p>
                {geolocation.status === "pending" && t("位置情報を取得中です(取得できるまで全件表示しています)")}
                {geolocation.status === "denied" && (
                  <Trans
                    k="位置情報が許可されていないため、全件表示しています。ブラウザの拒否設定はアプリからは解除できないため、ブラウザのアドレスバー付近のアイコンから位置情報の許可を変更したうえで、{retry}してください"
                    values={{
                      retry: (
                        <button onClick={geolocation.retry} className="text-[var(--accent)] underline underline-offset-2">
                          {t("再試行")}
                        </button>
                      ),
                    }}
                  />
                )}
                {geolocation.status === "error" && (
                  <Trans
                    k="位置情報を取得できなかったため、全件表示しています。{retry}"
                    values={{
                      retry: (
                        <button onClick={geolocation.retry} className="text-[var(--accent)] underline underline-offset-2">
                          {t("位置情報を取得")}
                        </button>
                      ),
                    }}
                  />
                )}
                {geolocation.status === "unsupported" &&
                  t("この端末・ブラウザは位置情報に対応していないため、全件表示しています")}
              </p>
            </div>
          )}
          {sortMode === "favoriteArea" && (
            <p className="text-[11px] text-[var(--c-text-3)] mt-1.5">
              {favoriteArea.prefecture
                ? t("登録エリア: {area}(設定で変更できます)", {
                    area: `${t(favoriteArea.prefecture)}${favoriteArea.city ? ` ${favoriteArea.city}` : ""}`,
                  })
                : t("登録エリアが未登録です(設定で登録できます)")}
            </p>
          )}
          {sortMode === "random" && (
            <p className="text-[11px] text-[var(--c-text-3)] mt-1.5">
              {t("表示範囲: {label}(設定で変更できます)", {
                label: t(displayRadiusOptions.find((o) => o.id === displayRadiusId)?.label ?? ""),
              })}
            </p>
          )}
          <div className="relative mt-3">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--c-text-3)]" strokeWidth={2} />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t("商品名・産地・銘柄・店舗名・住所・駅名で検索")}
              className="w-full pl-9 pr-9 py-2.5 rounded-xl bg-[var(--c-surface)] border border-[var(--c-border)] text-[13px] text-[var(--c-text)] placeholder:text-[var(--c-text-3)] focus:outline-none focus:border-[var(--accent-label)]"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery("")}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--c-text-3)] hover:text-[var(--c-text)]"
                aria-label={t("検索をクリア")}
              >
                <X size={14} />
              </button>
            )}
          </div>
          <div className="flex items-center gap-2 mt-3">
            <button
              onClick={() => setSheetOpen(true)}
              className="flex items-center gap-1.5 shrink-0 text-[13px] px-3.5 py-1.5 rounded-full border border-[var(--accent-label)] text-[var(--accent)] hover:bg-[var(--c-surface-2)] transition-colors"
            >
              <SlidersHorizontal size={13} strokeWidth={2} />
              {t("絞り込み")}
              {activeCount > 0 && (
                <span className="ml-0.5 text-[11px] bg-[var(--accent)] text-[var(--on-accent)] rounded-full w-4 h-4 flex items-center justify-center font-medium">
                  {activeCount}
                </span>
              )}
            </button>
            <div className="flex gap-1.5 overflow-x-auto pb-1 scrollbar-hide">
              {activeChips.map(({ dim, v }) => (
                <button
                  key={`${dim}-${v}`}
                  onClick={() => removeFilter(dim, v)}
                  className="shrink-0 flex items-center gap-1 text-[12px] pl-2.5 pr-1.5 py-1 rounded-full bg-[var(--c-surface-2)] text-[var(--accent-muted)] border border-[var(--c-border)]"
                >
                  {t(v)}
                  <X size={11} />
                </button>
              ))}
            </div>
          </div>
          <label className="flex items-center gap-1.5 mt-2.5 text-[12px] text-[var(--c-text-3)] cursor-pointer select-none w-fit">
            <input
              type="checkbox"
              checked={showOutOfStock}
              onChange={(e) => setShowOutOfStock(e.target.checked)}
              className="accent-[var(--accent)] w-3.5 h-3.5"
            />
            {t("売り切れ商品も表示")}
          </label>
        </div>
      )}

      {tab === "products" && (
        <main className="px-5 py-5 max-w-xl mx-auto">
          <div className="mb-3">
            <DiscoveryFactCard />
          </div>
          {displayed.length === 0 ? (
            <div className="text-center py-16 text-[var(--c-text-3)]">
              <Coffee size={28} className="mx-auto mb-3 opacity-40" />
              {filtered.length === 0 ? (
                <p className="text-[14px]">{t("該当する商品が見つかりませんでした")}</p>
              ) : sortMode === "random" ? (
                <p className="text-[14px]">{t("この範囲には商品がありません。表示範囲を広げてみてください")}</p>
              ) : sortMode === "favoriteArea" ? (
                <p className="text-[14px]">
                  {favoriteArea.prefecture
                    ? t("登録したエリアには該当する商品がありません。設定でエリアを変更してみてください")
                    : t("設定で登録エリア(都道府県・市区町村)を登録してください")}
                </p>
              ) : (
                <p className="text-[14px]">{t("現在30日以内に新規掲載された商品はありません")}</p>
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

      {tab === "collection" && (
        <CollectionView
          products={products}
          isFavorite={isFavorite}
          onToggleFavorite={toggleFavorite}
          onOpenMap={openMapForProduct}
          onLearnOrigin={learnAboutOrigin}
          onOpenDetail={openProductDetail}
          favoriteShops={favoriteShops}
          favoriteDates={favoriteDates}
          getRating={getRating}
          shelf={{ items: shelfItems, onOpen: openShelfItem }}
          backup={{
            favoriteIds,
            favoriteDates,
            importFavorites,
            isPremium,
            userShops: userCollection.userShops,
            userProducts: userCollection.userProducts,
            importUserCollection: userCollection.importCollection,
            photos: { count: photoCount, getBytes: getPhotoBytes, exportAll: exportPhotos, importAll: importPhotos },
          }}
          registered={{
            userShops: userCollection.userShops,
            userProducts: userCollection.userProducts,
            getPhotoUrl,
            onRate: setRating,
            getLogCount: (id) => getLogs(id).length,
            onRegisterProduct: () => setUserShopPickerOpen(true),
            hasSamples,
            onAddSamples: addSamples,
            onRemoveSamples: removeSamples,
            onEditShop: (shop) => setUserShopForm({ shop }),
            onDeleteShop: deleteUserShop,
            onAddProduct: (shop) => setUserProductForm({ shop }),
            onEditProduct: (shop, product) => setUserProductForm({ shop, product }),
            onDeleteProduct: deleteUserProduct,
            onOpenTastingLog: (product) => setTastingLogProduct({ id: product.id, rawName: product.name }),
            onOpenShopMap: openMapForUserShop,
          }}
        />
      )}

      {tab === "diary" && (
        <DiaryView
          events={diaryEvents}
          onOpenLog={(event) => setTastingLogProduct({ id: event.productId, rawName: event.title })}
          history={{ items: historyItems, isPremium, onOpenDetail: openProductDetail }}
          achievements={achievements}
          onOpenAchievements={() => setTab("achievements")}
        />
      )}

      {tab === "achievements" && (
        <AchievementsView
          items={achievements.items}
          earnedCount={achievements.earnedCount}
          visitedPrefectures={achievements.visitedPrefectures}
        />
      )}

      {tab === "shops" && !selectedShop && (
        <ShopListView
          shops={displayedShops}
          productsByShop={productsByShop}
          onSelectShop={setSelectedShop}
          sortMode={shopSortMode}
          onSortModeChange={handleShopSortModeClick}
          geolocation={geolocation}
          favoriteArea={favoriteArea}
        />
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
          tastingNotes={getShopNotes(selectedShop.name)}
          onCreateTastingNote={() => setNoteFormShop(selectedShop)}
          onDeleteTastingNote={(noteId) => deleteShopNote(selectedShop.name, noteId)}
          registered={registeredForSelectedShop}
        />
      )}

      {tab === "guide" && (
        <BuyingGuideView pendingOriginCountry={pendingOriginCountry} onViewProducts={viewProductsForCountry} />
      )}
      {tab === "trivia" && <TriviaView subTab={triviaSub} onLearnOrigin={learnAboutOrigin} events={events} />}

      {tab === "settings" && (
        <SettingsView
          themeId={themeId}
          setThemeId={setThemeId}
          themes={themes}
          isPremium={isPremium}
          setPremium={setPremium}
          products={products}
          displayRadiusId={displayRadiusId}
          setDisplayRadiusId={setDisplayRadiusId}
          displayRadiusOptions={displayRadiusOptions}
          favoriteArea={favoriteArea}
          setFavoriteAreaPrefecture={setFavoriteAreaPrefecture}
          setFavoriteAreaCity={setFavoriteAreaCity}
          myTools={myTools}
          onOpenAbout={() => setAboutOpen(true)}
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
        photoUrl={detailProduct ? getPhotoUrl(detailProduct.id) : null}
        onChangePhoto={(productId, blob) => (blob ? setPhoto(productId, blob) : removePhoto(productId))}
      />
      <UserShopPickerModal
        open={userShopPickerOpen}
        appShops={appShopSuggestions}
        userShops={userCollection.userShops}
        onPickAppShop={pickAppShopForProduct}
        onPickUserShop={pickUserShopForProduct}
        onNewShop={() => {
          setUserShopPickerOpen(false);
          setUserShopForm({});
        }}
        onClose={() => setUserShopPickerOpen(false)}
      />
      <UserShopFormModal
        target={userShopForm}
        appShops={appShopSuggestions}
        userShops={userCollection.userShops}
        onSave={saveUserShop}
        onClose={() => setUserShopForm(null)}
      />
      <UserProductFormModal
        target={userProductForm}
        photoUrl={userProductForm?.product ? getPhotoUrl(userProductForm.product.id) : null}
        onSave={saveUserProduct}
        onClose={() => setUserProductForm(null)}
      />
      <TastingLogModal
        product={tastingLogProduct}
        logs={tastingLogProduct ? getLogs(tastingLogProduct.id) : []}
        myTools={myTools.tools}
        onAddLog={(entry) => addLog(tastingLogProduct.id, entry)}
        onDeleteLog={(entryId) => deleteLog(tastingLogProduct.id, entryId)}
        onClose={() => setTastingLogProduct(null)}
      />
      <ShopTastingNoteModal
        shop={noteFormShop}
        onAddNote={(entry) => addShopNote(noteFormShop.name, entry)}
        onClose={() => setNoteFormShop(null)}
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

      {/* 下から順に: メインメニュー(タブバー) → 著作権表示 → 比較トレイ。
          backdrop-filter は、中の子メニュー用の透明な面(fixed)の基準を狂わせるため付けず、
          ぼかしの代わりに背景は不透明にしている(半透明だと下の文字が透けて見える)。 */}
      <div ref={bottomBarRef} className="fixed bottom-0 inset-x-0 z-20 bg-[var(--c-bar)] flex flex-col">
        {compareTrayVisible && (
          <CompareTray
            count={compareIds.length}
            limit={compareLimit}
            isPremium={isPremium}
            onOpen={() => setCompareModalOpen(true)}
          />
        )}
        <CopyrightFooter />
        <BottomNav
          page={tab}
          triviaSub={triviaSub}
          onNavigate={navigateTo}
          alertCount={alerts.length}
          onAction={(action) => action === "alerts" && setAlertsPanelOpen(true)}
        />
      </div>
    </div>
    </AppNavigationContext.Provider>
  );
}
