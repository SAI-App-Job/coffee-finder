import { createContext, useContext } from "react";

// 画面移動の関数({ page, sub })を、深い部品へ渡すためのコンテキスト。
// 例: 商品カードのふきだしから、豆知識の「用語解説」(page: "trivia", sub: "glossary")へ移動する。
// 提供されていない場所(テストなど)では、何もしない関数になる。
export const AppNavigationContext = createContext(() => {});
export const useAppNavigation = () => useContext(AppNavigationContext);
