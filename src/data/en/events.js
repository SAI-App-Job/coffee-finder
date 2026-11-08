// 大会・イベント(src/data/events.js の静的データ)の英訳。キーは name。
// 開催日・会場・説明の訳で、事実は変えていない。取得データ(data/events.json)のイベントは、日付だけ英語の書式に直す。
export const EVENTS_EN = {
  "World Brewers Cup 2026": {
    dateRange: "June 25-27, 2026",
    note: "A world competition contesting hand-brewing skill. PHILOCOFFEA (Tetsu Kasuya) won the 2016 competition.",
  },
  "World Barista Championship 2026": {
    dateRange: "October 22-25, 2026",
    note: "The most historic world competition (started in 2000), contesting espresso, milk drinks and signature drinks.",
  },
  "SCAJ2026 ワールドスペシャルティコーヒーカンファレンス&エキシビション": {
    name: "SCAJ 2026 World Specialty Coffee Conference & Exhibition",
    venue: "Tokyo Big Sight, South Halls 1-4",
    dateRange: "October 14-17, 2026",
    note: "One of Japan's largest specialty coffee exhibitions. The previous edition drew over 75,000 visitors over four days.",
  },
  "Guatemala Cup of Excellence 2026": {
    venue: "Guatemala",
    dateRange: "COE (auction): July 15 / NW (judging week): July 14-18",
    note: "An international competition called the \"Olympics of coffee.\" The winning lots are sold in an online auction, and the profits go directly to producers.",
  },
  "Nicaragua Cup of Excellence 2026": {
    venue: "Nicaragua",
    dateRange: "COE (auction): June 19",
    note: "The competition that opens the 2026 season.",
  },
};

// 開催元の名前(日本語 → 英語)
export const EVENT_SOURCES_EN = {
  "SCAJ(日本スペシャルティコーヒー協会)": "SCAJ (Specialty Coffee Association of Japan)",
  "珈琲博覧日(onedaycoffeeexpo.com)": "Coffee Expo Day (onedaycoffeeexpo.com)",
};

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const monthName = (m) => MONTHS[Number(m) - 1] ?? String(m);

// 「2026年6月25日〜27日」のような開催日の日本語表記を、英語の書式にする(形が合わないものは、そのまま返す)
export function formatDateRangeEn(text) {
  if (typeof text !== "string") return text;
  let m = text.match(/^(\d{4})年(\d{1,2})月(\d{1,2})日\s*[〜~～-]\s*(\d{1,2})日$/);
  if (m) return `${monthName(m[2])} ${m[3]}-${m[4]}, ${m[1]}`;
  m = text.match(/^(\d{4})年(\d{1,2})月(\d{1,2})日\s*[〜~～-]\s*(\d{1,2})月(\d{1,2})日$/);
  if (m) return `${monthName(m[2])} ${m[3]} - ${monthName(m[4])} ${m[5]}, ${m[1]}`;
  m = text.match(/^(\d{4})年(\d{1,2})月(\d{1,2})日$/);
  if (m) return `${monthName(m[2])} ${m[3]}, ${m[1]}`;
  return text;
}
