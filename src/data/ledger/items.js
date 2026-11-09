// 台帳のキーと「検証した本文」の作り方(アプリと検査スクリプトで共通)。
// キーの規則は docs/research-rules.md。本文を変えると、ハッシュが変わり、再検証が必要になる。
import { DISCOVERY_FACTS } from "../discoveryFacts";
import { GLOSSARY_TERMS } from "../glossary";
import { BREW_METHODS, EXTRACTION_VARIABLES, EXTRACTION_DIAGNOSIS } from "../brewGuide";
import { ORIGIN_GUIDE } from "../originGuide";
import { VARIETY_GUIDE } from "../varietyGuide";
import { DESIGNATED_BRANDS } from "../designatedBrands";
import { PROCESSING_EXPLANATIONS, DESIGNATED_BRAND_EXPLANATIONS } from "../explanations";
import { JAPAN_COMPETITIONS } from "../japanCompetitions";
import { EVENTS } from "../events";
import { GRADE_EXPLANATION_TEMPLATES } from "../../utils/grade";
import { PROSE } from "./prose";

export const ORIGIN_FIELDS = [
  "tagline",
  "regions",
  "terroir",
  "harvestSeason",
  "varietiesDetail",
  "farmStructure",
  "history",
  "gradeSystem",
  "officialBody",
];
export const COMPETITION_FIELDS = ["tagline", "history", "format", "latestResult"];

export const factItem = (fact) => ({ key: `fact:${fact.title}`, text: `${fact.title}\n${fact.text}` });
export const glossaryItem = (g) => ({ key: `glossary:${g.term}`, text: `${g.term}\n${g.summary}\n${g.detail}` });
export const brewItem = (b) => ({
  key: `brew:${b.method}`,
  text: [b.method, b.tagline, b.ratio, b.temp, b.time, b.grindSize, ...(b.steps ?? []), b.pairing, b.calibration].join("\n"),
});
export const extractionItem = (v) => ({ key: `extraction:${v.key}`, text: `${v.title}\n${v.summary}\n${v.detail}` });
export const diagnosisItem = (d) => ({ key: `diagnosis:${d.label}`, text: `${d.label}\n${d.cause}\n${d.taste}` });
export const originFieldItem = (country, field, value) => ({ key: `origin:${country}:${field}`, text: String(value ?? "") });
export const originSubItem = (country, sub) => ({ key: `origin:${country}:sub:${sub.name}`, text: `${sub.name}\n${sub.detail}` });
export const varietyItem = (v) => ({
  key: `variety:${v.lineage}`,
  text: [v.lineage, v.tagline, ...(v.varieties ?? []), v.note].join("\n"),
});
export const brandItem = (brand) => ({
  key: `brand:${brand.name}`,
  text: [brand.name, brand.note ?? "", DESIGNATED_BRAND_EXPLANATIONS[brand.name] ?? ""].join("\n"),
});
export const processingItem = (name) => ({ key: `processing:${name}`, text: `${name}\n${PROCESSING_EXPLANATIONS[name]}` });
export const gradeItem = (kind) => ({ key: `grade:${kind}`, text: GRADE_EXPLANATION_TEMPLATES[kind] });
export const competitionItem = (c, field) => ({ key: `competition:${c.id}:${field}`, text: String(c[field] ?? "") });
export const eventItem = (e) => ({
  key: `event:${e.name}`,
  text: [e.name, e.venue ?? "", e.dateRange ?? "", e.note ?? ""].join("\n"),
});
export const proseItem = (id) => ({ key: `prose:${id}`, text: PROSE[id] });

/** 台帳が必要な記述を、すべて列挙する(検査スクリプト用)。 */
export function allItems() {
  const items = [];
  DISCOVERY_FACTS.forEach((f) => items.push(factItem(f)));
  GLOSSARY_TERMS.forEach((g) => items.push(glossaryItem(g)));
  BREW_METHODS.forEach((b) => items.push(brewItem(b)));
  EXTRACTION_VARIABLES.forEach((v) => items.push(extractionItem(v)));
  EXTRACTION_DIAGNOSIS.forEach((d) => items.push(diagnosisItem(d)));
  ORIGIN_GUIDE.forEach((o) => {
    ORIGIN_FIELDS.forEach((field) => {
      if (o[field]) items.push(originFieldItem(o.country, field, o[field]));
    });
    (o.subRegions ?? []).forEach((sub) => items.push(originSubItem(o.country, sub)));
  });
  VARIETY_GUIDE.forEach((v) => items.push(varietyItem(v)));
  DESIGNATED_BRANDS.forEach((b) => items.push(brandItem(b)));
  Object.keys(PROCESSING_EXPLANATIONS).forEach((name) => items.push(processingItem(name)));
  Object.keys(GRADE_EXPLANATION_TEMPLATES).forEach((kind) => items.push(gradeItem(kind)));
  JAPAN_COMPETITIONS.forEach((c) => {
    COMPETITION_FIELDS.forEach((field) => {
      if (c[field]) items.push(competitionItem(c, field));
    });
  });
  EVENTS.forEach((e) => items.push(eventItem(e)));
  Object.keys(PROSE).forEach((id) => items.push(proseItem(id)));
  return items;
}
