// 器具カタログ(data/tools.json)の検索。
// カタログは、メーカー公式のデータから作る(scripts/build_tools_catalog.py)。ここでは、読み込んだ後の検索だけを行う。

const norm = (s) =>
  String(s ?? "")
    .normalize("NFKC")
    .toLowerCase()
    .replace(/[\s\-_・/]/g, "");

/** カタログ(items)を、検索しやすい1行ずつの形(商品×型番・色)に広げる */
export function flattenToolCatalog(catalog) {
  const items = Array.isArray(catalog?.items) ? catalog.items : [];
  const rows = [];
  for (const item of items) {
    if (!item || typeof item.name !== "string" || typeof item.kind !== "string") continue;
    const variants = Array.isArray(item.variants) && item.variants.length > 0 ? item.variants : [{ label: "", sku: "", gtin: "" }];
    variants.forEach((v, i) => {
      rows.push({
        key: `${item.id}:${v.sku || i}`,
        kind: item.kind,
        maker: item.maker ?? "",
        name: item.name,
        label: v.label ?? "",
        sku: v.sku ?? "",
        gtin: v.gtin ?? "",
        url: item.url ?? "",
        search: norm([item.maker, item.makerAlias, item.name, v.label, v.sku].filter(Boolean).join(" ")),
      });
    });
  }
  return rows;
}

/** 表示する名前(商品名+色・大きさ) */
export const toolDisplayName = (row) => [row.name, row.label].filter(Boolean).join(" ");

/** 名前・メーカー・型番の一部から、同じ種類の候補を探す(語を空白で区切ると、すべて含むものだけ) */
export function searchToolCatalog(rows, kind, query, limit = 8) {
  const tokens = String(query ?? "")
    .split(/\s+/)
    .map(norm)
    .filter(Boolean);
  if (tokens.length === 0) return [];
  const first = tokens[0];
  return rows
    .filter((r) => r.kind === kind && tokens.every((tk) => r.search.includes(tk)))
    .sort((a, b) => Number(b.search.startsWith(first)) - Number(a.search.startsWith(first))) // 同じ順位は、カタログの並びのまま
    .slice(0, limit);
}

/** バーコードの番号(JAN・GTIN)が一致する行を返す。無ければ undefined */
export function findToolByGtin(rows, gtin) {
  const digits = String(gtin ?? "").replace(/[\s-]/g, "");
  if (!/^\d{8,14}$/.test(digits)) return undefined;
  return rows.find((r) => r.gtin === digits);
}
