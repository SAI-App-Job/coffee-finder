// 商品データ(data/products.json)から、店舗が書いた長い説明文を取り除き、アプリが抽出した事実だけにする。
//   node scripts/reduce-product-text.js [--check]
//
// 目的: 店舗が書いた紹介文(著作物になりうる長い文章)を、アプリで全文表示したり、公開リポジトリで配ったりしない。
//   - flavor_notes(味わいの説明): 短い風味の列挙・短文(60字以内・句点と改行なし)だけを残し、それ以外は null にする。
//     残す・残さないに関わらず、説明文から、アプリ独自の風味語彙で判定した結果(事実)を、次の欄に入れる(src/utils/flavor.js と同じ判定):
//       flavor_terms          : [[風味の語(日本語), 説明文に載っていた表記], ...]
//       flavor_category_only  : 語は特定できず、カテゴリだけに分類されたカテゴリの id
//   - farm_note(農園情報): 農園名・生産者名・標高などの短い情報は残し、句点・改行を含む文章や200字を超えるものは null にする。
// 何度実行しても同じ結果になる(すでに取り除いた後は、何もしない)。
// 週次の集約(scraper/aggregate_shops.py)のあとに、毎回実行する(.github/workflows/scrape-shops.yml)。
// --check: ファイルは書き換えず、まだ取り除いていない長文があれば、終了コード1で終わる。
import { register } from "node:module";
import { readFileSync, writeFileSync } from "node:fs";

register("./lib/resolve-extensionless.mjs", import.meta.url);
const { analyzeFlavorNotes } = await import("../src/utils/flavor.js");

const FILE = "data/products.json";
const FLAVOR_KEEP_MAX = 60;
const FARM_KEEP_MAX = 200;

const isProse = (t) => /[。\n\r]/.test(t);
const keepFlavor = (t) => t.length <= FLAVOR_KEEP_MAX && !isProse(t);
const keepFarm = (t) => t.length <= FARM_KEEP_MAX && !isProse(t);

const checkOnly = process.argv.includes("--check");
const products = JSON.parse(readFileSync(FILE, "utf8"));
const stat = { analyzed: 0, flavorDropped: 0, flavorKept: 0, farmDropped: 0, farmKept: 0, pending: 0 };

for (const p of products) {
  const notes = typeof p.flavor_notes === "string" && p.flavor_notes.trim() ? p.flavor_notes : null;
  if (notes) {
    if (!keepFlavor(notes)) stat.pending++;
    if (!checkOnly) {
      const a = analyzeFlavorNotes(notes);
      p.flavor_terms = a.terms.map((x) => [x.ja, x.word]);
      p.flavor_category_only = a.categoryOnly.map((c) => c.id);
      stat.analyzed++;
      if (keepFlavor(notes)) stat.flavorKept++;
      else {
        p.flavor_notes = null;
        stat.flavorDropped++;
      }
    }
  }
  const farm = typeof p.farm_note === "string" && p.farm_note.trim() ? p.farm_note : null;
  if (farm) {
    if (!keepFarm(farm)) stat.pending++;
    if (!checkOnly) {
      if (keepFarm(farm)) stat.farmKept++;
      else {
        p.farm_note = null;
        stat.farmDropped++;
      }
    }
  }
}

if (checkOnly) {
  console.log(`まだ取り除いていない長文: ${stat.pending} 件`);
  process.exitCode = stat.pending > 0 ? 1 : 0;
} else {
  writeFileSync(FILE, JSON.stringify(products, null, 2) + "\n", "utf8");
  console.log(`商品 ${products.length} 件 / 風味の判定 ${stat.analyzed} 件 / 味わいの説明: 残した ${stat.flavorKept}・取り除いた ${stat.flavorDropped} / 農園情報: 残した ${stat.farmKept}・取り除いた ${stat.farmDropped}`);
}
