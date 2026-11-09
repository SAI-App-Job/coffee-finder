// 出典の台帳の検査(docs/research-rules.md)。
//  - 台帳に矛盾があれば失敗: 存在しない資料の参照、検証した本文と違う本文、画面に出ない状態の「verified」など
//  - 台帳の無い記述は「非表示」として数える(失敗にはしない。画面には出ない)
// 使い方: npm run sources:check [-- --list]  (--list で非表示の記述の一覧を出す)
import { createServer } from "vite";

const list = process.argv.includes("--list");
const server = await createServer({ server: { middlewareMode: true }, appType: "custom", logLevel: "error" });
let failed = false;
const fail = (message) => {
  failed = true;
  console.error(`NG: ${message}`);
};

try {
  const items = (await server.ssrLoadModule("/src/data/ledger/items.js")).allItems();
  const ledger = await server.ssrLoadModule("/src/data/ledger/index.js");
  const { PROSE } = await server.ssrLoadModule("/src/data/ledger/prose.js");
  const { EN } = await server.ssrLoadModule("/src/i18n/en.js");

  const itemKeys = new Set(items.map((item) => item.key));
  const entries = ledger.LEDGER_ENTRIES;
  const sources = ledger.LEDGER_SOURCES;

  // 資料の記録の形
  for (const [id, source] of Object.entries(sources)) {
    for (const field of ["title", "org", "url", "kind", "readMethod", "accessed"]) {
      if (!source[field]) fail(`資料 ${id} に ${field} が無い`);
    }
    if (!["primary", "secondary"].includes(source.kind)) fail(`資料 ${id} の kind が不正: ${source.kind}`);
    if (!["full-text", "excerpt", "snippet", "failed"].includes(source.readMethod)) fail(`資料 ${id} の readMethod が不正`);
  }

  // 台帳の記述
  for (const [key, entry] of Object.entries(entries)) {
    if (!itemKeys.has(key)) {
      fail(`台帳のキーに対応する記述が無い(古い台帳か、キーの誤り): ${key}`);
      continue;
    }
    for (const claim of entry.claims ?? []) {
      for (const id of claim.sourceIds ?? []) {
        if (!sources[id]) fail(`${key}: 存在しない資料を参照している: ${id}`);
      }
      if (claim.status === "verified" && !(claim.quote && claim.location)) fail(`${key}: verified の主張に quote か location が無い: ${claim.text}`);
    }
    if (entry.status === "verified") {
      const item = items.find((it) => it.key === key);
      const state = ledger.publishState(key, item.text);
      if (!state.ok) fail(`${key}: verified だが表示できない状態: ${state.reason}`);
    }
  }

  // 画面の説明文(prose)の英訳
  for (const [id, text] of Object.entries(PROSE)) {
    if (!EN[text]) fail(`prose:${id} の英訳が辞書に無い`);
  }

  const shown = items.filter((item) => ledger.isPublishable(item.key, item.text));
  const hidden = items.filter((item) => !ledger.isPublishable(item.key, item.text));
  console.log(`記述 ${items.length} 件: 表示 ${shown.length} / 非表示(出典の確認が未了) ${hidden.length}`);
  if (list) hidden.forEach((item) => console.log(`  非表示: ${item.key}`));
  console.log(failed ? "台帳に矛盾があります。" : "台帳に矛盾はありません。");
} finally {
  await server.close();
}
process.exit(failed ? 1 : 0);
