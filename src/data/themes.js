// ---------------------------------------------------------------------------
// アプリの配色テーマ(2種類)。実際の色は src/index.css の CSS 変数で定義していて、
// <html data-theme="..."> の値で切り替える("dark" は属性なしの既定値と同じ)。
//   dark  : 従来の配色(ダークブラウン基調+ゴールドのアクセント)
//   light : 白を基調にした配色
// preview は設定のカラーテーマの選択カードに描く見本の色(背景・文字・アクセント)。
// ---------------------------------------------------------------------------
export const COLOR_THEMES = [
  {
    id: "dark",
    label: "ダーク",
    description: "ダークブラウン基調(従来の配色)",
    preview: { bg: "#231810", surface: "#2f241a", text: "#f2e9dd", accent: "#d4a24e" },
  },
  {
    id: "light",
    label: "ホワイト",
    description: "白を基調にした明るい配色",
    preview: { bg: "#ffffff", surface: "#faf6f0", text: "#2a1f16", accent: "#9a6a1e" },
  },
];

export const DEFAULT_COLOR_THEME_ID = "dark";
