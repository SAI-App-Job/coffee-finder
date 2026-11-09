import { translate } from "../i18n";
import { isPublishable } from "../data/ledger";

// 商品のグレード表記の解説。文は日本語をキーにして、英語の辞書(i18n/en.js)で置き換える。
// 各文は台帳(src/data/ledger、キーは grade:<kind>)で出典を確認できたものだけを表示する。
// 文面の{grade}などは、画面に出す時に埋める(台帳のハッシュは、埋める前の文面で取る)。
export const GRADE_EXPLANATION_TEMPLATES = {
  bluemountain:
    "ジャマイカ・ブルーマウンテン地区独自の等級。No.1が最上位(木樽出荷)で、No.2、No.3と続き、規格外はピーベリー・トリアージとして扱われる。",
  ethiopia:
    "エチオピアの{grade}は欠点数(300gあたり)による格付け。G1は欠点0〜3個の最高等級で、地域・精選方法によっては特別に扱われることも。数字が大きいほど欠点が多い。",
  indonesia:
    "インドネシアの{grade}も欠点数による格付けだが、基準はエチオピアより緩め(G1で欠点0〜11個程度)。同じ「G1」でも国によって意味する品質水準が異なる点に注意。",
  "defect-generic": "欠点数による格付け(数字が小さいほど高品質)。ただし基準は生産国ごとに異なる。",
  aa: "スクリーンサイズ(豆の粒の大きさ)による格付け。ケニア・タンザニアで使われる代表的な表記で、AAは大粒の等級を示す。粒の大きさは必ずしも風味の良さを保証しない。",
  shb: "Strictly Hard Bean。標高の高さで格付けする表記で、グアテマラやコスタリカでは標高1,350m前後以上が目安。標高が高いほど豆が硬く締まり、高品質とされる。",
  number:
    "生産地・店舗によって意味が異なる通し番号やロット表記。ブラジルでは欠点数による等級(No.2〜8)を指すことが多い。",
  excelso:
    "コロンビア(FNC)のスクリーンサイズ(豆の粒の大きさ)による等級体系。「エクセルソ」は7段階の等級群に共通する親カテゴリ名で、単独では等級を特定できないため常にサブグレード名と組み合わせて表記される。本商品のサブグレードは「{subGrade}」。",
  generic:
    "国別グレードは、標高・スクリーンサイズ(粒の大きさ)・欠点数など、生産国ごとに異なる基準で決まる。同じ表記でも国が違えば意味が異なることがある。",
};

// グレード表記から、どの解説(kind)を使うかを決める
function classify(grade, country, designatedBrand) {
  if (!grade) return null;

  // ブルーマウンテンは国別グレードとは別の、銘柄固有の等級体系
  if (designatedBrand === "ブルーマウンテン" && /No\.?\s*\d/i.test(grade)) return { kind: "bluemountain" };

  if (/^G[1-6]$/.test(grade)) {
    if (country === "エチオピア") return { kind: "ethiopia", params: { grade } };
    if (country === "インドネシア") return { kind: "indonesia", params: { grade } };
    return { kind: "defect-generic" };
  }

  if (grade === "AA") return { kind: "aa" };
  if (/^SHB$/.test(grade)) return { kind: "shb" };
  if (/^No\.?\s*\d+$/i.test(grade)) return { kind: "number" };

  if (grade.startsWith("エクセルソ")) {
    return { kind: "excelso", params: { subGrade: grade.replace(/^エクセルソ\s*/, "") } };
  }

  return { kind: "generic" };
}

/** 出典を確認できた解説だけを返す。確認できていなければ null。 */
export function getGradeExplanation(grade, country, designatedBrand) {
  const found = classify(grade, country, designatedBrand);
  if (!found) return null;
  const template = GRADE_EXPLANATION_TEMPLATES[found.kind];
  if (!isPublishable(`grade:${found.kind}`, template)) return null;
  return translate(template, found.params);
}

/** その解説の台帳のキー(出典の表示に使う) */
export function getGradeExplanationKey(grade, country, designatedBrand) {
  const found = classify(grade, country, designatedBrand);
  return found ? `grade:${found.kind}` : null;
}
