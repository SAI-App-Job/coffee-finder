import {
  Coffee,
  Store,
  Globe,
  Search,
  Bell,
  User,
  BookOpen,
  Palette,
  Tag,
  Dna,
  Droplet,
  Calendar,
  Trophy,
  Heart,
  History,
  Settings,
} from "lucide-react";

// 「豆知識」タブ内のサブナビゲーション(旧: 用語解説/品種/淹れ方タブを統合)。
// 「大会・イベント」は、開催スケジュール中心の「イベント」と、SCAJ主催競技会の
// 詳細記事中心の「競技会」に分割した(EventsView.jsxのEventsView/CompetitionsView
// という2つの入れ物に対応)。
// popupLabel: 下部メニューの子メニュー(1項目76px幅)で、ラベルが長いときの改行位置。
export const TRIVIA_SUB_TABS = [
  { id: "flavorWheel", icon: Palette, ja: "フレーバーホイール", popupLabel: "フレーバー\nホイール", en: "Flavor Wheel" },
  { id: "glossary", icon: BookOpen, ja: "用語解説", en: "Glossary" },
  { id: "brands", icon: Tag, ja: "特定銘柄", en: "Designated Brands" },
  { id: "variety", icon: Dna, ja: "品種", en: "Varieties" },
  { id: "brew", icon: Droplet, ja: "淹れ方", en: "Brewing" },
  { id: "events", icon: Calendar, ja: "イベント", en: "Events" },
  { id: "competitions", icon: Trophy, ja: "競技会", en: "Competitions" },
];

// 画面下部のタブバー(アプリのメインメニュー)。
// - children を持つタブ: 押すと、そのタブの真上に子メニュー(アイコン付き)が開く。
//   子メニューの項目を選ぶとその画面へ移動する(page = 画面ID、sub = 豆知識のサブ画面ID)。
// - children を持たないタブ: 押すと page の画面へ直接移動する。
// 子メニューの項目が action を持つ場合は、画面移動ではなくその操作を行う("alerts" = お知らせパネルを開く)。
// 画面ID(page): products | shops | guide | collection | history | settings | trivia
export const NAV_TABS = [
  {
    id: "search",
    icon: Search,
    ja: "検索",
    children: [
      { page: "products", icon: Coffee, ja: "商品" },
      { page: "shops", icon: Store, ja: "店舗" },
      { action: "alerts", icon: Bell, ja: "お知らせ" },
    ],
  },
  { id: "guide", icon: Globe, ja: "産地", page: "guide" },
  {
    id: "mypage",
    icon: User,
    ja: "マイページ",
    children: [
      { page: "collection", icon: Heart, ja: "コレクション" },
      { page: "history", icon: History, ja: "履歴" },
      { page: "settings", icon: Settings, ja: "設定" },
    ],
  },
  {
    id: "trivia",
    icon: BookOpen,
    ja: "豆知識",
    children: TRIVIA_SUB_TABS.map(({ id, icon, ja, popupLabel }) => ({
      page: "trivia",
      sub: id,
      icon,
      ja,
      popupLabel,
    })),
  },
];

// 子メニューの項目が、いま開いている画面(と豆知識のサブ画面)に当たるか
export const isNavTargetCurrent = (target, page, triviaSub) =>
  target.page === page && (target.sub === undefined || target.sub === triviaSub);

// タブが「いま開いている画面」を含むか(タブバーの強調表示に使う)
export const isNavTabActive = (tab, page) =>
  tab.children ? tab.children.some((c) => c.page === page) : tab.page === page;

// この件数を超える選択肢を持つFilterSectionには、自動的に検索窓を表示する。
// 店舗名は今後スクレイピング対象が増えるにつれ件数が伸びていく想定のため、
// 特定の項目に決め打ちせず、件数ベースで汎用的に効くようにしている。
export const FILTER_SEARCH_THRESHOLD = 8;
