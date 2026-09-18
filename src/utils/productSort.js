import { haversineDistanceKm } from "./geo";

// 「新規掲載」として扱う期間(日数)。first_detected_atからこの日数以内の商品を
// 新着扱いにする(店舗側の新発売日ではなく、このアプリが新たに収録した日基準)。
export const NEW_ARRIVAL_WINDOW_DAYS = 30;

// ランダム表示「自動(おすすめ)」の段階的拡大方式で、この件数に満たない場合は
// 次の段階(より広い範囲)に拡大する。仮置きの閾値で、調整可能なパラメータ
// として残している。
export const RANDOM_MIN_RESULTS_THRESHOLD = 10;

// 段階的拡大の各段階(km)。最後のnullは「全国、絞り込み無し」を表す。
export const RADIUS_STEPS_KM = [5, 20, 50, null];

export function isNewArrival(product, now = new Date()) {
  if (!product.firstDetectedAt) return false;
  const detected = new Date(product.firstDetectedAt);
  if (Number.isNaN(detected.getTime())) return false;
  const diffDays = (now.getTime() - detected.getTime()) / (1000 * 60 * 60 * 24);
  return diffDays >= 0 && diffDays <= NEW_ARRIVAL_WINDOW_DAYS;
}

// 新着(仕様書の「新規掲載」)のみを対象に、新しい順に並べる。表示範囲は
// 当面全国固定(地域を絞らない)。位置情報ソートの許可待ち・拒否時の
// フォールバック表示にも、そのまま同じ関数を使う。
export function sortNewArrivalsFirst(products, now = new Date()) {
  return products
    .filter((p) => isNewArrival(p, now))
    .sort((a, b) => new Date(b.firstDetectedAt) - new Date(a.firstDetectedAt));
}

// 新規掲載かどうかで絞り込まず、収録が新しい順に並べ替えるだけ(お気に入り
// エリア表示用)。first_detected_at不明な商品は末尾にまとめる。
export function sortByRecency(products) {
  return [...products].sort((a, b) => {
    if (!a.firstDetectedAt && !b.firstDetectedAt) return 0;
    if (!a.firstDetectedAt) return 1;
    if (!b.firstDetectedAt) return -1;
    return new Date(b.firstDetectedAt) - new Date(a.firstDetectedAt);
  });
}

export function distanceKmFor(product, coords) {
  if (!coords) return null;
  return haversineDistanceKm(coords.lat, coords.lng, product.shopLat, product.shopLng);
}

// 距離の近い順に並べる。距離不明(店舗が未ジオコーディング、または位置情報
// 未取得)の商品は非表示にせず末尾にまとめる。
export function sortByDistance(products, coords) {
  return [...products].sort((a, b) => {
    const da = distanceKmFor(a, coords);
    const db = distanceKmFor(b, coords);
    if (da === null && db === null) return 0;
    if (da === null) return 1;
    if (db === null) return -1;
    return da - db;
  });
}

// ランダム表示の対象範囲を決める。radiusIdは"auto"|"5"|"20"|"50"|"all"。
// "auto"は段階的拡大方式(5km→20km→50km→全国)で、各段階の該当件数が
// thresholdに満たない場合は次の段階に拡大する。手動固定(5/20/50)は該当件数が
// 0件になり得ることを許容する(位置情報が無い場合も同様に0件を返す――
// 「Xkm以内」を判定する手段が無いため、これは正しい0件であり隠さない)。
export function pickRandomDisplaySet(
  products,
  { radiusId, coords, threshold = RANDOM_MIN_RESULTS_THRESHOLD }
) {
  const withinRadius = (radiusKm) => {
    if (radiusKm === null) return products; // 全国 = 絞り込み無し
    if (!coords) return [];
    return products.filter((p) => {
      const d = distanceKmFor(p, coords);
      return d !== null && d <= radiusKm;
    });
  };

  if (radiusId === "all") return products;

  if (radiusId === "auto") {
    for (const radiusKm of RADIUS_STEPS_KM) {
      const candidates = withinRadius(radiusKm);
      if (candidates.length >= threshold || radiusKm === null) return candidates;
    }
    return products; // 到達しないはずだが保険
  }

  return withinRadius(Number(radiusId));
}

// 登録エリア(マイページで手動登録した都道府県・市区町村)に該当する
// 商品だけを残す。都道府県は完全一致、市区町村は住所文字列への部分一致
// (「区」「市」等の行政区画名まで含めて入力される想定)。どちらも未入力なら
// 絞り込まない。ジオコーディング済みかどうかは問わない(住所文字列のみで
// 判定するため、店舗の緯度経度が無くても機能する)。
export function filterByFavoriteArea(products, { prefecture, city } = {}) {
  const trimmedCity = city?.trim();
  return products.filter((p) => {
    if (prefecture && p.prefecture !== prefecture) return false;
    if (trimmedCity && !p.shopAddress?.includes(trimmedCity)) return false;
    return true;
  });
}

// Fisher-Yatesシャッフル(引数の配列は変更しない)
export function shuffle(array) {
  const result = [...array];
  for (let i = result.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [result[i], result[j]] = [result[j], result[i]];
  }
  return result;
}
