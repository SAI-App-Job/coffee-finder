import { translate } from "../i18n";
import { loadStoredJson } from "../utils/storage";
import { useCallback, useEffect, useRef, useState } from "react";

const STORAGE_KEY = "coffee-finder:favorites";
// 保存した日(登録日)。お気に入りのIDリストとは別のキーに持つ(IDリストの形式は変えない)
const DATES_STORAGE_KEY = "coffee-finder:favorite-dates";
export const FREE_FAVORITES_LIMIT = 20;

// 商品IDは実データ(product_url由来の文字列)とモックデータ(数値)が混在するため、
// 比較・保存の際は常にStringに揃えて型の不一致による誤判定を防ぐ。
function loadFavoriteIds() {
  return loadStoredJson(STORAGE_KEY, (parsed) => (Array.isArray(parsed) ? { value: parsed.map(String) } : null), []);
}

const isValidDate = (v) => typeof v === "string" && !Number.isNaN(new Date(v).getTime());

// { [商品ID]: ISO日時 }。日付の記録が始まる前に保存した商品は、日付を持たない(推測で補わない)。
function loadFavoriteDates() {
  return loadStoredJson(
    DATES_STORAGE_KEY,
    (parsed) => {
      if (parsed === null) return { value: {} };
      if (typeof parsed !== "object" || Array.isArray(parsed)) return null;
      return { value: Object.fromEntries(Object.entries(parsed).filter(([, v]) => isValidDate(v))) };
    },
    {}
  );
}

export function useFavorites(isPremium, showToast) {
  const [favoriteIds, setFavoriteIds] = useState(loadFavoriteIds);
  const [favoriteDates, setFavoriteDates] = useState(loadFavoriteDates);
  // toggleFavorite を毎回作り直さない(商品カードの再描画を抑える)ため、最新のIDリストは ref で参照する
  const idsRef = useRef(favoriteIds);
  idsRef.current = favoriteIds;
  const limit = isPremium ? Infinity : FREE_FAVORITES_LIMIT;

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(favoriteIds));
    } catch {
      // プライベートブラウジング等でlocalStorageが使えない場合は保存をスキップ
    }
  }, [favoriteIds]);

  useEffect(() => {
    try {
      localStorage.setItem(DATES_STORAGE_KEY, JSON.stringify(favoriteDates));
    } catch {
      // 保存できない環境では、日付の保存をスキップ
    }
  }, [favoriteDates]);

  const isFavorite = useCallback((id) => favoriteIds.includes(String(id)), [favoriteIds]);

  const toggleFavorite = useCallback(
    (id) => {
      const key = String(id);
      const prev = idsRef.current;
      if (prev.includes(key)) {
        idsRef.current = prev.filter((existing) => existing !== key);
        setFavoriteIds(idsRef.current);
        setFavoriteDates(({ [key]: _removed, ...rest }) => rest);
        return;
      }
      if (!isPremium && prev.length >= FREE_FAVORITES_LIMIT) {
        showToast?.(
          translate("コレクションに保存できる商品は、無料プランで{n}件までです。有料プランでは無制限に保存できます。", { n: FREE_FAVORITES_LIMIT })
        );
        return;
      }
      idsRef.current = [...prev, key];
      setFavoriteIds(idsRef.current);
      setFavoriteDates((dates) => ({ ...dates, [key]: new Date().toISOString() }));
    },
    [isPremium, showToast]
  );

  // バックアップファイルからの復元用。既存のお気に入りは失わないよう、
  // 上書きではなく差分(未登録分)だけを追加するマージ方式にしている。
  // dates: バックアップに入っていた登録日({ [商品ID]: ISO日時 })。新しく追加する商品の分だけ取り込む。
  // 無料プランの上限は超えて追加できる(復元操作をデータ欠落で失敗させないため)。
  const importFavorites = useCallback(
    (ids, dates) => {
      const incoming = Array.isArray(ids) ? [...new Set(ids.map(String))] : [];
      const existing = new Set(favoriteIds);
      const newOnes = incoming.filter((id) => !existing.has(id));
      if (newOnes.length > 0) {
        setFavoriteIds((prev) => [...prev, ...newOnes]);
        const restored = Object.fromEntries(
          newOnes.filter((id) => isValidDate(dates?.[id])).map((id) => [id, new Date(dates[id]).toISOString()])
        );
        if (Object.keys(restored).length > 0) setFavoriteDates((prev) => ({ ...restored, ...prev }));
      }
      return { total: incoming.length, added: newOnes.length };
    },
    [favoriteIds]
  );

  return { favoriteIds, favoriteDates, isFavorite, toggleFavorite, importFavorites, limit };
}
