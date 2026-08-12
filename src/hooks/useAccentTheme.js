import { useEffect, useState } from "react";
import { ACCENT_THEMES, DEFAULT_ACCENT_THEME_ID } from "../data/themes";

const STORAGE_KEY = "coffee-finder:accent-theme";

function loadThemeId() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return ACCENT_THEMES.some((t) => t.id === raw) ? raw : DEFAULT_ACCENT_THEME_ID;
  } catch {
    return DEFAULT_ACCENT_THEME_ID;
  }
}

export function useAccentTheme() {
  const [themeId, setThemeId] = useState(loadThemeId);
  const theme = ACCENT_THEMES.find((t) => t.id === themeId) ?? ACCENT_THEMES[0];

  useEffect(() => {
    const root = document.documentElement.style;
    root.setProperty("--accent", theme.accent);
    root.setProperty("--accent-soft", theme.accentSoft);
    root.setProperty("--accent-muted", theme.accentMuted);
    root.setProperty("--accent-label", theme.accentLabel);
    root.setProperty("--accent-glow", theme.accentGlow);
  }, [theme]);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, themeId);
    } catch {
      // プライベートブラウジング等でlocalStorageが使えない場合は保存をスキップ
    }
  }, [themeId]);

  return { themeId, setThemeId, theme, themes: ACCENT_THEMES };
}
