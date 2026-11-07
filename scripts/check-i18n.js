// 英語の辞書(src/i18n/en.js)の漏れを調べる: npm run i18n:check
// - ソース内の t("…") / translate("…") / <Trans k="…"> に使われている日本語の文のうち、辞書に無いものを一覧にする。
// - 見つかったら終了コード1で終わる(辞書に足すか、翻訳しない文なら無視してよいか確認する)。
// - 変数を渡す t(label) のような呼び方は調べられない。その種類のラベルは、辞書の LABELS / 用語の節に直接足す。
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const JP = /[぀-ヿ一-鿿]/;
const CALL = /(?<![\w.$])(?:t|translate)\(\s*("(?:[^"\\]|\\.)*")/g;
const TRANS = /<Trans\s+k="((?:[^"\\]|\\.)*)"/g;

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) {
      if (name !== "i18n") walk(path, out);
    } else if (/\.(js|jsx)$/.test(name)) {
      out.push(path);
    }
  }
  return out;
}

const { EN } = await import(pathToFileURL(join("src", "i18n", "en.js")).href);
const used = new Map();
for (const file of walk("src")) {
  const text = readFileSync(file, "utf8");
  for (const m of text.matchAll(CALL)) used.set(JSON.parse(m[1]), file);
  for (const m of text.matchAll(TRANS)) used.set(JSON.parse(`"${m[1]}"`), file);
}

const missing = [...used].filter(([key]) => JP.test(key) && !(key in EN));
if (missing.length === 0) {
  console.log(`OK: ${used.size} 個の文が、すべて辞書にあります。`);
} else {
  console.log(`辞書に無い文が ${missing.length} 件あります:`);
  for (const [key, file] of missing) console.log(`  ${JSON.stringify(key)}  (${file})`);
  process.exitCode = 1;
}
