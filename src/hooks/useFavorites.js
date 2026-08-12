import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "coffee-finder:favorites";
export const FREE_FAVORITES_LIMIT = 20;

// 商品IDは実データ(product_url由来の文字列)とモックデータ(数値)が混在するため、
// 比較・保存の際は常にStringに揃えて型の不一致による誤判定を防ぐ。
function loadFavoriteIds() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.map(String) : [];
  } catch {
    return [];
  }
}

export function useFavorites(isPremium, showToast) {
  const [favoriteIds, setFavoriteIds] = useState(loadFavoriteIds);
  const limit = isPremium ? Infinity : FREE_FAVORITES_LIMIT;

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(favoriteIds));
    } catch {
      // プライベートブラウジング等でlocalStorageが使えない場合は保存をスキップ
    }
  }, [favoriteIds]);

  const isFavorite = useCallback((id) => favoriteIds.includes(String(id)), [favoriteIds]);

  const toggleFavorite = useCallback(
    (id) => {
      const key = String(id);
      setFavoriteIds((prev) => {
        if (prev.includes(key)) return prev.filter((existing) => existing !== key);
        if (!isPremium && prev.length >= FREE_FAVORITES_LIMIT) {
          showToast?.(
            `お気に入りは無料プランで${FREE_FAVORITES_LIMIT}件までです。有料プランでは無制限に保存できます。`
          );
          return prev;
        }
        return [...prev, key];
      });
    },
    [isPremium, showToast]
  );

  // バックアップファイルからの復元用。既存のお気に入りは失わないよう、
  // 上書きではなく差分(未登録分)だけを追加するマージ方式にしている。
  // 無料プランの上限は超えて追加できる(復元操作をデータ欠落で失敗させないため)。
  const importFavorites = useCallback(
    (ids) => {
      const incoming = Array.isArray(ids) ? [...new Set(ids.map(String))] : [];
      const existing = new Set(favoriteIds);
      const newOnes = incoming.filter((id) => !existing.has(id));
      if (newOnes.length > 0) {
        setFavoriteIds((prev) => [...prev, ...newOnes]);
      }
      return { total: incoming.length, added: newOnes.length };
    },
    [favoriteIds]
  );

  return { favoriteIds, isFavorite, toggleFavorite, importFavorites, limit };
}
