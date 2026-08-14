// 値下げ判定・保存用に、単一価格(price)と範囲価格(priceMin)の両方を
// 1つの数値に正規化する。範囲価格しか持たない店舗(Denim bis等)も
// 下限の変化で値下げを検知できるようにするため。
function effectivePrice(product) {
  if (typeof product.price === "number") return product.price;
  if (typeof product.priceMin === "number") return product.priceMin;
  return null;
}

// 「前回アプリを開いた時点」のスナップショットを作る。
// - products: お気に入り商品の価格・在庫状態(値下げ・在庫復活の検知用)
// - shopCatalogs: お気に入り店舗(派生方式)が扱う商品IDの一覧(新商品の検知用)
export function buildAlertSnapshot(products, favoriteIds, favoriteShopNames) {
  const favoriteIdSet = new Set(favoriteIds.map(String));
  const productsState = {};
  const shopCatalogs = {};

  products.forEach((p) => {
    const id = String(p.id);
    if (favoriteShopNames.has(p.shopName)) {
      if (!shopCatalogs[p.shopName]) shopCatalogs[p.shopName] = [];
      shopCatalogs[p.shopName].push(id);
    }
    if (favoriteIdSet.has(id)) {
      productsState[id] = {
        price: effectivePrice(p),
        outOfStock: typeof p.outOfStock === "boolean" ? p.outOfStock : null,
      };
    }
  });

  return { products: productsState, shopCatalogs, updatedAt: new Date().toISOString() };
}

// 前回スナップショットと現在のスナップショットを突き合わせて変化を検出する。
// 前回スナップショットに存在しない商品・店舗(=今回新たにお気に入りにした)は
// 比較対象にせず、今回から追跡を始めるだけにする(いきなり大量の「新商品」
// として誤検知しないようにするため)。
export function diffAlertSnapshot(prevSnapshot, nextSnapshot, products) {
  if (!prevSnapshot) return [];
  const productsById = new Map(products.map((p) => [String(p.id), p]));
  const alerts = [];
  const now = new Date().toISOString();

  Object.entries(nextSnapshot.products).forEach(([id, state]) => {
    const prev = prevSnapshot.products?.[id];
    if (!prev) return;
    const product = productsById.get(id);
    if (!product) return;

    if (typeof prev.price === "number" && typeof state.price === "number" && state.price < prev.price) {
      alerts.push({
        id: `priceDrop-${id}`,
        type: "priceDrop",
        productId: id,
        productName: product.rawName,
        shopName: product.shopName,
        detail: `¥${prev.price.toLocaleString()} → ¥${state.price.toLocaleString()}`,
        detectedAt: now,
      });
    }
    if (prev.outOfStock === true && state.outOfStock === false) {
      alerts.push({
        id: `restock-${id}`,
        type: "restock",
        productId: id,
        productName: product.rawName,
        shopName: product.shopName,
        detail: "在庫が復活しました",
        detectedAt: now,
      });
    }
  });

  Object.entries(nextSnapshot.shopCatalogs).forEach(([shopName, ids]) => {
    const prevIds = prevSnapshot.shopCatalogs?.[shopName];
    if (!prevIds) return;
    const prevIdSet = new Set(prevIds);
    ids.forEach((id) => {
      if (prevIdSet.has(id)) return;
      const product = productsById.get(id);
      if (!product) return;
      alerts.push({
        id: `newProduct-${id}`,
        type: "newProduct",
        productId: id,
        productName: product.rawName,
        shopName,
        detail: "新商品が追加されました",
        detectedAt: now,
      });
    });
  });

  return alerts;
}
