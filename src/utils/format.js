import { ROAST_LEVELS } from "../data/roastLevels";

export const roastColor = (roastKey) =>
  ROAST_LEVELS.find((r) => r.key === roastKey)?.color ?? "#8B5E2E";

// 住所文字列から都道府県部分を除いた市区(以降)だけを取り出す
// 例:「神奈川県川崎市多摩区」→「川崎市多摩区」、「愛知県名古屋市」→「名古屋市」
export const cityFromAddress = (address) => {
  if (!address) return "";
  return address.replace(/^.+?[都道府県]/, "");
};

// 単一priceを持つ店舗(MiLL Coffee/PHILOCOFFEA/FUGLEN)と、価格帯のみを
// 持つ店舗(Denim bis。一覧ページに「890円〜4,010円」のような範囲表記しかなく、
// 単一priceを取得できない)の両方に対応する表示用フォーマッタ。
// いずれも取得できない場合はnullを返し、呼び出し側で価格欄自体を出し分ける。
export const formatPrice = ({ price, priceMin, priceMax }) => {
  if (typeof price === "number") return `¥${price.toLocaleString()}`;
  if (typeof priceMin === "number" && typeof priceMax === "number") {
    return priceMin === priceMax
      ? `¥${priceMin.toLocaleString()}`
      : `¥${priceMin.toLocaleString()}〜¥${priceMax.toLocaleString()}`;
  }
  if (typeof priceMin === "number") return `¥${priceMin.toLocaleString()}〜`;
  if (typeof priceMax === "number") return `〜¥${priceMax.toLocaleString()}`;
  return null;
};

// 閲覧履歴表示用の相対時刻(例:「たった今」「3時間前」「5日前」)
export const formatRelativeTime = (isoString) => {
  const diffMs = Date.now() - new Date(isoString).getTime();
  const minutes = Math.floor(diffMs / 60000);
  if (minutes < 1) return "たった今";
  if (minutes < 60) return `${minutes}分前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}時間前`;
  const days = Math.floor(hours / 24);
  return `${days}日前`;
};
