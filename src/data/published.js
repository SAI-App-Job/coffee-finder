// 画面に出してよい記述だけを集めたデータ。出典のない記述は、ここで取り除かれる。
// 判定は src/data/ledger(台帳)。ルールは docs/research-rules.md。
// 画面は、各データ(discoveryFacts.jsなど)を直接使わず、必ずここを通す。
//
// 台帳に「内容(content)」がある記述は、監査を経て直した内容を表示する(データ側の本文は使わない)。
// その英訳(contentEn)があれば _en に付ける。英訳が無ければ、英語表示でも日本語の内容を出す。
import { isPublishable, contentOf, contentEnOf } from "./ledger";
import { getLang } from "../i18n";
import { DISCOVERY_FACTS } from "./discoveryFacts";
import { GLOSSARY_TERMS } from "./glossary";
import { BREW_METHODS, EXTRACTION_VARIABLES, EXTRACTION_DIAGNOSIS } from "./brewGuide";
import { VARIETY_GUIDE } from "./varietyGuide";
import { DESIGNATED_BRANDS } from "./designatedBrands";
import { JAPAN_COMPETITIONS } from "./japanCompetitions";
import { PROCESSING_EXPLANATIONS } from "./explanations";
import {
  ORIGIN_FIELDS,
  COMPETITION_FIELDS,
  factItem,
  glossaryItem,
  brewItem,
  extractionItem,
  diagnosisItem,
  originFieldItem,
  originSubItem,
  varietyItem,
  brandItem,
  processingItem,
  competitionItem,
  proseItem,
} from "./ledger/items";
import { PROSE } from "./ledger/prose";

const ok = ({ key, text }) => isPublishable(key, text);

// 出してよい記述だけ返す。台帳に内容があれば、その内容に差し替える。出せなければ null
function publish(raw, item, build) {
  if (!ok(item)) return null;
  const content = contentOf(item.key);
  if (!content) return raw;
  return { ...build(raw, content), _ledger: true, _en: contentEnOf(item.key) };
}

export const PUBLISHED_FACTS = DISCOVERY_FACTS.map((f) =>
  publish(f, factItem(f), (r, c) => ({ ...r, title: c.title ?? r.title, text: c.text }))
).filter(Boolean);

export const PUBLISHED_GLOSSARY_TERMS = GLOSSARY_TERMS.map((g) =>
  publish(g, glossaryItem(g), (r, c) => ({ ...r, summary: c.summary ?? "", detail: c.detail ?? "" }))
).filter(Boolean);

// 淹れ方・抽出理論は、確認できた欄だけを出す(無い欄は空にする)
export const PUBLISHED_BREW_METHODS = BREW_METHODS.map((b) =>
  publish(b, brewItem(b), (r, c) => ({
    ...r,
    tagline: "",
    ratio: "",
    temp: "",
    time: "",
    grindSize: "",
    steps: [],
    pairing: "",
    calibration: "",
    ...c,
  }))
).filter(Boolean);
export const PUBLISHED_EXTRACTION_VARIABLES = EXTRACTION_VARIABLES.map((v) =>
  publish(v, extractionItem(v), (r, c) => ({ ...r, summary: "", detail: "", ...c }))
).filter(Boolean);
export const PUBLISHED_EXTRACTION_DIAGNOSIS = EXTRACTION_DIAGNOSIS.map((d) =>
  publish(d, diagnosisItem(d), (r, c) => ({ ...r, cause: "", taste: "", ...c }))
).filter(Boolean);

export const PUBLISHED_VARIETIES = VARIETY_GUIDE.map((v) =>
  publish(v, varietyItem(v), (r, c) => ({ ...r, tagline: c.tagline ?? "", varieties: c.varieties ?? [], note: c.note ?? "" }))
).filter(Boolean);

// 特定銘柄。explanation は、商品タグの解説にも使う
export const PUBLISHED_DESIGNATED_BRANDS = DESIGNATED_BRANDS.map((b) =>
  publish(b, brandItem(b), (r, c) => ({ ...r, note: c.note ?? null, explanation: c.explanation ?? "" }))
).filter(Boolean);

/** 精選方法の解説(日本語)と、その英訳。出せなければ null */
export function publishedProcessing(name) {
  if (!PROCESSING_EXPLANATIONS[name]) return null;
  const item = processingItem(name);
  if (!ok(item)) return null;
  const content = contentOf(item.key);
  const en = contentEnOf(item.key);
  return {
    ja: content ? content.explanation : PROCESSING_EXPLANATIONS[name],
    en: en?.explanation ?? null,
    key: item.key,
    overridden: Boolean(content),
  };
}

// 台帳のキー(出典の表示に使う)
export const factKey = (f) => factItem(f).key;
export const glossaryKey = (g) => glossaryItem(g).key;
export const brewKey = (b) => brewItem(b).key;
export const extractionKey = (v) => extractionItem(v).key;
export const diagnosisKey = (d) => diagnosisItem(d).key;
export const varietyKey = (v) => varietyItem(v).key;
export const brandKey = (b) => brandItem(b).key;

/**
 * 産地ガイドの1か国分。出典を確認できていない項目は取り除く(空になる)。
 * keys は、残った項目の台帳のキー(出典の表示に使う)。
 * en は、台帳に英訳がある項目の英訳(英語表示用)。
 */
export function publishedOrigin(origin) {
  const keys = [];
  const en = { subs: {} };
  const result = { ...origin };
  for (const field of ORIGIN_FIELDS) {
    if (!origin[field]) continue;
    const item = originFieldItem(origin.country, field, origin[field]);
    if (!ok(item)) {
      result[field] = "";
      continue;
    }
    keys.push(item.key);
    const content = contentOf(item.key);
    if (content) result[field] = content.text;
    const contentEn = contentEnOf(item.key);
    if (contentEn?.text) en[field] = contentEn.text;
  }
  result.subRegions = (origin.subRegions ?? [])
    .filter((sub) => ok(originSubItem(origin.country, sub)))
    .map((sub) => {
      const item = originSubItem(origin.country, sub);
      keys.push(item.key);
      const content = contentOf(item.key);
      const contentEn = contentEnOf(item.key);
      if (contentEn?.detail) en.subs[sub.name] = contentEn.detail;
      return content ? { ...sub, detail: content.detail } : sub;
    });
  return { ...result, keys, en };
}

/** 言語に合わせた産地ガイド(localized)から、出典を確認できていない項目を取り除く。判定は日本語の原文(raw)で行う。 */
export function gateLocalizedOrigin(localized, raw) {
  const published = publishedOrigin(raw);
  const en = getLang() === "en"; // 英語表示のときだけ、台帳の英訳を使う
  const out = { ...localized };
  for (const field of ORIGIN_FIELDS) {
    if (!published[field]) {
      out[field] = "";
    } else if (contentOf(`origin:${raw.country}:${field}`)) {
      // 直した内容を出す。英訳があれば英訳、無ければ日本語
      out[field] = en ? (published.en[field] ?? published[field]) : published[field];
    }
  }
  const names = new Set(published.subRegions.map((sub) => sub.name));
  out.subRegions = (raw.subRegions ?? [])
    .map((sub, i) => ({ sub, shown: localized.subRegions?.[i] ?? sub }))
    .filter(({ sub }) => names.has(sub.name))
    .map(({ sub, shown }) => {
      if (!contentOf(`origin:${raw.country}:sub:${sub.name}`)) return shown;
      const ja = published.subRegions.find((s) => s.name === sub.name);
      return { ...shown, detail: en ? (published.en.subs[sub.name] ?? ja.detail) : ja.detail };
    });
  return out;
}

/** 産地ガイドの国ごとの公開状況(1項目でも出せるか) */
export const originHasPublished = (origin) => publishedOrigin(origin).keys.length > 0;

/** 国内競技会。出典を確認できていない項目は取り除く。直した内容があれば差し替える。 */
export function publishedCompetition(competition) {
  const keys = [];
  const en = {};
  const overridden = [];
  const result = { ...competition };
  for (const field of COMPETITION_FIELDS) {
    if (!competition[field]) continue;
    const item = competitionItem(competition, field);
    if (!ok(item)) {
      result[field] = undefined;
      continue;
    }
    keys.push(item.key);
    const content = contentOf(item.key);
    if (content) {
      result[field] = content.text;
      overridden.push(field);
    }
    const contentEn = contentEnOf(item.key);
    if (contentEn?.text) en[field] = contentEn.text;
  }
  return { ...result, keys, en, overridden };
}

export const PUBLISHED_COMPETITIONS = JAPAN_COMPETITIONS.map(publishedCompetition).filter((c) => c.keys.length > 0);

/** 画面の説明文。出典を確認できていなければ null */
export const prose = (id) => (ok(proseItem(id)) ? PROSE[id] : null);
export const proseKey = (id) => proseItem(id).key;
