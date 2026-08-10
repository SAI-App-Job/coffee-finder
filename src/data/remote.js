const BASE_URL = "https://raw.githubusercontent.com/SAI-App-Job/coffee-finder/main/data/";

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
    mapQuery: loc.map_query,
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
    processingMethod: raw.processing_method,
    grade: raw.grade,
    roast: raw.roast_level,
    roastSelectable: raw.roast_selectable,
    price: raw.price,
    weightG: raw.weight_g,
    flavorNotes: raw.flavor_notes,
    mapQuery: raw.map_query,
    farmNote: raw.farm_note,
  };
}

function mapEvent(raw, sourcesById) {
  return {
    source: sourcesById.get(raw.source_id)?.name ?? raw.source_id,
    name: raw.name,
    eventType: raw.event_type,
    venue: raw.venue,
    dateRange: raw.date_range,
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
