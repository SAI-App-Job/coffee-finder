// 検証担当の下書き(docs/ledger-drafts/*.json)から、画面に出してよい記述だけを台帳(src/data/ledger/)へ取り込む。
// - 取り込むのは次の2種類だけ:
//     1. 「全主張が verified」の記述(現在の本文のまま表示できるもの)
//     2. 監査担当が pass/edit とした記述(監査後の内容 finalContent を表示する。docs/ledger-drafts/audit/)
// - 一部しか確認できていない記述(partial)で監査を通らなかったものと、未確認の記述は、台帳に入れない(画面に出ない)。
// - ユーザーが承認した資料の扱い(docs/research-rules.md)を、ここで適用する:
//     * ICOなどが各国規格の数字を転記しているだけの資料は、根拠にしない(下の TRANSCRIPTION_URLS)
//     * 企業・団体の自己申告ページは、その団体自身についての主張にだけ使う(下の SELF_REPORTED)
// 使い方: node scripts/merge-ledger.js   (結果は src/data/ledger/{sources,entries}.json)
import fs from "node:fs";
import path from "node:path";
import { createServer } from "vite";

const DRAFTS = "docs/ledger-drafts";
const OUT = "src/data/ledger";

const TRANSCRIPTION_URLS = ["icc-122-12e-national-quality-standards"];
const SELF_REPORTED = {
  "qima-yemenia-page": /Qima/,
  "qima-yemen-page": /Qima/,
  "kcfa-ecological-profile": /コナ・コーヒー農家協会|KCFA/,
  "descamex-procesos": /Descamex/,
  "descamex-home": /Descamex/,
};

const files = fs.readdirSync(DRAFTS).filter((f) => f.endsWith(".json")).sort();
const sources = {};
const drafts = {};
for (const f of files) {
  const j = JSON.parse(fs.readFileSync(path.join(DRAFTS, f), "utf8"));
  for (const [id, s] of Object.entries(j.sources ?? {})) sources[id] = sources[id] ?? s;
  for (const [key, e] of Object.entries(j.entries ?? {})) {
    // 同じキーが複数あれば、主張の多いほうを採る
    if (!drafts[key] || (e.claims?.length ?? 0) > (drafts[key].claims?.length ?? 0)) drafts[key] = e;
  }
}

const server = await createServer({ server: { middlewareMode: true }, appType: "custom", logLevel: "error" });
const { allItems } = await server.ssrLoadModule("/src/data/ledger/items.js");
const { hashText } = await server.ssrLoadModule("/src/data/ledger/index.js");
const items = new Map(allItems().map((item) => [item.key, item]));
await server.close();

const isTranscription = (id) => TRANSCRIPTION_URLS.some((u) => (sources[id]?.url ?? "").includes(u));
const backs = (claim) => {
  const usable = [];
  for (const id of claim.sourceIds ?? []) {
    const s = sources[id];
    if (!s || s.kind !== "primary" || s.readMethod !== "full-text") continue;
    if (isTranscription(id)) continue;
    if (SELF_REPORTED[id] && !SELF_REPORTED[id].test(claim.text)) continue;
    usable.push(id);
  }
  return usable;
};

const entries = {};
const report = { merged: [], demoted: [], notVerified: 0, unknownKey: [] };
for (const [key, draft] of Object.entries(drafts)) {
  const item = items.get(key);
  if (!item) {
    report.unknownKey.push(key);
    continue;
  }
  if (draft.status !== "verified") {
    report.notVerified++;
    continue;
  }
  const claims = (draft.claims ?? []).map((c) => ({ ...c, usable: backs(c) }));
  const bad = claims.filter((c) => c.status !== "verified" || c.usable.length === 0 || !c.quote || !c.location);
  if (bad.length) {
    report.demoted.push({ key, claims: bad.map((c) => c.text) });
    continue;
  }
  entries[key] = {
    status: "verified",
    textHash: hashText(item.text),
    claims: claims.map((c) => ({ text: c.text, status: "verified", sourceIds: c.usable, quote: c.quote, location: c.location })),
  };
  report.merged.push(key);
}

// 監査を経た記述(pass / edit)
const AUDIT = path.join(DRAFTS, "audit");
const packets = {};
const results = {};
if (fs.existsSync(AUDIT)) {
  for (const f of fs.readdirSync(AUDIT).sort()) {
    const j = JSON.parse(fs.readFileSync(path.join(AUDIT, f), "utf8"));
    if (f.startsWith("packets-")) for (const p of j) packets[p.key] = p;
    if (f.startsWith("results-")) Object.assign(results, j.results ?? {});
  }
}
const audit = { merged: [], rejected: [], dropped: [], missing: [] };
const nonEmpty = (v) => typeof v === "string" && v.trim().length > 0;
function validContent(key, c) {
  if (!c || typeof c !== "object") return "内容が無い";
  const kind = key.split(":")[0];
  if (kind === "fact") return nonEmpty(c.title) && nonEmpty(c.text) ? "" : "title/text が空";
  if (kind === "glossary") return nonEmpty(c.summary) || nonEmpty(c.detail) ? "" : "summary/detail が空";
  if (kind === "origin") return key.includes(":sub:") ? (nonEmpty(c.detail) ? "" : "detail が空") : nonEmpty(c.text) ? "" : "text が空";
  if (kind === "variety") return nonEmpty(c.note) || nonEmpty(c.tagline) ? "" : "内容が空";
  if (kind === "brand") return nonEmpty(c.explanation) ? "" : "explanation が空";
  if (kind === "processing") return nonEmpty(c.explanation) ? "" : "explanation が空";
  if (kind === "grade" || kind === "competition") return nonEmpty(c.text) ? "" : "text が空";
  if (["brew", "extraction", "diagnosis"].includes(kind)) return Object.values(c).some((v) => (Array.isArray(v) ? v.length : nonEmpty(v))) ? "" : "内容が空";
  return "未対応の種類";
}
for (const [key, packet] of Object.entries(packets)) {
  if (entries[key]) continue;
  const r = results[key];
  const draft = drafts[key];
  if (!r) {
    audit.missing.push(key);
    continue;
  }
  if (r.verdict === "drop") {
    audit.dropped.push(key);
    continue;
  }
  const content = r.verdict === "pass" ? packet.proposed : r.finalContent;
  const problem = validContent(key, content);
  const used = (r.usedClaims ?? []).map((i) => draft?.claims?.[i]);
  if (problem || !used.length || used.some((c) => !c || c.status !== "verified")) {
    audit.rejected.push([key, problem || "使った主張が不正"]);
    continue;
  }
  const claims = used.map((c) => ({ ...c, usable: backs(c) }));
  const bad = claims.filter((c) => c.usable.length === 0 || !c.quote || !c.location);
  if (bad.length) {
    audit.rejected.push([key, `根拠にできない主張: ${bad.map((c) => c.text).join(" / ")}`]);
    continue;
  }
  const { _parsed, ...clean } = content;
  entries[key] = {
    status: "verified",
    content: clean,
    textHash: hashText(JSON.stringify(clean)),
    claims: claims.map((c) => ({ text: c.text, status: "verified", sourceIds: c.usable, quote: c.quote, location: c.location })),
  };
  audit.merged.push(key);
}

// 再監査(reresults-*.json): 監査後の内容をもう一度確かめた結果。fix は内容を差し替え、drop は取り下げる。
const reaudit = { ok: 0, fixed: [], dropped: [], rejected: [], missing: [] };
if (fs.existsSync(AUDIT)) {
  const rr = {};
  for (const f of fs.readdirSync(AUDIT).sort()) {
    if (f.startsWith("reresults-")) Object.assign(rr, JSON.parse(fs.readFileSync(path.join(AUDIT, f), "utf8")).results ?? {});
  }
  const reRan = Object.keys(rr).length > 0;
  for (const [key, entry] of Object.entries({ ...entries })) {
    if (!entry.content) continue;
    const r = rr[key];
    if (!r) {
      if (reRan) reaudit.missing.push(key);
      continue;
    }
    if (r.verdict === "ok") {
      reaudit.ok++;
      continue;
    }
    if (r.verdict === "drop") {
      delete entries[key];
      reaudit.dropped.push(key);
      continue;
    }
    const problem = validContent(key, r.finalContent);
    const used = (r.usedClaims ?? []).map((i) => entry.claims[i]);
    if (problem || !used.length || used.some((c) => !c)) {
      delete entries[key];
      reaudit.rejected.push([key, problem || "使った主張が不正"]);
      continue;
    }
    const { _parsed, ...clean } = r.finalContent;
    entries[key] = { status: "verified", content: clean, textHash: hashText(JSON.stringify(clean)), claims: used };
    reaudit.fixed.push(key);
  }
}

// 英訳(docs/ledger-drafts/translations/): 翻訳した時点の内容(packets)が、いまの内容と同じ記述にだけ付ける。
// 日本語の内容が変わっていたら付けない(英語表示では日本語を出す)。
const TRANS = path.join(DRAFTS, "translations");
const tr = { attached: 0, stale: [], badShape: [], missing: [], numberReview: [] };
if (fs.existsSync(TRANS)) {
  const tpackets = {};
  const trans = {};
  for (const f of fs.readdirSync(TRANS).sort()) {
    const j = JSON.parse(fs.readFileSync(path.join(TRANS, f), "utf8"));
    if (f.startsWith("packets-")) for (const p of j) tpackets[p.key] = p.content;
    if (f.startsWith("translations-")) Object.assign(trans, j.translations ?? {});
  }
  // 人名は「漢字+(姓)」の併記を許す(例: 新田千香子 (Nitta))。それ以外に日本語が残っていたら不可
  const hasJa = (v) =>
    Array.isArray(v) ? v.some(hasJa) : v && typeof v === "object" ? Object.values(v).some(hasJa) : typeof v === "string" && /[぀-ヿ㐀-鿿]/.test(v.replace(/[぀-ヿ㐀-鿿]+(?= \()/g, "").replace(/\([^)]*[぀-ヿ㐀-鿿][^)]*\)/g, ""));
  const sameShape = (a, b) =>
    Array.isArray(a) ? Array.isArray(b) && a.length === b.length && a.every((x, i) => sameShape(x, b[i])) :
    a && typeof a === "object" ? b && typeof b === "object" && Object.keys(a).sort().join() === Object.keys(b).sort().join() && Object.keys(a).every((k) => sameShape(a[k], b[k])) :
    typeof a === typeof b;
  const flat = (v) => (Array.isArray(v) ? v.map(flat).join(" ") : v && typeof v === "object" ? Object.values(v).map(flat).join(" ") : String(v ?? ""));
  const MONTHS = { January: 1, February: 2, March: 3, April: 4, May: 5, June: 6, July: 7, August: 8, September: 9, October: 10, November: 11, December: 12 };
  const WORDS = { one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10, eleven: 11, twelve: 12, thirty: 30, forty: 40, fifty: 50 };
  const digits = (t) => {
    let u = t.replace(/,/g, "");
    // 英訳が月名・数詞で書いた数字も、数字として数える
    u = u.replace(new RegExp(Object.keys(MONTHS).join("|"), "g"), (m) => ` ${MONTHS[m]} `);
    u = u.replace(new RegExp(`\b(${Object.keys(WORDS).join("|")})\b`, "gi"), (m) => ` ${WORDS[m.toLowerCase()]} `);
    // 日本語の「万」「分の」は、数字の表記が変わるので比べない
    return [...new Set(u.match(/\d+(?:\.\d+)?/g) ?? [])];
  };
  for (const [key, entry] of Object.entries(entries)) {
    if (!entry.content) continue;
    const t = trans[key];
    if (!t || !tpackets[key]) {
      tr.missing.push(key);
      continue;
    }
    if (JSON.stringify(tpackets[key]) !== JSON.stringify(entry.content)) {
      tr.stale.push(key);
      continue;
    }
    if (!sameShape(entry.content, t.en) || hasJa(t.en)) {
      tr.badShape.push(key);
      continue;
    }
    const jaText = flat(entry.content).replace(/(\d+(?:[.,]\d+)?)\s*(万|千|分の)/g, " ").replace(/(\d+)\s*[〜~]\s*(\d+)\s*月/g, "$1 $2 月");
    const ja = digits(jaText);
    const en = new Set(digits(flat(t.en)));
    const lost = ja.filter((d) => !en.has(d));
    if (lost.length) tr.numberReview.push([key, lost.join(",")]);
    entry.contentEn = t.en;
    tr.attached++;
  }
}

const usedIds = new Set(Object.values(entries).flatMap((e) => e.claims.flatMap((c) => c.sourceIds)));
const outSources = {};
for (const id of [...usedIds].sort()) {
  const { title, org, url, kind, readMethod, accessed, note } = sources[id];
  outSources[id] = { title, org, url, kind, readMethod, accessed, ...(note ? { note } : {}) };
}
fs.writeFileSync(path.join(OUT, "sources.json"), JSON.stringify(outSources, null, 1) + "\n");
fs.writeFileSync(path.join(OUT, "entries.json"), JSON.stringify(entries, null, 1) + "\n");

console.log(`取り込み: ${report.merged.length} 件 / 資料 ${usedIds.size} 件`);
console.log(`下書きで全主張が verified だったが、資料の扱いの規則で外した: ${report.demoted.length} 件`);
report.demoted.forEach((d) => console.log(`  外した: ${d.key}  (${d.claims.length} 主張)`));
console.log(`一部のみ確認または未確認(台帳に入れない): ${report.notVerified} 件`);
if (report.unknownKey.length) {
  console.log(`対応する記述が無いキー: ${report.unknownKey.length} 件`);
  report.unknownKey.forEach((k) => console.log(`  ${k}`));
}
console.log(`監査を経て取り込み: ${audit.merged.length} 件 / 出さない(drop): ${audit.dropped.length} 件 / 規則で外した: ${audit.rejected.length} 件 / 結果なし: ${audit.missing.length} 件`);
audit.rejected.forEach(([k, why]) => console.log(`  外した: ${k}  (${why})`));
audit.missing.forEach((k) => console.log(`  結果なし: ${k}`));
console.log(`再監査: ok ${reaudit.ok} 件 / 直した ${reaudit.fixed.length} 件 / 取り下げ ${reaudit.dropped.length} 件 / 不正で外した ${reaudit.rejected.length} 件 / 結果なし ${reaudit.missing.length} 件`);
reaudit.dropped.forEach((k) => console.log(`  再監査で取り下げ: ${k}`));
reaudit.rejected.forEach(([k, why]) => console.log(`  再監査の結果が不正: ${k} (${why})`));
console.log(`英訳: 付けた ${tr.attached} 件 / 翻訳後に日本語が変わった ${tr.stale.length} 件 / 構造不一致または日本語が残った ${tr.badShape.length} 件 / 未翻訳 ${tr.missing.length} 件`);
tr.badShape.forEach((k) => console.log(`  英訳を付けない(構造/日本語): ${k}`));
console.log(`英訳で日本語の数字が見当たらない記述(要目視 ${tr.numberReview.length} 件):`);
tr.numberReview.forEach(([k, d]) => console.log(`  ${k}: ${d}`));
console.log("取り込んだキー(現在の本文のまま):");
report.merged.forEach((k) => console.log(`  ${k}`));
