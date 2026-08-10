import { ROAST_LEVELS } from "../data/roastLevels";

export const roastColor = (roastKey) =>
  ROAST_LEVELS.find((r) => r.key === roastKey)?.color ?? "#8B5E2E";

// 住所文字列から都道府県部分を除いた市区(以降)だけを取り出す
// 例:「神奈川県川崎市多摩区」→「川崎市多摩区」、「愛知県名古屋市」→「名古屋市」
export const cityFromAddress = (address) => {
  if (!address) return "";
  return address.replace(/^.+?[都道府県]/, "");
};
