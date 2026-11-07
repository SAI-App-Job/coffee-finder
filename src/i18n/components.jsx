import { Fragment, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { EN } from "./en";
import { LanguageContext, applyLanguage, getCurrentLang } from "./core";

export function LanguageProvider({ children }) {
  const [lang, setLangState] = useState(getCurrentLang);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const setLang = useCallback((next) => {
    if (applyLanguage(next)) setLangState(next);
  }, []);

  const value = useMemo(() => ({ lang, setLang }), [lang, setLang]);
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

// 文の途中に、ボタンなどの要素を入れたいときに使う。<Trans k="…{retry}してください" values={{ retry: <button/> }} />
// {名前} の位置に、values の要素が入る(英語では語順が変わっても、要素の位置を辞書の側で決められる)。
export function Trans({ k, values = {} }) {
  useContext(LanguageContext);
  const raw = getCurrentLang() === "en" ? (EN[k] ?? k) : k;
  return raw.split(/(\{\w+\})/).map((part, i) => {
    const m = part.match(/^\{(\w+)\}$/);
    if (m && m[1] in values) return <Fragment key={i}>{values[m[1]]}</Fragment>;
    return part;
  });
}

