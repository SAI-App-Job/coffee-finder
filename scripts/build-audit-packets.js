// 検証担当の修正案(suggestedText)を、監査担当に渡す資料(パケット)にまとめる。
// 監査担当は、修正案の一文ずつが、確認済みの主張(claims)で裏付けられているかを確かめる。
// 出力: docs/ledger-drafts/audit/packets-<n>.json
import fs from "node:fs";
import path from "node:path";
import { createServer } from "vite";

const DRAFTS = "docs/ledger-drafts";
const OUT = path.join(DRAFTS, "audit");
const CHUNK = 34;

const sources = {};
const drafts = {};
for (const f of fs.readdirSync(DRAFTS).filter((x) => x.endsWith(".json")).sort()) {
  const j = JSON.parse(fs.readFileSync(path.join(DRAFTS, f), "utf8"));
  for (const [id, s] of Object.entries(j.sources ?? {})) sources[id] = sources[id] ?? s;
  for (const [key, e] of Object.entries(j.entries ?? {})) {
    if (!drafts[key] || (e.claims?.length ?? 0) > (drafts[key].claims?.length ?? 0)) drafts[key] = e;
  }
}

const server = await createServer({ server: { middlewareMode: true }, appType: "custom", logLevel: "error" });
const data = {
  facts: (await server.ssrLoadModule("/src/data/discoveryFacts.js")).DISCOVERY_FACTS,
  glossary: (await server.ssrLoadModule("/src/data/glossary.js")).GLOSSARY_TERMS,
  designated: (await server.ssrLoadModule("/src/data/designatedBrands.js")).DESIGNATED_BRANDS,
  expl: await server.ssrLoadModule("/src/data/explanations.js"),
  variety: (await server.ssrLoadModule("/src/data/varietyGuide.js")).VARIETY_GUIDE,
  brew: await server.ssrLoadModule("/src/data/brewGuide.js"),
  origin: (await server.ssrLoadModule("/src/data/originGuide.js")).ORIGIN_GUIDE,
  comps: (await server.ssrLoadModule("/src/data/japanCompetitions.js")).JAPAN_COMPETITIONS,
};
const { allItems } = await server.ssrLoadModule("/src/data/ledger/items.js");
const keys = new Set(allItems().map((i) => i.key));
await server.close();

const isDrop = (t) => !t || /^[((].*(表示不可|削除|公開しない|載せない)/s.test(t.trim());
const parseLabeled = (t) => {
  const out = {};
  for (const line of String(t).split("\n")) {
    const m = line.match(/^(tagline|varieties|note|summary|detail):\s*(.*)$/);
    if (m) out[m[1]] = m[2];
  }
  return out;
};

// 修正案を、画面の構造(content)の案にする
function proposal(key, d) {
  const s = d.suggestedText;
  const [kind, a, b, c] = key.split(":");
  if (kind === "fact") {
    const f = data.facts.find((x) => x.title === key.slice(5));
    return { title: f.title, text: String(s) };
  }
  if (kind === "glossary") {
    const t = String(s);
    const sm = t.match(/【要約】([\s\S]*?)(?=【詳細】|$)/);
    const dm = t.match(/【詳細】([\s\S]*)$/);
    return { summary: sm ? sm[1].trim() : "", detail: dm ? dm[1].trim() : "", _parsed: Boolean(sm && dm) };
  }
  if (kind === "brew") {
    const { note, ...rest } = typeof s === "object" ? s : {};
    return rest;
  }
  if (kind === "extraction" || kind === "diagnosis") {
    const { note, ...rest } = typeof s === "object" ? s : {};
    return rest;
  }
  if (kind === "variety") {
    const p = parseLabeled(s);
    return { tagline: p.tagline ?? "", varieties: (p.varieties ?? "").split(/[、,]/).map((x) => x.trim()).filter(Boolean), note: p.note ?? "" };
  }
  if (kind === "brand") {
    const brand = data.designated.find((x) => x.name === key.slice(6));
    return { note: brand?.note ?? null, explanation: String(s) };
  }
  if (kind === "processing") return { explanation: String(s) };
  if (kind === "grade") return { text: String(s) };
  if (kind === "competition") return { text: String(s) };
  if (kind === "origin") return b === "sub" ? { detail: String(s) } : { text: String(s) };
  return null;
}

const packets = [];
const skipped = [];
for (const [key, d] of Object.entries(drafts).sort()) {
  if (!keys.has(key)) continue;
  if (key.startsWith("event:") || key.startsWith("flavorwheel:")) {
    skipped.push([key, "ledger対象外または構造の修正が必要"]);
    continue;
  }
  if (d.status === "verified") continue; // 現在の本文のまま取り込み済み
  if (d.suggestedText === undefined || (typeof d.suggestedText === "string" && isDrop(d.suggestedText))) {
    skipped.push([key, "修正案なし/削除"]);
    continue;
  }
  const claims = (d.claims ?? []).map((c, i) => ({ index: i, text: c.text, status: c.status, quote: c.quote ?? "", location: c.location ?? "", sourceIds: c.sourceIds ?? [] }));
  const verified = claims.filter((c) => c.status === "verified");
  const rejected = claims.filter((c) => c.status !== "verified").map((c) => ({ text: c.text, status: c.status }));
  const used = new Set(verified.flatMap((c) => c.sourceIds));
  packets.push({
    key,
    proposed: proposal(key, d),
    verifiedClaims: verified,
    rejectedClaims: rejected,
    sources: Object.fromEntries([...used].map((id) => [id, { title: sources[id]?.title, org: sources[id]?.org, kind: sources[id]?.kind, readMethod: sources[id]?.readMethod }])),
    verifierNote: d.note ?? "",
  });
}
fs.rmSync(OUT, { recursive: true, force: true });
fs.mkdirSync(OUT, { recursive: true });
const chunks = [];
for (let i = 0; i < packets.length; i += CHUNK) chunks.push(packets.slice(i, i + CHUNK));
chunks.forEach((c, i) => fs.writeFileSync(path.join(OUT, `packets-${i + 1}.json`), JSON.stringify(c, null, 1)));
console.log(`パケット ${packets.length} 件 → ${chunks.length} ファイル`);
console.log(`対象外 ${skipped.length} 件`);
skipped.forEach(([k, why]) => console.log(`  ${k}: ${why}`));
