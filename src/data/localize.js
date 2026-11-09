import { getLang } from "../i18n";
import { ORIGIN_GUIDE_EN_1 } from "./en/originGuide1";
import { ORIGIN_GUIDE_EN_2 } from "./en/originGuide2";
import {
  DISCOVERY_FACTS_EN,
  BREW_METHODS_EN,
  EXTRACTION_VARIABLES_EN,
  EXTRACTION_DIAGNOSIS_EN,
  GLOSSARY_EN,
} from "./en/trivia";
import {
  JAPAN_COMPETITIONS_EN,
  COMPETITION_SOURCE_LABELS_EN,
  COMPETITION_ABBR_EN,
  PROCESSING_EXPLANATIONS_EN,
  DESIGNATED_BRAND_EXPLANATIONS_EN,
  DESIGNATED_BRANDS_EN,
  VARIETY_GUIDE_EN,
} from "./en/guides";
import { EVENTS_EN, EVENT_SOURCES_EN, formatDateRangeEn } from "./en/events";
import { DESIGNATED_BRAND_EXPLANATIONS } from "./explanations";
import { PUBLISHED_DESIGNATED_BRANDS, publishedProcessing } from "./published";

// コンテンツ(産地ガイド・豆知識・用語集・解説文など)を、いまの言語の版にして返す。
// 英語の版が無いものは、日本語のまま返す(新しい項目を足して、英訳がまだのときも画面が壊れない)。
// 商品・店舗のデータ(商品名・フレーバーの説明・住所など)は対象外で、日本語のまま。
const isEn = () => getLang() === "en";

const ORIGIN_GUIDE_EN = { ...ORIGIN_GUIDE_EN_1, ...ORIGIN_GUIDE_EN_2 };

// 台帳に「直した内容」がある項目(_ledger)は、台帳の英訳(_en)があればそれを、無ければ日本語の内容を出す。
// (データ側の古い英訳は、直した内容と合わないので使わない)
const ledgerAware = (localizeOld) => (x) => (x._ledger ? (isEn() && x._en ? { ...x, ...x._en } : x) : localizeOld(x));

export const localizeOrigin = (origin) => (isEn() && ORIGIN_GUIDE_EN[origin.country] ? { ...origin, ...ORIGIN_GUIDE_EN[origin.country] } : origin);
export const localizeFact = ledgerAware((fact) => (isEn() && DISCOVERY_FACTS_EN[fact.title] ? { ...fact, ...DISCOVERY_FACTS_EN[fact.title] } : fact));
export const localizeBrewMethod = ledgerAware((brew) => (isEn() && BREW_METHODS_EN[brew.method] ? { ...brew, ...BREW_METHODS_EN[brew.method] } : brew));
export const localizeExtractionVariable = ledgerAware((v) => (isEn() && EXTRACTION_VARIABLES_EN[v.key] ? { ...v, ...EXTRACTION_VARIABLES_EN[v.key] } : v));
export const localizeExtractionDiagnosis = ledgerAware((d) => (isEn() && EXTRACTION_DIAGNOSIS_EN[d.label] ? { ...d, ...EXTRACTION_DIAGNOSIS_EN[d.label] } : d));
export const localizeGlossaryTerm = ledgerAware((item) => (isEn() && GLOSSARY_EN[item.term] ? { ...item, ...GLOSSARY_EN[item.term] } : item));
export const localizeVariety = ledgerAware((v) => (isEn() && VARIETY_GUIDE_EN[v.lineage] ? { ...v, ...VARIETY_GUIDE_EN[v.lineage] } : v));
export const localizeBrand = (b) => {
  const base = isEn() && DESIGNATED_BRANDS_EN[b.name] ? { ...b, ...DESIGNATED_BRANDS_EN[b.name] } : b;
  // 直した内容(_ledger)は、名前だけ英語名にして、注記と解説は台帳の内容(英訳があれば英訳)を使う
  if (!b._ledger) return base;
  const name = isEn() ? (DESIGNATED_BRANDS_EN[b.name]?.name ?? b.name) : b.name;
  return isEn() && b._en ? { ...b, name, ...b._en } : { ...b, name };
};

export function localizeCompetition(c) {
  if (!isEn()) return c;
  const en = JAPAN_COMPETITIONS_EN[c.id] ?? {};
  const result = {
    ...c,
    ...en,
    abbr: COMPETITION_ABBR_EN[c.abbr] ?? c.abbr,
    sources: c.sources.map((s) => ({ ...s, label: COMPETITION_SOURCE_LABELS_EN[s.label] ?? s.label })),
  };
  // 台帳で直した項目は、データ側の古い英訳を使わず、台帳の英訳(無ければ日本語)を出す
  for (const field of c.overridden ?? []) result[field] = c.en?.[field] ?? c[field];
  return result;
}

// 精選方法・特定銘柄の解説文(商品カード・詳細の、タグの解説)。キーは日本語の名前
// 出典を確認できていない解説は返さない(null)。台帳: processing:<name> / brand:<name>
export const processingExplanation = (name) => {
  const p = publishedProcessing(name);
  if (!p) return null;
  if (p.overridden) return isEn() && p.en ? p.en : p.ja;
  return isEn() ? (PROCESSING_EXPLANATIONS_EN[name] ?? p.ja) : p.ja;
};
export const designatedBrandExplanation = (name) => {
  const brand = PUBLISHED_DESIGNATED_BRANDS.find((b) => b.name === name);
  if (!brand) return null;
  if (brand._ledger) return (isEn() && brand._en?.explanation) || brand.explanation || null;
  const ja = DESIGNATED_BRAND_EXPLANATIONS[name];
  if (!ja) return null;
  return isEn() ? (DESIGNATED_BRAND_EXPLANATIONS_EN[name] ?? ja) : ja;
};

// 特定銘柄の名前(英語表示のときは英語名)
export const brandName = (name) => (isEn() ? (DESIGNATED_BRANDS_EN[name]?.name ?? name) : name);

// 大会・イベント。取得データのイベントは、開催日だけ英語の書式にする(会場などは日本語のまま)
export function localizeEvent(event) {
  if (!isEn()) return event;
  const en = EVENTS_EN[event.name];
  const next = { ...event, ...(en ?? {}) };
  if (!en?.dateRange) next.dateRange = formatDateRangeEn(event.dateRange);
  if (EVENT_SOURCES_EN[event.source]) next.source = EVENT_SOURCES_EN[event.source];
  return next;
}
