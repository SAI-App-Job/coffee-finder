// 器具カタログ(data/tools.json)の検査: npm run tools:check
// - 必須の項目(id・種類・メーカー・名前・URL・確認日・資料ID)があるか
// - JAN(GTIN)の桁数とチェックデジットが正しいか
// - 出典の原文(source-archive/<資料ID>)が、この端末にあるか(無ければ警告のみ。原文はgit管理外のため)
// - 同じJANが、別の商品に付いていないか(公式の情報でそうなっている場合は、警告として出す)
import { readFileSync, existsSync } from "node:fs";

const KINDS = ["dripper", "paper", "grinder"];
const catalog = JSON.parse(readFileSync("data/tools.json", "utf8"));
let errors = 0;
const warn = (m) => console.log(`  警告: ${m}`);
const fail = (m) => {
  console.log(`  エラー: ${m}`);
  errors++;
};

function validGtin(value) {
  const d = String(value);
  if (!/^\d+$/.test(d) || ![8, 12, 13, 14].includes(d.length)) return false;
  const body = d.slice(0, -1);
  let sum = 0;
  for (let i = 0; i < body.length; i++) sum += Number(body[body.length - 1 - i]) * (i % 2 === 0 ? 3 : 1);
  return (10 - (sum % 10)) % 10 === Number(d.at(-1));
}

const ids = new Set();
const gtins = new Map();
const missingArchive = new Set();
for (const item of catalog.items) {
  const where = `${item.id ?? "(idなし)"} ${item.name ?? ""}`;
  for (const key of ["id", "kind", "maker", "name", "url", "checkedAt", "sourceId"]) {
    if (!item[key]) fail(`${where}: ${key} が空です`);
  }
  if (!KINDS.includes(item.kind)) fail(`${where}: 種類が不正です(${item.kind})`);
  if (ids.has(item.id)) fail(`${where}: idが重複しています`);
  ids.add(item.id);
  if (!/^https:\/\//.test(item.url ?? "")) fail(`${where}: URLが https:// ではありません`);
  if (!Array.isArray(item.variants) || item.variants.length === 0) fail(`${where}: variants がありません`);
  for (const v of item.variants ?? []) {
    if (v.gtin) {
      if (!validGtin(v.gtin)) fail(`${where}: JANが不正です(${v.gtin})`);
      gtins.set(v.gtin, [...(gtins.get(v.gtin) ?? []), `${item.name}${v.label ? " " + v.label : ""}`]);
    }
  }
  if (item.sourceId && !existsSync(`source-archive/${item.sourceId}`)) missingArchive.add(item.sourceId);
  if (item.gtinSourceId && !existsSync(`source-archive/${item.gtinSourceId}`)) missingArchive.add(item.gtinSourceId);
}
for (const [g, names] of gtins) if (names.length > 1) warn(`同じJAN ${g} が複数の商品に付いています: ${names.join(" / ")}`);
for (const id of missingArchive) warn(`出典の原文 source-archive/${id} が、この端末にありません`);

const byMaker = {};
for (const item of catalog.items) {
  const m = (byMaker[item.maker] ??= { items: 0, variants: 0, gtins: 0 });
  m.items++;
  for (const v of item.variants ?? []) {
    m.variants++;
    if (v.gtin) m.gtins++;
  }
}
console.log(`器具カタログ: ${catalog.items.length} 件(更新日 ${catalog.updatedAt ?? "不明"})`);
for (const [maker, m] of Object.entries(byMaker)) console.log(`  ${maker}: ${m.items}製品 / ${m.variants}型番 / JANあり ${m.gtins}`);
if (errors) {
  console.log(`エラー ${errors} 件`);
  process.exitCode = 1;
} else {
  console.log("OK");
}
