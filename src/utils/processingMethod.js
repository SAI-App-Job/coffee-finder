import PROCESSING_METHOD_SYNONYMS from "../../data/processing_method_synonyms.json";

// scraper側(coffee_parser.pyのdetect_processing_method/normalize_processing_method)と
// 同じシノニム辞書(data/processing_method_synonyms.json)を参照する、フロントエンド版の
// 正規化ロジック。本来はスクレイパー側で正規化済みのはずだが、差分スクレイピングの
// キャッシュ等で万一未正規化の生の表記(英語表記・大文字小文字違い等)が紛れ込んだ場合に、
// タグの解説(PROCESSING_EXPLANATIONS)が引けなくなる不具合を表示側でも防ぐための保険。
const CANONICAL_ENTRIES = Object.entries(PROCESSING_METHOD_SYNONYMS).map(
  ([canonical, entry]) => [canonical, entry.synonyms.map((s) => s.toLowerCase())]
);

export function normalizeProcessingMethod(text) {
  if (!text) return text;
  const lowered = text.toLowerCase();
  for (const [canonical, synonyms] of CANONICAL_ENTRIES) {
    if (synonyms.some((kw) => lowered.includes(kw))) return canonical;
  }
  return text;
}
