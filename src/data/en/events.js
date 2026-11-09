// 大会・イベント(src/data/events.js の静的データ)の英訳。キーは name。
// 開催日・会場・説明の訳で、事実は変えていない。取得データ(data/events.json)のイベントは、日付だけ英語の書式に直す。
export const EVENTS_EN = {
  "World Brewers Cup 2026": {
    dateRange: "June 25-27, 2026",
    note: "A world competition contesting hand-brewing skill. Tetsu Kasuya won the 2016 competition.",
  },
  "World Barista Championship 2026": {
    dateRange: "October 22-25, 2026",
    note: "A world competition contesting espresso, milk drinks and signature drinks (the 26th edition).",
  },
  "SCAJ2026 ワールドスペシャルティコーヒーカンファレンス&エキシビション": {
    name: "SCAJ 2026 World Specialty Coffee Conference & Exhibition",
    venue: "Tokyo Big Sight, South Halls 1-4",
    dateRange: "October 14-17, 2026",
    note: "A specialty coffee exhibition in Japan. South Halls 3-4 run October 14-17 and South Halls 1-2 run October 14-16. The previous edition (2025) drew 96,823 visitors over four days (per the SCAJ 2026 overview).",
  },
  "Guatemala Cup of Excellence 2026": {
    venue: "Guatemala",
    dateRange: "COE judging: June 1-4 / auction: July 23 (13:00 UTC)",
    note: "Guatemala Cup of Excellence 2026. The winning lots are sold in an online auction (per the COE official yearly data).",
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
