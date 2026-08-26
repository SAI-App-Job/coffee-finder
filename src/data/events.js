// ---------------------------------------------------------------------------
// 大会・イベントデータ(scrape_events_wcc.py / scrape_events_scaj.py /
// scrape_events_ace.py で検証済みの構造を基にした静的データ)
// ---------------------------------------------------------------------------
export const EVENTS = [
  {
    source: "WCC(World Coffee Championships)",
    name: "World Brewers Cup 2026",
    eventType: "competition",
    venue: "World of Coffee Brussels",
    dateRange: "2026年6月25日〜27日",
    relatedCountry: null,
    note: "手淹れ抽出の技術を競う世界大会。PHILOCOFFEA(粕谷哲氏)は2016年大会の優勝者。",
    sourceUrl: "https://wcc.coffee/world-brewers-cup",
  },
  {
    source: "WCC(World Coffee Championships)",
    name: "World Barista Championship 2026",
    eventType: "competition",
    venue: "World of Coffee Panama",
    dateRange: "2026年10月22日〜25日",
    relatedCountry: "パナマ",
    note: "エスプレッソ・ミルクドリンク・シグネチャードリンクを競う、最も歴史のある世界大会(2000年開始)。",
    sourceUrl: "https://wcc.coffee/world-barista-championship",
  },
  {
    source: "SCAJ(日本スペシャルティコーヒー協会)",
    name: "SCAJ2026 ワールドスペシャルティコーヒーカンファレンス&エキシビション",
    eventType: "exhibition",
    venue: "東京ビッグサイト 南展示棟1-4ホール",
    dateRange: "2026年10月14日〜17日",
    relatedCountry: "日本",
    note: "日本最大級のスペシャルティコーヒー展示会。前回は4日間で75,000人超が来場。",
    sourceUrl: "https://scajconference.jp/overview",
  },
  {
    source: "ACE(Alliance for Coffee Excellence)",
    name: "Guatemala Cup of Excellence 2026",
    eventType: "auction",
    venue: "グアテマラ",
    dateRange: "COE(オークション): 7月15日 / NW(審査週間): 7月14日〜18日",
    relatedCountry: "グアテマラ",
    note: "「コーヒーのオリンピック」と呼ばれる国際品評会。優勝豆はオンラインオークションで販売され、生産者に直接利益が渡る。",
    sourceUrl: "https://cupofexcellence.org/",
  },
  {
    source: "ACE(Alliance for Coffee Excellence)",
    name: "Nicaragua Cup of Excellence 2026",
    eventType: "auction",
    venue: "ニカラグア",
    dateRange: "COE(オークション): 6月19日",
    relatedCountry: null,
    note: "2026年シーズンの開幕を飾る大会。",
    sourceUrl: "https://cupofexcellence.org/",
  },
];

export const EVENT_TYPE_LABELS = {
  competition: { ja: "競技会", color: "#D4A24E" },
  exhibition: { ja: "展示会", color: "#6DA7EC" },
  auction: { ja: "オークション", color: "#CDE2FB" },
  festival: { ja: "フェスティバル", color: "#E8956D" },
};
