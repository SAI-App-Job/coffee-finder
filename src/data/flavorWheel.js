// ---------------------------------------------------------------------------
// フレーバーホイール詳細データ(SCA/WCRが公開した用語リストを基に、
// 独自のカード形式で再構成。円形の図そのものは複製しない)
// 出典: coffee-flavor-notes.md(SCA Coffee Taster's Flavor Wheel / WCR Sensory Lexicon)
// ---------------------------------------------------------------------------
export const FLAVOR_WHEEL_DATA = [
  {
    en: "Fruity", ja: "フルーティー", color: "#C9506B",
    sub: [
      { group: "ベリー", terms: ["ブラックベリー", "ラズベリー", "ブルーベリー", "イチゴ"] },
      { group: "ドライフルーツ", terms: ["レーズン", "プルーン"] },
      { group: "その他フルーツ", terms: ["ココナッツ", "チェリー", "ザクロ", "パイナップル", "ぶどう", "リンゴ", "桃", "洋梨"] },
      { group: "柑橘", terms: ["グレープフルーツ", "オレンジ", "レモン", "ライム"] },
    ],
  },
  {
    en: "Floral", ja: "フローラル", color: "#B784C4",
    sub: [{ group: "花", terms: ["カモミール", "ローズ", "ジャスミン"] }],
  },
  {
    en: "Sweet", ja: "スイート/甘み", color: "#D4A24E",
    sub: [
      { group: "ブラウンシュガー系", terms: ["糖蜜", "メープルシロップ", "カラメル", "はちみつ"] },
      { group: "バニラ系", terms: ["バニラ", "バニリン"] },
      { group: "その他", terms: ["全体的な甘さ", "甘い香り", "紅茶"] },
    ],
  },
  {
    en: "Nutty/Cocoa", ja: "ナッツ/カカオ", color: "#8B5E2E",
    sub: [
      { group: "ナッツ", terms: ["ピーナッツ", "ヘーゼルナッツ", "アーモンド"] },
      { group: "カカオ", terms: ["チョコレート", "ダークチョコレート"] },
    ],
  },
  {
    en: "Spices", ja: "スパイス", color: "#A8452F",
    sub: [
      { group: "刺激的な香り", terms: ["ピリッとした香り", "ペッパー"] },
      { group: "褐色系スパイス", terms: ["アニス", "ナツメグ", "シナモン", "クローブ"] },
    ],
  },
  {
    en: "Roasted", ja: "ロースト", color: "#5A3A22",
    sub: [
      { group: "たばこ系", terms: ["パイプたばこ", "たばこ"] },
      { group: "焦げ", terms: ["刺激臭", "灰っぽさ", "スモーキー"] },
      { group: "穀物系", terms: ["ロースト香", "穀物", "麦芽"] },
    ],
  },
  {
    en: "Green/Vegetative", ja: "グリーン/野菜っぽさ", color: "#6B8E4E",
    sub: [
      { group: "青っぽさ", terms: ["未熟", "さやえんどう", "フレッシュ", "濃い緑", "野菜っぽさ", "干し草様", "ハーブ様"] },
      { group: "豆っぽさ", terms: ["豆様"] },
    ],
  },
  {
    en: "Sour/Fermented", ja: "酸味/発酵", color: "#C9A83B",
    sub: [
      { group: "酸味", terms: ["酸っぱい香り", "酢酸", "酪酸", "イソ吉草酸", "クエン酸", "リンゴ酸"] },
      { group: "発酵系", terms: ["ワインのような", "ウイスキーのような", "発酵", "過熟"] },
    ],
  },
  {
    en: "Other", ja: "その他", color: "#8B7361",
    sub: [
      { group: "紙っぽさ/カビっぽさ", terms: ["古紙様", "段ボール様", "紙様", "木質様", "カビ様", "埃っぽい", "土っぽい"] },
      { group: "ケミカル", terms: ["苦味", "塩味", "薬品様", "石油様", "スカンク様", "ゴム様"] },
      { group: "その他の要素", terms: ["動物臭", "肉様/だし様", "フェノール様", "オリーブオイル様"] },
    ],
  },
];

// テイスティングノート(flavor_notes)のフリーテキストから9大カテゴリを自動判定する
// ための索引。FLAVOR_WHEEL_DATAの日本語用語に加え、実店舗の説明文は英語表記も
// 多い(PHILOCOFFEA等)ため、代表的な英語用語も別途マッピングしている。
export const FLAVOR_TERM_INDEX = (() => {
  const index = [];
  FLAVOR_WHEEL_DATA.forEach((cat) => {
    cat.sub.forEach((s) => {
      s.terms.forEach((t) => index.push({ term: t.toLowerCase(), cat }));
    });
  });
  const englishTerms = {
    Fruity: ["berry", "blueberry", "raspberry", "strawberry", "cherry", "citrus", "orange", "lemon", "lime", "grape", "pineapple", "peach", "apple", "grapefruit"],
    Floral: ["floral", "jasmine", "rose", "bergamot"],
    Sweet: ["honey", "caramel", "vanilla", "molasses", "maple", "brown sugar", "sweet"],
    "Nutty/Cocoa": ["chocolate", "cocoa", "almond", "hazelnut", "nutty", "peanut"],
    Spices: ["cinnamon", "clove", "nutmeg", "pepper", "spice"],
    Roasted: ["smoky", "tobacco", "roasted", "malt"],
    "Green/Vegetative": ["herbal", "green", "vegetal", "grassy"],
    "Sour/Fermented": ["winey", "fermented", "sour", "whiskey"],
    Other: ["earthy", "musty", "papery", "bitter"],
  };
  Object.entries(englishTerms).forEach(([en, terms]) => {
    const cat = FLAVOR_WHEEL_DATA.find((c) => c.en === en);
    if (cat) terms.forEach((t) => index.push({ term: t, cat }));
  });
  return index;
})();

// フィルタの選択肢として使う風味カテゴリ一覧(日本語名)
export const FLAVOR_CATEGORY_OPTIONS = FLAVOR_WHEEL_DATA.map((c) => c.ja);
