// 特定銘柄14種(全日本コーヒー公正取引協議会)。countryはORIGIN_GUIDEのcountryと
// 一致させ、産地カードとの相互リンクに使う(ハワイのみORIGIN_GUIDE側の表記に合わせて
// 「ハワイ」、キューバは対象国リストに含まれないためnullにしている)。
export const DESIGNATED_BRANDS = [
  { name: "ブルーマウンテン", country: "ジャマイカ", note: null },
  { name: "ハイマウンテン", country: "ジャマイカ", note: null },
  { name: "ジャマイカ", country: "ジャマイカ", note: "ブルーマウンテン・ハイマウンテン以外" },
  { name: "クリスタルマウンテン", country: null, note: "キューバ産(地図の対象国には未収録)" },
  { name: "グアテマラアンティグア", country: "グアテマラ", note: null },
  { name: "コロンビアスプレモ", country: "コロンビア", note: null },
  { name: "モカ・ハラー", country: "エチオピア", note: "ハラー地区産のみ" },
  { name: "モカ・マタリ", country: "イエメン", note: null },
  { name: "キリマンジャロ", country: "タンザニア", note: "ブコバ地区産を除く" },
  { name: "トラジャ", country: "インドネシア", note: "スラウェシ島トラジャ地区産" },
  { name: "カロシ", country: "インドネシア", note: "スラウェシ島カロシ地区産" },
  { name: "ガヨマウンテン", country: "インドネシア", note: "スマトラ島タケンゴン地区産" },
  { name: "マンデリン", country: "インドネシア", note: "ガヨマウンテン地区を除く" },
  { name: "ハワイコナ", country: "ハワイ", note: null },
];
