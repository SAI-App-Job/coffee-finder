import { findAffirmedWord } from "./flavorMatch";
import { FLAVOR_TERM_ENTRIES, FLAVOR_CATEGORY_WORDS, FLAVOR_CATEGORIES } from "../data/flavorVocabulary";

// 商品のテイスティングノート(説明文)から、風味の詳細(語)とカテゴリを判定する。
// terms: 説明文に載っていた語 { ja, en, cat, generic, word(見つかった表記) }(カテゴリ→語の順)
// categories: 分類されたカテゴリ(語が見つかったカテゴリ+カテゴリ全体の別表記だけで分類されたもの)
// categoryOnly: 語は特定できず、カテゴリだけに分類されたもの
const cache = new Map();
export function analyzeFlavorNotes(text) {
  if (!text) return { terms: [], categories: [], categoryOnly: [] };
  const hit = cache.get(text);
  if (hit) return hit;
  const lower = text.toLowerCase();
  const terms = [];
  for (const e of FLAVOR_TERM_ENTRIES) {
    const word = findAffirmedWord(lower, e.words);
    if (word) terms.push({ ja: e.ja, en: e.en, cat: e.cat, generic: e.generic, word });
  }
  const withTerm = new Set(terms.map((t) => t.cat.id));
  const generalWords = new Set(FLAVOR_CATEGORY_WORDS.filter(({ words }) => findAffirmedWord(lower, words)).map(({ cat }) => cat.id));
  const categories = FLAVOR_CATEGORIES.filter((c) => withTerm.has(c.id) || generalWords.has(c.id));
  const categoryOnly = categories.filter((c) => !withTerm.has(c.id));
  const result = { terms, categories, categoryOnly };
  if (cache.size > 5000) cache.clear();
  cache.set(text, result);
  return result;
}

// 一覧カードに並べる順: 特定の語 → 一般的な語 → 語を特定できなかったカテゴリ
export function flavorTagItems(analysis) {
  return [
    ...analysis.terms.filter((x) => !x.generic).map((x) => ({ key: `t:${x.ja}`, label: x.ja, cat: x.cat, word: x.word })),
    ...analysis.terms.filter((x) => x.generic).map((x) => ({ key: `t:${x.ja}`, label: x.ja, cat: x.cat, word: x.word })),
    ...analysis.categoryOnly.map((c) => ({ key: `c:${c.id}`, label: c.ja, cat: c, word: null })),
  ];
}

// 商品の風味の判定。data/products.json には、店舗の長い説明文は載せず、判定済みの結果(flavor_terms・flavor_category_only)を載せている
// (scripts/reduce-product-text.js)。その結果があれば、それを使う。無い商品(サンプル等)は、説明文から判定する。
// terms: 判定済みの語 { ja, en, cat, generic, word(説明文に載っていた表記) }
const TERM_BY_JA = new Map(FLAVOR_TERM_ENTRIES.map((e) => [e.ja, e]));
const analysisCache = new WeakMap();
export function analyzeProductFlavor(product) {
  if (!Array.isArray(product?.flavorTerms)) return analyzeFlavorNotes(product?.flavorNotes);
  const hit = analysisCache.get(product);
  if (hit) return hit;
  const terms = [];
  for (const [ja, word] of product.flavorTerms) {
    const e = TERM_BY_JA.get(ja);
    if (e) terms.push({ ja: e.ja, en: e.en, cat: e.cat, generic: e.generic, word });
  }
  const withTerm = new Set(terms.map((t) => t.cat.id));
  const onlyIds = new Set(Array.isArray(product.flavorCategoryOnly) ? product.flavorCategoryOnly : []);
  const categories = FLAVOR_CATEGORIES.filter((c) => withTerm.has(c.id) || onlyIds.has(c.id));
  const categoryOnly = categories.filter((c) => !withTerm.has(c.id));
  const result = { terms, categories, categoryOnly };
  analysisCache.set(product, result);
  return result;
}

export const categorizeFlavorNotes = (text) => analyzeFlavorNotes(text).categories;
export const categorizeProduct = (product) => analyzeProductFlavor(product).categories;

// 評価済み商品のflavorNotesを星の数で重み付けして集計し、フレーバー
// カテゴリごとの好み傾向スコアを算出する。1商品が複数カテゴリに
// またがる場合は、該当する各カテゴリにそのまま星の数を加算する
// (商品カード等で複数タグを同時表示している既存の扱いに合わせている)。
export function computeFlavorPreferenceScores(ratedEntries) {
  const scores = new Map();
  ratedEntries.forEach(({ product, rating }) => {
    if (!rating) return;
    categorizeProduct(product).forEach((cat) => {
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
// 終売・売り切れの商品はおすすめとして提示しても購入できないため、
// 在庫状態が「販売中」の商品のみを候補にする(「好みの傾向」グラフ自体の
// 集計対象(評価済み商品全体)は在庫と無関係のためここでは絞り込まない)。
export function recommendByFlavorCategories(candidateProducts, topCategoryEns, limit = 6) {
  if (topCategoryEns.length === 0) return [];
  return candidateProducts
    .filter((product) => product.stockStatus === "販売中")
    .map((product) => {
      const categories = categorizeProduct(product).map((c) => c.en);
      const matchCount = categories.filter((en) => topCategoryEns.includes(en)).length;
      return { product, matchCount };
    })
    .filter((entry) => entry.matchCount > 0)
    .sort((a, b) => b.matchCount - a.matchCount)
    .slice(0, limit)
    .map((entry) => entry.product);
}
