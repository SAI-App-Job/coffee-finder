// アプリ独自の風味語彙。中身(カテゴリ・語・別表記)は flavorVocabulary.json にあり、ここはそれを使いやすい形にするだけ。
// 語を足す・直す手順は docs/flavor-vocabulary.md。直したら npm run flavor:check。
//
// 使う場所: 風味の入力(FlavorPicker)、検索の絞り込み(FilterSheet)、商品の説明文からの自動分類(utils/flavor.js)、英語表示(i18n/en.js)。
// 利用者の記録には「語(日本語)」だけが保存される。語を改名・削除するときは、旧い語を json の legacy に移す(記録が表示できなくなるのを防ぐ)。
import VOCAB from "./flavorVocabulary.json" with { type: "json" };

export const FLAVOR_NEUTRAL_COLOR = VOCAB.neutralColor;

/** カテゴリの一覧(順番は json のまま)。terms は { ja, en, match? } の配列 */
export const FLAVOR_CATEGORIES = VOCAB.categories;

const CATEGORY_BY_ID = new Map(FLAVOR_CATEGORIES.map((c) => [c.id, c]));

// 語 → カテゴリ(選択肢にある語と、旧い語)
const HOME = new Map();
FLAVOR_CATEGORIES.forEach((cat) => cat.terms.forEach((t) => HOME.set(t.ja, cat)));
const LEGACY_HOME = new Map(
  Object.entries(VOCAB.legacy).map(([ja, v]) => [ja, v.category ? CATEGORY_BY_ID.get(v.category) : null])
);

/** 語が属するカテゴリ。旧い語も引ける。どこにも属さない語は null */
export const flavorCategoryOf = (term) => HOME.get(term) ?? LEGACY_HOME.get(term) ?? null;

/** 語の表示色(16進。末尾に透明度を付けて使うため固定色)。カテゴリの無い語は中立色 */
export const flavorTermColor = (term) => flavorCategoryOf(term)?.color ?? FLAVOR_NEUTRAL_COLOR;

/** 選択肢に出る語か(旧い語は false) */
export const isCurrentFlavorTerm = (term) => HOME.has(term);

// 商品の説明文からの自動分類に使う索引。
// 詳細の語: { ja, en, cat, words(小文字: 語そのもの+別表記), generic }。generic は、ほとんどの商品に出る一般的な語(表示で後ろに回す)。
// auto: false の語(酸味など)は、利用者が自分で判断する語。入力の選択肢には出るが、商品の説明文からは自動で付けない。
export const FLAVOR_TERM_ENTRIES = FLAVOR_CATEGORIES.flatMap((cat) =>
  cat.terms.filter((t) => t.auto !== false).map((t) => ({ ja: t.ja, en: t.en, cat, words: [t.ja, ...(t.match ?? [])].map((w) => w.toLowerCase()), generic: t.generic === true }))
);
// カテゴリ全体の別表記(例: 「フルーティー」)。語までは特定できないが、カテゴリには分類できる
export const FLAVOR_CATEGORY_WORDS = FLAVOR_CATEGORIES.map((cat) => ({ cat, words: (cat.match ?? []).map((w) => w.toLowerCase()) }));

/** フィルタの選択肢(カテゴリの日本語名) */
export const FLAVOR_CATEGORY_OPTIONS = FLAVOR_CATEGORIES.map((c) => c.ja);

/** 英語の辞書に足す { 日本語: 英語 }(カテゴリ・語・旧い語) */
export const FLAVOR_EN = (() => {
  const en = {};
  for (const cat of FLAVOR_CATEGORIES) {
    en[cat.ja] = cat.en;
    for (const t of cat.terms) en[t.ja] = t.en;
  }
  for (const [ja, v] of Object.entries(VOCAB.legacy)) en[ja] ??= v.en;
  return en;
})();
