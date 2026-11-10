// GTIN(JANコード・EAN・UPC)の検査。
// 8桁(GTIN-8)・12桁(UPC-A)・13桁(JAN/EAN-13)・14桁(GTIN-14)で、末尾の1桁がチェックデジット。

/** 数字以外(ハイフン・空白)を取り除く */
export const cleanGtin = (value) => String(value ?? "").replace(/[\s-]/g, "");

/** 桁数とチェックデジットが正しいか */
export function isValidGtin(value) {
  const digits = cleanGtin(value);
  if (!/^\d+$/.test(digits) || ![8, 12, 13, 14].includes(digits.length)) return false;
  const body = digits.slice(0, -1);
  // 末尾から数えて、1桁目から3・1・3・1…の重みを掛ける
  let sum = 0;
  for (let i = 0; i < body.length; i++) {
    sum += Number(body[body.length - 1 - i]) * (i % 2 === 0 ? 3 : 1);
  }
  return (10 - (sum % 10)) % 10 === Number(digits.at(-1));
}

/** http(s)のURLだけを通す。書式が正しければ、整えたURLを返し、そうでなければnull */
export function normalizeUrl(value) {
  const raw = String(value ?? "").trim();
  if (!raw) return null;
  try {
    const url = new URL(/^https?:\/\//i.test(raw) ? raw : `https://${raw}`);
    return url.hostname.includes(".") ? url.href : null;
  } catch {
    return null;
  }
}
