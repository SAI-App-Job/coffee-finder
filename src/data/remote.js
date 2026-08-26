import { normalizeProcessingMethod } from "../utils/processingMethod";

const BASE_URL = "https://raw.githubusercontent.com/SAI-App-Job/coffee-finder/master/data/";

async function fetchJSON(path) {
  const res = await fetch(BASE_URL + path, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path} の取得に失敗しました(status: ${res.status})`);
  return res.json();
}

function mapLocation(loc) {
  return {
    label: loc.label,
    address: loc.address,
    hours: loc.hours,
    tel: loc.tel,
    email: loc.email,
    mapQuery: loc.map_query,
    lat: typeof loc.lat === "number" ? loc.lat : null,
    lng: typeof loc.lng === "number" ? loc.lng : null,
  };
}

function mapShop(raw) {
  const shop = {
    name: raw.name,
    address: raw.address,
    prefecture: raw.prefecture,
    hours: raw.hours,
    platform: raw.platform,
    url: raw.url,
    mapQuery: raw.map_query,
    lat: typeof raw.lat === "number" ? raw.lat : null,
    lng: typeof raw.lng === "number" ? raw.lng : null,
  };
  // 実店舗が複数ある場合のみlocationsを持たせる(単一店舗はSHOPの直接フィールドのみを
  // 見るShopDetailViewの`hasMultipleLocations`判定に合わせるため)
  if (raw.shop_type === "multi_location" && Array.isArray(raw.locations)) {
    shop.locations = raw.locations.map(mapLocation);
  }
  return shop;
}

function mapProduct(raw, shopsByName) {
  const shop = shopsByName.get(raw.shop_name);
  return {
    id: raw.id,
    shopName: raw.shop_name,
    shopAddress: shop?.address ?? null,
    prefecture: shop?.prefecture ?? null,
    rawName: raw.raw_name,
    originCountry: raw.origin_country,
    designatedBrand: raw.designated_brand,
    // データ取得時点で正規化しておく(未正規化の生の表記が紛れ込んでいても、
    // タグの解説を確実に引けるようにするための保険。詳細はutils/processingMethod.js参照)
    processingMethod: normalizeProcessingMethod(raw.processing_method),
    grade: raw.grade,
    roast: raw.roast_level,
    roastSelectable: raw.roast_selectable,
    price: raw.price,
    priceMin: raw.price_min,
    priceMax: raw.price_max,
    // 価格が店舗サイトに一切掲載されていない場合の案内文(例:豆コネクトの
    // 「価格は店舗にお問い合わせください」)。priceが取れなかった場合の表示分岐に使う
    priceNote: raw.price_note ?? null,
    weightG: raw.weight_g,
    flavorNotes: raw.flavor_notes,
    mapQuery: raw.map_query,
    farmNote: raw.farm_note,
    outOfStock: typeof raw.out_of_stock === "boolean" ? raw.out_of_stock : null,
    // 「販売中」「一時的に品切れ」「終売」の3段階。データに無い場合(モックデータ等)は
    // 販売中扱いにする(在庫状態が分からないことを理由に一覧から隠さないため)。
    stockStatus: raw.stock_status || "販売中",
    // ブレンドの産地別内訳(現状PHILOCOFFEAのみ)。各要素は判明した項目のみ
    // 埋まっている前提で、無い項目はnullのまま(欠けている項目を推測で埋めない)。
    blendComponents: Array.isArray(raw.blend_components)
      ? raw.blend_components.map((c) => ({
          originCountry: c.origin_country ?? null,
          percentage: typeof c.percentage === "number" ? c.percentage : null,
          producer: c.producer ?? null,
          farm: c.farm ?? null,
          variety: c.variety ?? null,
          altitude: c.altitude ?? null,
          processingMethod: c.processing_method ? normalizeProcessingMethod(c.processing_method) : null,
        }))
      : [],
  };
}

function mapEvent(raw, sourcesById) {
  return {
    source: sourcesById.get(raw.source_id)?.name ?? raw.source_id,
    sourceId: raw.source_id,
    name: raw.name,
    eventType: raw.event_type,
    venue: raw.venue,
    dateRange: raw.date_range,
    startDate: raw.start_date ?? null,
    relatedCountry: raw.related_country,
    note: raw.description,
    sourceUrl: raw.source_url,
  };
}

// GitHub(raw.githubusercontent.com)上の shops.json / products.json / events.json を取得し、
// 既存コンポーネントがそのまま使えるキャメルケース形状に変換して返す。
// 3ファイルのうちどれか1つでも失敗した場合は、部分的な差し替えによる不整合を避けるため
// nullを返す(呼び出し側は現行のモックデータをそのまま使い続ける)。
export async function loadRemoteData() {
  try {
    const [shopsRaw, productsRaw, eventsRaw] = await Promise.all([
      fetchJSON("shops.json"),
      fetchJSON("products.json"),
      fetchJSON("events.json"),
    ]);

    const shops = shopsRaw.map(mapShop);
    const shopsByName = new Map(shops.map((s) => [s.name, s]));
    const products = productsRaw.map((p) => mapProduct(p, shopsByName));

    const sourcesById = new Map((eventsRaw.sources || []).map((s) => [s.id, s]));
    const events = (eventsRaw.events || []).map((e) => mapEvent(e, sourcesById));

    return { shops, products, events };
  } catch (err) {
    console.warn("リモートデータの取得に失敗したため、モックデータを使用します。", err);
    return null;
  }
}
