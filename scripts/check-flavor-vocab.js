// 風味語彙(src/data/flavorVocabulary.json)の検査: npm run flavor:check
// - 形の誤り(重複・英語名の抜け・色の形式・別表記の衝突・legacy の参照先)があれば、終了コード1で終わる。
// - 商品説明(data/products.json があれば)での各語の出現数と、自動分類のカバー率を表示する(語を足すときの目安)。
import { readFileSync, existsSync } from "node:fs";
import { findAffirmedWord } from "../src/utils/flavorMatch.js";

const vocab = JSON.parse(readFileSync("src/data/flavorVocabulary.json", "utf8"));
const errors = [];
const fail = (m) => errors.push(m);

const ids = new Set();
const enNames = new Set();
const jaOwner = new Map(); // 語・カテゴリ名 → 所有者
const matchOwner = new Map(); // 別表記(小文字) → 語
const COLOR = /^#[0-9a-fA-F]{6}$/;
if (!COLOR.test(vocab.neutralColor ?? "")) fail(`neutralColor が #RRGGBB ではない: ${vocab.neutralColor}`);

for (const cat of vocab.categories) {
  if (!cat.id || ids.has(cat.id)) fail(`カテゴリ id が空か重複: ${cat.id}`);
  ids.add(cat.id);
  if (!cat.ja || !cat.en) fail(`カテゴリ ${cat.id} に ja/en が無い`);
  if (enNames.has(cat.en)) fail(`カテゴリの英語名が重複: ${cat.en}`);
  enNames.add(cat.en);
  if (!COLOR.test(cat.color ?? "")) fail(`カテゴリ ${cat.id} の color が #RRGGBB ではない`);
  if (jaOwner.has(cat.ja)) fail(`名前が重複: ${cat.ja}`);
  jaOwner.set(cat.ja, `カテゴリ ${cat.id}`);
  if (!Array.isArray(cat.terms) || cat.terms.length === 0) fail(`カテゴリ ${cat.id} に語が無い`);
}
for (const cat of vocab.categories) {
  for (const t of cat.terms) {
    if (!t.ja || !t.en) fail(`${cat.id}: ja/en が揃っていない語 ${JSON.stringify(t)}`);
    if (jaOwner.has(t.ja)) fail(`語が重複: ${t.ja}(${jaOwner.get(t.ja)} と ${cat.id})`);
    jaOwner.set(t.ja, `${cat.id}の語`);
    for (const w of t.match ?? []) {
      const key = w.toLowerCase();
      if (matchOwner.has(key) && matchOwner.get(key) !== t.ja) fail(`別表記が複数の語にある: ${w}(${matchOwner.get(key)} と ${t.ja})`);
      matchOwner.set(key, t.ja);
    }
  }
}
const current = new Set([...jaOwner.keys()]);
for (const [ja, v] of Object.entries(vocab.legacy)) {
  if (current.has(ja)) fail(`legacy の語が、現在の語と重複: ${ja}(現在の語に戻したなら legacy から消す)`);
  if (!v.en) fail(`legacy ${ja} に en が無い`);
  if (v.category && !ids.has(v.category)) fail(`legacy ${ja} の category が存在しない: ${v.category}`);
}

// 自動分類で、短すぎる別表記は誤判定のもと
const words = [];
for (const cat of vocab.categories) {
  for (const t of cat.terms.filter((t) => t.auto !== false)) words.push({ cat, term: t.ja, w: t.ja, isTerm: true }, ...(t.match ?? []).map((w) => ({ cat, term: t.ja, w })));
  for (const w of cat.match ?? []) words.push({ cat, term: "(カテゴリ)", w });
}
// (語そのもの(例: 桃)は、利用者が選ぶ語なので1文字でもよい)
for (const { cat, term, w, isTerm } of words) if (w.length < 2 && !isTerm) fail(`1文字の別表記は誤判定しやすい: ${w}(${cat.id} / ${term})`);

if (errors.length) {
  console.log(`風味語彙に問題が ${errors.length} 件あります:`);
  for (const e of errors) console.log("  - " + e);
  process.exitCode = 1;
} else {
  const nTerms = vocab.categories.reduce((n, c) => n + c.terms.length, 0);
  console.log(`OK: カテゴリ ${vocab.categories.length}・語 ${nTerms}・旧い語(legacy) ${Object.keys(vocab.legacy).length}`);
}

// 第1引数に、説明文の全文を含む商品データのパスを渡すと、そちらで数える。
// 公開する data/products.json には、店舗の長い説明文を載せていない(scripts/reduce-product-text.js)ため、既定では、短い記述だけが対象になる。
const productsFile = process.argv[2] ?? "data/products.json";
if (existsSync(productsFile)) {
  if (!process.argv[2]) console.log("注意: data/products.json には、短い風味の記述だけが載っています。出現数・カバー率は、目安にとどまります(全文の商品データのパスを、第1引数に渡せます)");
  const texts = JSON.parse(readFileSync(productsFile, "utf8")).map((p) => (p.flavor_notes ?? "").toLowerCase()).filter(Boolean);
  const hits = new Map();
  let classified = 0;
  for (const text of texts) {
    const cats = new Set();
    for (const { cat, w } of words) if (findAffirmedWord(text, [w.toLowerCase()])) cats.add(cat.id);
    if (cats.size) classified++;
  }
  console.log(`\n商品説明 ${texts.length} 件のうち、1つ以上のカテゴリに分類できた: ${classified} 件(${((classified / texts.length) * 100).toFixed(1)}%)`);
  for (const cat of vocab.categories) {
    const rows = cat.terms.map((t) => [t.auto === false ? `${t.ja}(自動分類なし)` : t.ja, t.auto === false ? 0 : texts.filter((x) => findAffirmedWord(x, [t.ja, ...(t.match ?? [])].map((w) => w.toLowerCase()))).length]);
    const total = texts.filter((x) => words.some((e) => e.cat === cat && findAffirmedWord(x, [e.w.toLowerCase()]))).length;
    console.log(`\n[${cat.ja}] 該当 ${total} 件`);
    console.log("  " + rows.map(([ja, n]) => `${ja} ${n}`).join(" / "));
    const zero = rows.filter(([ja, n]) => n === 0 && !ja.includes("自動分類なし")).map(([ja]) => ja);
    if (zero.length) console.log(`  (説明文に出ない語: ${zero.join("、")}。入力の選択肢としては使える)`);
  }
  void hits;
}
