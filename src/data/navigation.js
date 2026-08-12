import { Coffee, Store, Award, BookOpen, Palette, Tag, Dna, Droplet, Trophy, Heart } from "lucide-react";

export const TAB_ITEMS = [
  { id: "products", icon: Coffee, ja: "商品", en: "Products" },
  { id: "favorites", icon: Heart, ja: "お気に入り", en: "Favorites" },
  { id: "shops", icon: Store, ja: "店舗", en: "Shops" },
  { id: "guide", icon: Award, ja: "産地", en: "Origin" },
  { id: "trivia", icon: BookOpen, ja: "豆知識", en: "Trivia" },
];

// 「豆知識」タブ内のサブナビゲーション(旧: 用語解説/品種/淹れ方タブを統合)
export const TRIVIA_SUB_TABS = [
  { id: "flavorWheel", icon: Palette, ja: "フレーバーホイール", en: "Flavor Wheel" },
  { id: "glossary", icon: BookOpen, ja: "用語解説", en: "Glossary" },
  { id: "brands", icon: Tag, ja: "特定銘柄", en: "Designated Brands" },
  { id: "variety", icon: Dna, ja: "品種", en: "Varieties" },
  { id: "brew", icon: Droplet, ja: "淹れ方", en: "Brewing" },
  { id: "events", icon: Trophy, ja: "大会・イベント", en: "Competitions & Events" },
];

// この件数を超える選択肢を持つFilterSectionには、自動的に検索窓を表示する。
// 店舗名は今後スクレイピング対象が増えるにつれ件数が伸びていく想定のため、
// 特定の項目に決め打ちせず、件数ベースで汎用的に効くようにしている。
export const FILTER_SEARCH_THRESHOLD = 8;
