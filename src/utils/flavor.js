import { FLAVOR_TERM_INDEX } from "../data/flavorWheel";

export function categorizeFlavorNotes(text) {
  if (!text) return [];
  const lower = text.toLowerCase();
  const matched = [];
  for (const { term, cat } of FLAVOR_TERM_INDEX) {
    if (lower.includes(term) && !matched.find((c) => c.en === cat.en)) {
      matched.push(cat);
    }
  }
  return matched;
}

// 評価済み商品のflavorNotesを星の数で重み付けして集計し、フレーバー
// カテゴリごとの好み傾向スコアを算出する。1商品が複数カテゴリに
// またがる場合は、該当する各カテゴリにそのまま星の数を加算する
// (商品カード等で複数タグを同時表示している既存の扱いに合わせている)。
export function computeFlavorPreferenceScores(ratedEntries) {
  const scores = new Map();
  ratedEntries.forEach(({ product, rating }) => {
    if (!rating) return;
    categorizeFlavorNotes(product.flavorNotes).forEach((cat) => {
      const entry = scores.get(cat.en) ?? { category: cat, score: 0, count: 0 };
      entry.score += rating;
      entry.count += 1;
      scores.set(cat.en, entry);
    });
  });
  return [...scores.values()].sort((a, b) => b.score - a.score);
}

// 傾向上位カテゴリに合致する商品を、一致カテゴリ数の多い順に返す。
// 呼び出し側で「まだ評価していない商品」に絞り込んだ上で渡す想定。
export function recommendByFlavorCategories(candidateProducts, topCategoryEns, limit = 6) {
  if (topCategoryEns.length === 0) return [];
  return candidateProducts
    .map((product) => {
      const categories = categorizeFlavorNotes(product.flavorNotes).map((c) => c.en);
      const matchCount = categories.filter((en) => topCategoryEns.includes(en)).length;
      return { product, matchCount };
    })
    .filter((entry) => entry.matchCount > 0)
    .sort((a, b) => b.matchCount - a.matchCount)
    .slice(0, limit)
    .map((entry) => entry.product);
}
