import { useEffect, useState } from "react";

const STORAGE_KEY = "coffee-finder:favorite-area";
const DEFAULT_FAVORITE_AREA = { prefecture: "", city: "" };

function loadFavoriteArea() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_FAVORITE_AREA;
    const parsed = JSON.parse(raw);
    return {
      prefecture: typeof parsed.prefecture === "string" ? parsed.prefecture : "",
      city: typeof parsed.city === "string" ? parsed.city : "",
    };
  } catch {
    return DEFAULT_FAVORITE_AREA;
  }
}

// 登録エリア(マイページで手動登録する都道府県・市区町村)。郵便番号や
// ジオコーディングは使わず、住所文字列との部分一致で判定する(端末内のみで
// 完結し、店舗網羅率に左右されない)。
export function useFavoriteArea() {
  const [favoriteArea, setFavoriteAreaState] = useState(loadFavoriteArea);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(favoriteArea));
    } catch {
      // プライベートブラウジング等でlocalStorageが使えない場合は保存をスキップ
    }
  }, [favoriteArea]);

  const setPrefecture = (prefecture) => setFavoriteAreaState((prev) => ({ ...prev, prefecture }));
  const setCity = (city) => setFavoriteAreaState((prev) => ({ ...prev, city }));

  return { favoriteArea, setPrefecture, setCity };
}
