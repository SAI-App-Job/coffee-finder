import { useCallback, useEffect, useState } from "react";
import { loadStoredJson } from "../utils/storage";
import { mergeRatings } from "../utils/backupMerge";

const STORAGE_KEY = "coffee-finder:ratings";

// 商品ごとの評価(★1〜5)をお気に入りとは独立した軸として保存する。
// レコードは { [productId]: { rating, ratedAt } }。
// 後続の「④ 記録」フェーズで追加予定のテイスティングノートは、この
// 同じレコードに note/notedAt を追加する形で統合する想定(商品IDを
// キーにした単一のレコードにまとめることで、評価とノートを一緒に
// 振り返れるようにするため。ノート追加時にストレージキーの分割・
// 移行が発生しないよう、あらかじめこの構造で揃えている)。
function loadRatings() {
  // 読めなかった・形が違うときは、元の文字列を残してから、空で始める(utils/storage.js)
  return loadStoredJson(
    STORAGE_KEY,
    (parsed) => (parsed === null ? { value: {} } : typeof parsed === "object" && !Array.isArray(parsed) ? { value: parsed } : null),
    {}
  );
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

  // バックアップファイルからの復元用。上書きはせず、無い商品の評価を足す(同じ商品は、日時が新しい方を残す)
  const importRatings = useCallback(
    (incoming) => {
      const result = mergeRatings(ratings, incoming);
      if (result.added + result.updated > 0) setRatings(result.value);
      return { added: result.added, updated: result.updated };
    },
    [ratings]
  );

  return { ratings, getRating, setRating, importRatings };
}
