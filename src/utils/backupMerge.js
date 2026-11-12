// バックアップファイルの内容を、いまの端末のデータに、追加(マージ)するための関数。
// 方針: 上書きしない。すでにあるものは、そのまま残し、無いものだけを足す(評価だけは、新しい方を残す)。
// ファイルは、利用者が編集できる外部の入力なので、形を確かめて、合わないものは、飛ばす。

const isObj = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
const validTime = (v) => typeof v === "string" && !Number.isNaN(Date.parse(v));
const safeKey = (k) => typeof k === "string" && k !== "" && k !== "__proto__" && k !== "constructor" && k !== "prototype";

/** ★評価: { [商品ID]: { rating: 1〜5, ratedAt } }。同じ商品が両方にあれば、評価の日時が新しい方を残す */
export function mergeRatings(prev, incoming) {
  if (!isObj(incoming)) return { value: prev, added: 0, updated: 0 };
  const value = { ...prev };
  let added = 0;
  let updated = 0;
  for (const [id, r] of Object.entries(incoming)) {
    if (!safeKey(id) || !isObj(r) || !Number.isInteger(r.rating) || r.rating < 1 || r.rating > 5 || !validTime(r.ratedAt)) continue;
    const cur = value[id];
    if (!cur) {
      value[id] = { rating: r.rating, ratedAt: r.ratedAt };
      added++;
    } else if (Date.parse(r.ratedAt) > (Date.parse(cur.ratedAt) || 0)) {
      value[id] = { ...cur, rating: r.rating, ratedAt: r.ratedAt };
      updated++;
    }
  }
  return { value, added, updated };
}

/** テイスティングログ({ [商品ID]: 記録[] })・店舗のテイスティングノート({ [店名]: 記録[] }): 記録の id が無いものだけを足す。新しい順に並べる */
export function mergeEntries(prev, incoming) {
  if (!isObj(incoming)) return { value: prev, added: 0 };
  const value = { ...prev };
  let added = 0;
  for (const [key, entries] of Object.entries(incoming)) {
    if (!safeKey(key) || !Array.isArray(entries)) continue;
    const have = new Set((value[key] ?? []).map((e) => e.id));
    const fresh = entries.filter((e) => isObj(e) && typeof e.id === "string" && e.id && validTime(e.recordedAt) && !have.has(e.id));
    if (fresh.length === 0) continue;
    // 同じファイルの中の重複も、1件にする
    const unique = [...new Map(fresh.map((e) => [e.id, e])).values()];
    value[key] = [...(value[key] ?? []), ...unique].sort((a, b) => Date.parse(b.recordedAt) - Date.parse(a.recordedAt));
    added += unique.length;
  }
  return { value, added };
}

/** マイツール: id が無いものだけを足す(incoming は、normalize 済みの配列) */
export function mergeTools(prev, incoming) {
  const have = new Set(prev.map((t) => t.id));
  const fresh = [...new Map(incoming.filter((t) => !have.has(t.id)).map((t) => [t.id, t])).values()];
  return { value: fresh.length > 0 ? [...prev, ...fresh] : prev, added: fresh.length };
}
