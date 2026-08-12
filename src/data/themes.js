// ---------------------------------------------------------------------------
// アクセントカラーのプリセット。配色そのものはダーク基調(#231810等)に固定し、
// ボタン・アクティブタブ・リンクなどに使う「アクセント」だけをここから選ぶ。
// 各色は以下4トークンを持つ:
//   accent      : 主要な塗り色(ボタン背景・アクティブタブ・強調テキスト)
//   accentSoft  : ホバー時の明るいバリエーション
//   accentMuted : タグ/ピルの控えめなテキスト色
//   accentLabel : 見出しラベル・アイコン・ボーダーに使う、やや暗めのトーン
//   accentGlow  : ボタンのドロップシャドウに使うrgba文字列
// ---------------------------------------------------------------------------
export const ACCENT_THEMES = [
  {
    id: "gold",
    label: "ゴールド",
    accent: "#D4A24E",
    accentSoft: "#E8C89A",
    accentMuted: "#C9A876",
    accentLabel: "#8B5E2E",
    accentGlow: "rgba(212, 162, 78, 0.35)",
  },
  {
    id: "terracotta",
    label: "テラコッタ",
    accent: "#C1663A",
    accentSoft: "#E3A47C",
    accentMuted: "#D0916A",
    accentLabel: "#8A4A2A",
    accentGlow: "rgba(193, 102, 58, 0.35)",
  },
  {
    id: "sage",
    label: "セージグリーン",
    accent: "#7C9473",
    accentSoft: "#B7CBA9",
    accentMuted: "#A0B693",
    accentLabel: "#556B4A",
    accentGlow: "rgba(124, 148, 115, 0.35)",
  },
  {
    id: "dustyblue",
    label: "ダスティブルー",
    accent: "#5E85A8",
    accentSoft: "#A6C4DB",
    accentMuted: "#89ABC4",
    accentLabel: "#3E5F7A",
    accentGlow: "rgba(94, 133, 168, 0.35)",
  },
  {
    id: "plum",
    label: "プラム",
    accent: "#9B5C7A",
    accentSoft: "#D19DB4",
    accentMuted: "#BD84A0",
    accentLabel: "#6B3A52",
    accentGlow: "rgba(155, 92, 122, 0.35)",
  },
];

export const DEFAULT_ACCENT_THEME_ID = "gold";
