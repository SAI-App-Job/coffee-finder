import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "coffee-finder:favorites";

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

export function useFavorites() {
  const [favoriteIds, setFavoriteIds] = useState(loadFavoriteIds);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(favoriteIds));
    } catch {
      // プライベートブラウジング等でlocalStorageが使えない場合は保存をスキップ
    }
  }, [favoriteIds]);

  const isFavorite = useCallback((id) => favoriteIds.includes(String(id)), [favoriteIds]);

  const toggleFavorite = useCallback((id) => {
    const key = String(id);
    setFavoriteIds((prev) =>
      prev.includes(key) ? prev.filter((existing) => existing !== key) : [...prev, key]
    );
  }, []);

  // バックアップファイルからの復元用。既存のお気に入りは失わないよう、
  // 上書きではなく差分(未登録分)だけを追加するマージ方式にしている。
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

  return { favoriteIds, isFavorite, toggleFavorite, importFavorites };
}
