// ---------------------------------------------------------------------------
// 大会・イベントデータ(scrape_events_wcc.py / scrape_events_scaj.py /
// scrape_events_ace.py で検証済みの構造を基にした静的データ)
// ---------------------------------------------------------------------------
export const EVENTS = [
  {
    source: "WCC(World Coffee Championships)",
    sourceId: "wcc",
    name: "World Brewers Cup 2026",
    eventType: "competition",
    venue: "World of Coffee Brussels",
    dateRange: "2026年6月25日〜27日",
    startDate: "2026-06-25",
    relatedCountry: null,
    note: "手淹れ抽出の技術を競う世界大会。粕谷哲氏は2016年大会の優勝者。",
    sourceUrl: "https://wcc.coffee/world-brewers-cup",
  },
  {
    source: "WCC(World Coffee Championships)",
    sourceId: "wcc",
    name: "World Barista Championship 2026",
    eventType: "competition",
    venue: "World of Coffee Panama",
    dateRange: "2026年10月22日〜25日",
    startDate: "2026-10-22",
    relatedCountry: "パナマ",
    note: "エスプレッソ・ミルクドリンク・シグネチャードリンクを競う世界大会(第26回)。",
    sourceUrl: "https://wcc.coffee/world-barista-championship",
  },
  {
    source: "SCAJ(日本スペシャルティコーヒー協会)",
    sourceId: "scaj",
    name: "SCAJ2026 ワールドスペシャルティコーヒーカンファレンス&エキシビション",
    eventType: "exhibition",
    venue: "東京ビッグサイト 南展示棟1-4ホール",
    dateRange: "2026年10月14日〜17日",
    relatedCountry: "日本",
    note: "日本のスペシャルティコーヒー展示会。南3-4ホールは10月14日〜17日、南1-2ホールは14日〜16日。前回(2025年)の来場者は4日間で96,823名(SCAJ2026開催概要による)。",
    sourceUrl: "https://scajconference.jp/overview",
  },
  {
    source: "ACE(Alliance for Coffee Excellence)",
    sourceId: "ace",
    name: "Guatemala Cup of Excellence 2026",
    eventType: "auction",
    venue: "グアテマラ",
    dateRange: "COE審査: 6月1日〜4日 / オークション: 7月23日(13:00 UTC)",
    relatedCountry: "グアテマラ",
    note: "グアテマラのCup of Excellence 2026。優勝豆はオンラインオークションで販売される(COE公式の年別データによる)。",
    sourceUrl: "https://cupofexcellence.org/",
  },
  {
    source: "ACE(Alliance for Coffee Excellence)",
    sourceId: "ace",
    name: "Nicaragua Cup of Excellence 2026",
    eventType: "auction",
    venue: "ニカラグア",
    dateRange: "日程はCOE公式サイトを参照",
    relatedCountry: null,
    note: "ニカラグアのCup of Excellence 2026。",
    sourceUrl: "https://cupofexcellence.org/",
  },
];

export const EVENT_TYPE_LABELS = {
  competition: { ja: "競技会", en: "Competition", color: "#D4A24E" },
  exhibition: { ja: "展示会", en: "Exhibition", color: "#6DA7EC" },
  auction: { ja: "オークション", en: "Auction", color: "#CDE2FB" },
  festival: { ja: "フェスティバル", en: "Festival", color: "#E8956D" },
  seminar: { ja: "セミナー", en: "Seminar", color: "#A8C97F" },
};
