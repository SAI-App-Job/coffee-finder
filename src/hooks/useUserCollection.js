import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "coffee-finder:user-collection";

function generateId(prefix) {
  const random =
    typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
  return `${prefix}-${random}`;
}

const asString = (v) => (typeof v === "string" ? v.trim() : "");
const asNumberOrNull = (v) => (typeof v === "number" && Number.isFinite(v) && v >= 0 ? v : null);

// 保存データ・バックアップファイルのどちらから来た値も、同じ形に整えて取り込む。
function sanitizeShop(raw) {
  if (!raw || typeof raw !== "object") return null;
  const id = asString(raw.id);
  const name = asString(raw.name);
  if (!id || !name) return null;
  return {
    id,
    name,
    address: asString(raw.address),
    // アプリに収録されている店舗と紐づいている場合の、その店舗名(手動で作った店舗は空)
    appShopName: asString(raw.appShopName),
    createdAt: asString(raw.createdAt) || new Date().toISOString(),
  };
}

function sanitizeProduct(raw) {
  if (!raw || typeof raw !== "object") return null;
  const id = asString(raw.id);
  const shopId = asString(raw.shopId);
  const name = asString(raw.name);
  if (!id || !shopId || !name) return null;
  return {
    id,
    shopId,
    name,
    price: asNumberOrNull(raw.price),
    weightG: asNumberOrNull(raw.weightG),
    originCountry: asString(raw.originCountry),
    roast: asString(raw.roast),
    processingMethod: asString(raw.processingMethod),
    flavors: Array.isArray(raw.flavors) ? raw.flavors.filter((f) => typeof f === "string") : [],
    note: asString(raw.note),
    createdAt: asString(raw.createdAt) || new Date().toISOString(),
  };
}

function load() {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null");
    const shops = (Array.isArray(parsed?.shops) ? parsed.shops : []).map(sanitizeShop).filter(Boolean);
    const shopIds = new Set(shops.map((s) => s.id));
    const products = (Array.isArray(parsed?.products) ? parsed.products : [])
      .map(sanitizeProduct)
      .filter((p) => p && shopIds.has(p.shopId));
    return { shops, products };
  } catch {
    return { shops: [], products: [] };
  }
}

// ユーザーが手動で登録した「店舗 → 商品」。アプリ収録の店舗・商品データ(GitHub上のJSON)とは
// 完全に別の、端末内だけのデータで、コレクション画面の「登録した商品」に表示する。
// レコード: shops = { id, name, address, appShopName, createdAt }[]、
//   appShopName があるものは、アプリ収録の店舗(店名で一致)に紐づく「登録商品のまとまり」で、
//   店舗そのものを新しく作ったわけではない(店舗画面にも、その店舗の登録商品として表示する)。
//           products = { id, shopId, name, price, weightG, originCountry, roast,
//                        processingMethod, flavors[], note, createdAt }[]
// 商品IDは評価(★)・テイスティングログのキーにも使う(アプリ収録の商品IDとは衝突しない "user-" 始まり)。
export function useUserCollection() {
  const [data, setData] = useState(load);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    } catch {
      // プライベートブラウジング等でlocalStorageが使えない場合は保存をスキップ
    }
  }, [data]);

  const addShop = useCallback((input) => {
    const shop = sanitizeShop({ ...input, id: generateId("user-shop"), createdAt: new Date().toISOString() });
    if (!shop) return null;
    setData((prev) => ({ ...prev, shops: [...prev.shops, shop] }));
    return shop.id;
  }, []);

  // アプリ収録の店舗に紐づく登録先を返す(無ければ作る)。店名で一致させ、同じ店舗の重複は作らない。
  const findOrCreateAppShop = useCallback(
    ({ name, address }) => {
      const existing = data.shops.find((s) => s.appShopName === name);
      if (existing) return existing.id;
      return addShop({ name, address, appShopName: name });
    },
    [data.shops, addShop]
  );

  const updateShop = useCallback((id, input) => {
    setData((prev) => ({
      ...prev,
      shops: prev.shops.map((s) => {
        if (s.id !== id) return s;
        return sanitizeShop({ ...s, ...input, id }) ?? s;
      }),
    }));
  }, []);

  // 店舗を消すと、その店舗の商品も一緒に消える。評価の掃除のため、消えた商品のIDを返す。
  const deleteShop = useCallback(
    (id) => {
      const removedProductIds = data.products.filter((p) => p.shopId === id).map((p) => p.id);
      setData((prev) => ({
        shops: prev.shops.filter((s) => s.id !== id),
        products: prev.products.filter((p) => p.shopId !== id),
      }));
      return removedProductIds;
    },
    [data.products]
  );

  const addProduct = useCallback((shopId, input) => {
    const product = sanitizeProduct({
      ...input,
      id: generateId("user-product"),
      shopId,
      createdAt: new Date().toISOString(),
    });
    if (!product) return null;
    setData((prev) => ({ ...prev, products: [product, ...prev.products] }));
    return product.id;
  }, []);

  const updateProduct = useCallback((id, input) => {
    setData((prev) => ({
      ...prev,
      products: prev.products.map((p) => {
        if (p.id !== id) return p;
        return sanitizeProduct({ ...p, ...input, id, shopId: p.shopId }) ?? p;
      }),
    }));
  }, []);

  const deleteProduct = useCallback((id) => {
    setData((prev) => ({ ...prev, products: prev.products.filter((p) => p.id !== id) }));
  }, []);

  // バックアップファイルからの復元用。既存のデータは失わないよう、上書きではなく
  // 差分(IDが未登録のもの)だけを追加するマージ方式。商品は、店舗が存在するものだけ取り込む。
  const importCollection = useCallback(
    ({ shops: rawShops, products: rawProducts }) => {
      const knownShopIds = new Set(data.shops.map((s) => s.id));
      const knownProductIds = new Set(data.products.map((p) => p.id));
      const newShops = (Array.isArray(rawShops) ? rawShops : [])
        .map(sanitizeShop)
        .filter((s) => s && !knownShopIds.has(s.id));
      const allShopIds = new Set([...knownShopIds, ...newShops.map((s) => s.id)]);
      const newProducts = (Array.isArray(rawProducts) ? rawProducts : [])
        .map(sanitizeProduct)
        .filter((p) => p && allShopIds.has(p.shopId) && !knownProductIds.has(p.id));
      if (newShops.length > 0 || newProducts.length > 0) {
        setData((prev) => ({
          shops: [...prev.shops, ...newShops],
          products: [...prev.products, ...newProducts],
        }));
      }
      return {
        shopsAdded: newShops.length,
        productsAdded: newProducts.length,
        // 取り込み後に存在する、手動登録した商品のID(写真の復元で、行き先のない写真を弾くのに使う)
        productIds: [...data.products, ...newProducts].map((p) => p.id),
      };
    },
    [data]
  );

  return {
    userShops: data.shops,
    userProducts: data.products,
    addShop,
    findOrCreateAppShop,
    updateShop,
    deleteShop,
    addProduct,
    updateProduct,
    deleteProduct,
    importCollection,
  };
}
