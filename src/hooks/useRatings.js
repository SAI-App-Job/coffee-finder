import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "coffee-finder:ratings";

// 商品ごとの評価(★1〜5)をお気に入りとは独立した軸として保存する。
// レコードは { [productId]: { rating, ratedAt } }。
// 後続の「④ 記録」フェーズで追加予定のテイスティングノートは、この
// 同じレコードに note/notedAt を追加する形で統合する想定(商品IDを
// キーにした単一のレコードにまとめることで、評価とノートを一緒に
// 振り返れるようにするため。ノート追加時にストレージキーの分割・
// 移行が発生しないよう、あらかじめこの構造で揃えている)。
function loadRatings() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return typeof parsed === "object" && parsed !== null && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

export function useRatings() {
  const [ratings, setRatings] = useState(loadRatings);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(ratings));
    } catch {
      // プライベートブラウジング等でlocalStorageが使えない場合は保存をスキップ
    }
  }, [ratings]);

  const getRating = useCallback((id) => ratings[String(id)]?.rating ?? 0, [ratings]);

  // starsに0を渡すと評価を取り消す(同じ星をもう一度タップした場合など)
  const setRating = useCallback((id, stars) => {
    const key = String(id);
    setRatings((prev) => {
      if (!stars || stars <= 0) {
        if (!(key in prev)) return prev;
        const next = { ...prev };
        delete next[key];
        return next;
      }
      return { ...prev, [key]: { ...prev[key], rating: stars, ratedAt: new Date().toISOString() } };
    });
  }, []);

  return { ratings, getRating, setRating };
}
