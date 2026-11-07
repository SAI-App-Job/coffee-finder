import { createContext, useContext } from "react";
import { EN } from "./en";

// 画面の言語(日本語 / 英語)。文言は「日本語の文そのものをキー」にして、英語の辞書(en.js)で置き換える。
// - 辞書に無い文は、日本語のまま表示する(未翻訳でも画面が壊れない)。
// - 文の中の変わる部分は {name} と書き、translate("…{n}件", { n: 3 }) のように渡す。
//   英語の単数形・複数形は、辞書の側で {n?log:logs} と書く(n が 1 のとき log、それ以外は logs)。
// - 商品・店舗のデータ、豆知識・産地ガイドの本文は、日本語のまま(翻訳しない)。
const STORAGE_KEY = "coffee-finder:language";

export const LANGUAGES = [
  { id: "ja", label: "日本語" },
  { id: "en", label: "English" },
];

function detectLanguage() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "ja" || stored === "en") return stored;
  } catch {
    // localStorage が使えない環境では、端末の言語だけで決める
  }
  const nav = typeof navigator !== "undefined" ? (navigator.languages?.[0] ?? navigator.language ?? "") : "";
  return nav.toLowerCase().startsWith("ja") ? "ja" : "en";
}

// いまの言語。日付の表記など、画面の部品以外(utils)からも参照できるようにモジュールで持つ。
// 切り替えは LanguageProvider の setLang だけが行う。
let currentLang = detectLanguage();

export const getLang = () => currentLang;

// 日付・数値の表記に使うロケール
export const getLocale = () => (currentLang === "en" ? "en-US" : "ja-JP");

export function translate(key, params) {
  if (typeof key !== "string") return key;
  let text = currentLang === "en" ? (EN[key] ?? key) : key;
  if (params) {
    // 単数形・複数形: {n?log:logs} は、n が 1 のとき "log"、それ以外は "logs"
    text = text.replace(/\{(\w+)\?([^:}]*):([^}]*)\}/g, (match, name, one, other) =>
      name in params ? (Number(params[name]) === 1 ? one : other) : match
    );
    text = text.replace(/\{(\w+)\}/g, (match, name) => (name in params ? String(params[name]) : match));
  }
  return text;
}

export const LanguageContext = createContext({ lang: currentLang, setLang: () => {} });

// 言語を切り替える(LanguageProvider から呼ぶ)。保存もここで行う。
export function applyLanguage(next) {
  if (next !== "ja" && next !== "en") return false;
  currentLang = next; // 再描画の前に切り替える(子の描画が新しい言語になるように)
  try {
    localStorage.setItem(STORAGE_KEY, next);
  } catch {
    // 保存できなくても、この起動中は切り替わる
  }
  return true;
}

export const getCurrentLang = () => currentLang;

export const useLang = () => useContext(LanguageContext);

// 画面の部品で使う翻訳関数。言語が切り替わったときに、その部品を再描画させるため、
// translate をそのまま import せずに、この hook を通して使う。
export function useT() {
  useContext(LanguageContext);
  return translate;
}
