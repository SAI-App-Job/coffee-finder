// docs/implemented-shops.md を data/shops.json・data/products.json から再生成する。
// 新しい店舗を実装したら、コミット前にこれを実行してインデックスを更新する。
//
//   node scripts/gen-implemented-shops.js
//
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const shops = JSON.parse(fs.readFileSync(path.join(ROOT, "data/shops.json"), "utf8"));
const products = JSON.parse(fs.readFileSync(path.join(ROOT, "data/products.json"), "utf8"));

function shortPlatform(p, isManual) {
  if (isManual) {
    if (!p) return "手動";
    if (p.includes("STORES")) return "STORES(手動)";
    if (p.includes("Tsuku2")) return "Tsuku2(手動)";
    if (p.includes("Wix")) return "Wix(手動)";
    if (p.includes("Instagram")) return "手動(SNSのみ)";
    return "手動";
  }
  if (!p) return "";
  if (p.startsWith("カラーミーショップ")) return "カラーミー";
  if (p.startsWith("おちゃのこネット")) return "Ocnk";
  if (p.startsWith("THE SHOP")) return "BASE(theshop)";
  if (p === "BASE") return "BASE";
  if (p.startsWith("Shopify")) return "Shopify";
  if (p === "EC-CUBE") return "EC-CUBE";
  if (p === "MakeShop") return "MakeShop";
  if (p === "ShopServe") return "ShopServe";
  if (p.startsWith("WordPress + USC")) return "WP+USCe";
  if (p.startsWith("WordPress + WooCommerce")) return "WooCommerce";
  if (p.startsWith("WordPress + Welcart")) return "Welcart";
  if (p.startsWith("WordPress")) return "WordPress";
  if (p === "Wix" || p.startsWith("Wix、")) return "Wix";
  if (p === "Goope") return "Goope";
  if (p.startsWith("crayon")) return "crayon";
  if (p.startsWith("独自HTML")) return "独自HTML";
  return p;
}

const rows = shops.map((s) => {
  const items = products.filter((p) => p.shop_name === s.name);
  const isManual = items.length > 0 && items.every((p) => p.data_source === "manual");
  return {
    name: s.name,
    prefecture: s.prefecture || "",
    address: (s.address || "").replace(s.prefecture || "", "").trim(),
    platform: shortPlatform(s.platform, isManual),
    count: items.length,
  };
});
rows.sort(
  (a, b) =>
    (a.prefecture || "").localeCompare(b.prefecture || "", "ja") ||
    (a.address || "").localeCompare(b.address || "", "ja")
);

const today = new Date().toISOString().slice(0, 10);
let out = "# 実装店舗インデックス\n\n";
out +=
  "`data/shops.json`・`data/products.json`から生成。件数は生成時点のスナップショット\n" +
  "(実際の最新値はdata/products.jsonを参照)。「方式」が「手動」の店舗は\n" +
  "`scraper/manual/shops/`配下、それ以外は`scraper/scrape_*.py`で自動取得。\n" +
  "実装を見送った店舗は`docs/not-implementable-shops.md`を参照。\n\n";
out += `合計${rows.length}店舗・${products.length}商品(生成日: ${today})。\n\n`;
out += "再生成コマンド:\n```\nnode scripts/gen-implemented-shops.js\n```\n";

let currentPref = null;
for (const r of rows) {
  if (r.prefecture !== currentPref) {
    out += "\n### " + (r.prefecture || "(所在地不明)") + "\n\n";
    out += "| 店舗名 | 所在地 | 方式 | 件数 |\n|---|---|---|---|\n";
    currentPref = r.prefecture;
  }
  out += `| ${r.name} | ${r.address} | ${r.platform} | ${r.count} |\n`;
}

fs.writeFileSync(path.join(ROOT, "docs/implemented-shops.md"), out);
console.log(`[done] docs/implemented-shops.md を更新しました(${rows.length}店舗・${products.length}商品)`);
