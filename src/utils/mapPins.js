// 店舗1件から、地図に表示するピンの配列を作る。複数拠点(locations)を持つ店舗は
// 全拠点分、単一店舗は代表座標(shop.lat/lng)1件分を返す。緯度経度が未取得の
// 拠点(ジオコーディング失敗)は除外する。
export function shopToPins(shop) {
  if (Array.isArray(shop.locations) && shop.locations.length > 0) {
    return shop.locations
      .filter((loc) => typeof loc.lat === "number" && typeof loc.lng === "number")
      .map((loc) => ({
        id: `${shop.name}-${loc.label ?? "main"}`,
        shopName: shop.name,
        label: loc.label,
        address: loc.address,
        mapQuery: loc.mapQuery || shop.mapQuery,
        lat: loc.lat,
        lng: loc.lng,
      }));
  }
  if (typeof shop.lat === "number" && typeof shop.lng === "number") {
    return [
      {
        id: shop.name,
        shopName: shop.name,
        label: null,
        address: shop.address,
        mapQuery: shop.mapQuery,
        lat: shop.lat,
        lng: shop.lng,
      },
    ];
  }
  return [];
}

// 日本の住所ジオコーディングは町丁目レベルまでしか解決できないことがあり、
// 同じ町内の複数拠点が同一座標に重なる場合がある。表示上だけ小さな円状に
// 分散させて、すべてのピンをクリックできるようにする(実データの座標は変更しない)。
const OVERLAP_OFFSET_DEG = 0.0006; // およそ50〜60m相当

export function spreadOverlappingPins(pins) {
  const groups = new Map();
  pins.forEach((pin) => {
    const key = `${pin.lat.toFixed(4)},${pin.lng.toFixed(4)}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(pin);
  });

  const result = [];
  groups.forEach((group) => {
    if (group.length === 1) {
      result.push(group[0]);
      return;
    }
    group.forEach((pin, i) => {
      const angle = (2 * Math.PI * i) / group.length;
      result.push({
        ...pin,
        lat: pin.lat + OVERLAP_OFFSET_DEG * Math.sin(angle),
        lng: pin.lng + OVERLAP_OFFSET_DEG * Math.cos(angle),
      });
    });
  });
  return result;
}
