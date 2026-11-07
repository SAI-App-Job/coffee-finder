import { ALL_PREFECTURES } from "../data/prefectures";
import { isSampleId } from "../data/sampleCollection";

// 日記・実績の元になる「記録の出来事」。次の4種類を、日時つきで集める。
//   log      : テイスティングログ(商品ごと)
//   note     : 店舗のテイスティングノート
//   register : 手動で登録した商品
//   photo    : パッケージ写真(追加した日。日付が無い写真は、手動登録した商品の登録日で代用する)
// サンプルデータは、使い方を見せるためのものなので、集計に含めない。
export const EVENT_KINDS = ["log", "note", "register", "photo"];

export function buildDiaryEvents({
  logsByProduct,
  notesByShop,
  userProducts,
  userShops,
  photoIds,
  photoDates,
  productsById,
  shopsByName,
}) {
  const userProductById = new Map(userProducts.map((p) => [p.id, p]));
  const userShopById = new Map(userShops.map((s) => [s.id, s]));
  const appProduct = (id) => productsById.get(String(id));
  const nameOf = (id) => userProductById.get(id)?.name ?? appProduct(id)?.rawName ?? "";
  const originOf = (id) => userProductById.get(id)?.originCountry || appProduct(id)?.originCountry || "";
  const prefectureOfUserShop = (shop) => {
    if (shop.appShopName) return shopsByName.get(shop.appShopName)?.prefecture ?? "";
    return ALL_PREFECTURES.find((p) => shop.address?.startsWith(p)) ?? "";
  };

  const events = [];
  for (const [productId, entries] of Object.entries(logsByProduct)) {
    if (isSampleId(productId)) continue;
    for (const entry of entries) {
      const t = Date.parse(entry.recordedAt);
      if (Number.isNaN(t)) continue;
      events.push({
        kind: "log",
        t,
        id: `log-${entry.id}`,
        productId,
        title: nameOf(productId),
        place: entry.place === "shop" ? "shop" : "home",
        origin: originOf(productId),
      });
    }
  }
  for (const [shopName, notes] of Object.entries(notesByShop)) {
    const prefecture = shopsByName.get(shopName)?.prefecture ?? "";
    for (const note of notes) {
      const t = Date.parse(note.recordedAt);
      if (Number.isNaN(t)) continue;
      events.push({ kind: "note", t, id: `note-${note.id}`, title: note.productName ?? "", shopName, prefecture });
    }
  }
  for (const product of userProducts) {
    if (isSampleId(product.id)) continue;
    const t = Date.parse(product.createdAt);
    if (Number.isNaN(t)) continue;
    const shop = userShopById.get(product.shopId);
    events.push({
      kind: "register",
      t,
      id: `register-${product.id}`,
      productId: product.id,
      title: product.name,
      shopName: shop?.name ?? "",
      prefecture: shop ? prefectureOfUserShop(shop) : "",
      origin: product.originCountry,
    });
  }
  for (const id of photoIds) {
    if (isSampleId(id)) continue;
    const t = Date.parse(photoDates[id] ?? userProductById.get(id)?.createdAt ?? "");
    if (Number.isNaN(t)) continue;
    events.push({ kind: "photo", t, id: `photo-${id}`, productId: id, title: nameOf(id) });
  }
  return events.sort((a, b) => a.t - b.t);
}

// 今週(月曜はじまり)・今月・今年の、それぞれの開始時刻(端末の時間帯で数える)
export function periodStarts(now = new Date()) {
  const day = new Date(now);
  day.setHours(0, 0, 0, 0);
  const week = new Date(day);
  week.setDate(day.getDate() - ((day.getDay() + 6) % 7));
  return {
    week: week.getTime(),
    month: new Date(day.getFullYear(), day.getMonth(), 1).getTime(),
    year: new Date(day.getFullYear(), 0, 1).getTime(),
  };
}

export const PERIODS = ["week", "month", "year"];

// 期間ごと・種類ごとの件数。{ week: { log, note, register, photo, total }, month: {…}, year: {…} }
export function countByPeriod(events, now = new Date()) {
  const starts = periodStarts(now);
  const result = Object.fromEntries(
    PERIODS.map((period) => [period, { log: 0, note: 0, register: 0, photo: 0, total: 0 }])
  );
  const nowMs = now.getTime();
  for (const event of events) {
    if (event.t > nowMs) continue; // 端末の時計が進んでいたときの、未来の日時は数えない
    for (const period of PERIODS) {
      if (event.t >= starts[period]) {
        result[period][event.kind] += 1;
        result[period].total += 1;
      }
    }
  }
  return result;
}

export const localDateKey = (t) => {
  const d = new Date(t);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

// 新しい順に、日付ごとにまとめる。[{ key: "2026-11-08", t: 日の正午, items: [...] }]
export function groupByDay(events) {
  const groups = [];
  const byKey = new Map();
  for (const event of [...events].sort((a, b) => b.t - a.t)) {
    const key = localDateKey(event.t);
    let group = byKey.get(key);
    if (!group) {
      const d = new Date(event.t);
      group = { key, t: new Date(d.getFullYear(), d.getMonth(), d.getDate(), 12).getTime(), items: [] };
      byKey.set(key, group);
      groups.push(group);
    }
    group.items.push(event);
  }
  return groups;
}
