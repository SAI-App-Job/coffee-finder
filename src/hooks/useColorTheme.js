import { useEffect, useState } from "react";
import { COLOR_THEMES, DEFAULT_COLOR_THEME_ID } from "../data/themes";

// 旧「アクセントカラー」("coffee-finder:accent-theme")とは別のキーにして、
// 旧設定(gold/terracotta等)を引き継がずに既定のダークから始める。
const STORAGE_KEY = "coffee-finder:color-theme";

function loadThemeId() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return COLOR_THEMES.some((t) => t.id === raw) ? raw : DEFAULT_COLOR_THEME_ID;
  } catch {
    return DEFAULT_COLOR_THEME_ID;
  }
}

export function useColorTheme() {
  const [themeId, setThemeId] = useState(loadThemeId);

  useEffect(() => {
    document.documentElement.dataset.theme = themeId;
    try {
      localStorage.setItem(STORAGE_KEY, themeId);
    } catch {
      // プライベートブラウジング等でlocalStorageが使えない場合は保存をスキップ
    }
  }, [themeId]);

  return { themeId, setThemeId, themes: COLOR_THEMES };
}
