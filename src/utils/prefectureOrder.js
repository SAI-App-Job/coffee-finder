// 都道府県を「登録店舗数が多い順」に並べるためのランク表。全件表示(位置情報
// 未取得時の商品タブ)と店舗一覧の両方で共通して使う。店舗数の集計は商品では
// なく店舗(shops)を基準にする(1店舗の商品数の多寡で都道府県の並びが
// ぶれないようにするため)。
export function buildPrefectureRank(shops) {
  const counts = new Map();
  for (const shop of shops) {
    if (!shop.prefecture) continue;
    counts.set(shop.prefecture, (counts.get(shop.prefecture) || 0) + 1);
  }
  const rank = new Map();
  [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .forEach(([prefecture], index) => rank.set(prefecture, index));
  return rank;
}

// 都道府県情報が無い項目は末尾にまとめる。同じ都道府県内での並び順は
// 元の配列の順序を保つ(Array#sortは安定ソート)。
export function sortByPrefecturePopularity(items, prefectureRank, getPrefecture) {
  const rankOf = (item) => {
    const prefecture = getPrefecture(item);
    return prefecture && prefectureRank.has(prefecture) ? prefectureRank.get(prefecture) : Infinity;
  };
  return [...items].sort((a, b) => rankOf(a) - rankOf(b));
}
