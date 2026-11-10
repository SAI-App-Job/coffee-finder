import { PREFECTURE_REGIONS } from "../data/prefectures";
import { EVENT_KINDS, localDateKey } from "./diary";
import { getLang } from "../i18n";

// 実績(チャレンジ)。記録(ログ・ノート・商品登録・写真・★評価)から、条件を満たしたものに印(バッジ)を付ける。
// 文言は、辞書(en.js)に入れるため、L("…") で囲む(中身は変えない。npm run i18n:check が拾うための印)。
const L = (s) => s;
const DAY_MS = 24 * 60 * 60 * 1000;
const WEEK_MS = 7 * DAY_MS;

// 実績の文言に入れる値({n}・{region})。地方名は、英語表示のときは英語名を使う。
export const achievementParams = (item) => ({
  n: item.goal,
  region: getLang() === "en" ? (item.regionEn ?? "") : (item.regionName ?? ""),
});

export const ACHIEVEMENT_GROUPS = [
  { id: "records", title: L("記録を重ねる") },
  { id: "weekly", title: L("1週間チャレンジ") },
  { id: "streak", title: L("毎日の記録") },
  { id: "origin", title: L("産地めぐり") },
  { id: "prefecture", title: L("都道府県制覇") },
];

// 条件(rule)の種類:
//   count   : 記録の累計(kind の件数)
//   window  : 7日間に kinds を合計 goal 件
//   streak  : 記録のある日が goal 日連続
//   distinct: 試した産地が goal か国
//   prefs   : お店を訪れた(商品登録・テイスティングノートのある)都道府県が goal
//   region  : 地方の全都道府県を訪れた
function tiers(group, icon, goals, title, desc, rule) {
  return goals.map((n) => ({ id: `${group}-${icon}-${n}`, group, icon, goal: n, title, desc, rule }));
}

export const ACHIEVEMENTS = [
  // 記録を重ねる
  ...tiers("records", "log", [1, 10, 30, 100], L("テイスティングログ{n}件"), L("テイスティングログを{n}件記録する"), { type: "count", kind: "log" }),
  ...tiers("records", "note", [1, 5, 20, 50], L("テイスティングノート{n}件"), L("テイスティングノートを{n}件記録する"), { type: "count", kind: "note" }),
  ...tiers("records", "register", [1, 5, 20, 50], L("商品を{n}件登録"), L("手動で商品を{n}件登録する"), { type: "count", kind: "register" }),
  ...tiers("records", "photo", [1, 5, 20, 50], L("パッケージ写真{n}枚"), L("パッケージ写真を{n}枚追加する"), { type: "count", kind: "photo" }),
  ...tiers("records", "rating", [5, 20, 50], L("★評価{n}件"), L("商品に★評価を{n}件つける"), { type: "count", kind: "rating" }),
  // 1週間チャレンジ
  ...tiers("weekly", "note", [3, 7], L("1週間でテイスティングノート{n}件"), L("7日間に、テイスティングノートを{n}件記録する"), { type: "window", kinds: ["note"] }),
  ...tiers("weekly", "log", [3, 7], L("1週間でテイスティングログ{n}件"), L("7日間に、テイスティングログを{n}件記録する"), { type: "window", kinds: ["log"] }),
  ...tiers("weekly", "register", [3, 5], L("1週間で商品登録{n}件"), L("7日間に、商品を{n}件登録する"), { type: "window", kinds: ["register"] }),
  ...tiers("weekly", "all", [10], L("1週間で記録{n}件"), L("7日間に、ログ・ノート・商品登録・写真を合わせて{n}件記録する"), { type: "window", kinds: EVENT_KINDS }),
  // 毎日の記録
  ...tiers("streak", "streak", [3, 7, 30], L("{n}日連続で記録"), L("{n}日続けて、ログ・ノート・商品登録・写真のどれかを記録する"), { type: "streak" }),
  // 産地めぐり
  ...tiers("origin", "origin", [3, 5, 10], L("{n}か国の産地を試す"), L("登録した商品やログをつけた豆で、{n}か国の産地を試す"), { type: "distinct" }),
  // 都道府県制覇
  ...tiers("prefecture", "prefecture", [3, 10, 20], L("{n}都道府県を訪れる"), L("{n}都道府県のお店で、商品を登録するか、テイスティングノートを記録する"), { type: "prefs" }),
  ...PREFECTURE_REGIONS.map((region) => ({
    id: `prefecture-region-${region.id}`,
    group: "prefecture",
    icon: "region",
    goal: region.prefectures.length,
    title: L("{region}制覇"),
    desc: L("{region}の全{n}都道府県のお店で、商品を登録するか、テイスティングノートを記録する"),
    rule: { type: "region", region },
    regionName: region.name,
    regionEn: region.en,
  })),
  {
    id: "prefecture-all",
    group: "prefecture",
    icon: "trophy",
    goal: 47,
    title: L("都道府県制覇"),
    desc: L("全国47都道府県のお店で、商品を登録するか、テイスティングノートを記録する"),
    rule: { type: "prefs" },
  },
];

// 日記に出す「次の目標」: 系列(同じ種類の段階)ごとに、まだ獲得していない最初の段階を選び、
// 進み具合(進捗/目標)が大きい順に limit 件返す。進捗が同じなら、目標の小さいものが先。
// items: useAchievements の items(earnedAt・progress・goal を持つ)
export function nextGoals(items, limit = 3) {
  const seriesOf = (id) => id.replace(/-\d+$/, "");
  const next = new Map();
  for (const item of items) {
    if (item.earnedAt) continue;
    const key = seriesOf(item.id);
    const cur = next.get(key);
    if (!cur || item.goal < cur.goal) next.set(key, item);
  }
  return [...next.values()]
    .sort((a, b) => b.progress / b.goal - a.progress / a.goal || a.goal - b.goal)
    .slice(0, limit);
}

// 今の連続記録日数。今日か昨日に記録があれば、そこから過去へ連続する日数(どちらも無ければ 0)。
// events: buildDiaryEvents の結果。未来の日時は数えない。
export function currentStreak(events, now = new Date()) {
  const days = new Set(events.filter((e) => e.t <= now.getTime()).map((e) => localDateKey(e.t)));
  const day = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  if (!days.has(localDateKey(day.getTime()))) day.setDate(day.getDate() - 1);
  let n = 0;
  while (days.has(localDateKey(day.getTime()))) {
    n += 1;
    day.setDate(day.getDate() - 1);
  }
  return n;
}

// ts(昇順)のうち、7日間に入る最大件数と、goal 件に初めて届いた時刻
function windowResult(ts, goal) {
  let start = 0;
  let max = 0;
  let earnedAt = null;
  for (let end = 0; end < ts.length; end += 1) {
    while (ts[end] - ts[start] >= WEEK_MS) start += 1;
    const count = end - start + 1;
    if (count > max) max = count;
    if (earnedAt === null && count >= goal) earnedAt = ts[end];
  }
  return { progress: max, earnedAt };
}

// 記録のある日(昇順・重複なし)から、最長の連続日数と、goal 日に初めて届いた日
function streakResult(ts, goal) {
  const days = [...new Set(ts.map(localDateKey))].sort();
  let run = 0;
  let max = 0;
  let earnedAt = null;
  let prev = null;
  for (const key of days) {
    const [y, m, d] = key.split("-").map(Number);
    const dayNumber = Math.round(Date.UTC(y, m - 1, d) / DAY_MS);
    run = prev !== null && dayNumber - prev === 1 ? run + 1 : 1;
    prev = dayNumber;
    if (run > max) max = run;
    if (earnedAt === null && run >= goal) earnedAt = new Date(y, m - 1, d, 12).getTime();
  }
  return { progress: max, earnedAt };
}

// 値(産地・都道府県)が、初めて現れた時刻
function firstSeen(list) {
  const map = new Map();
  for (const { t, value } of list) if (value && !map.has(value)) map.set(value, t);
  return map;
}

// events: buildDiaryEvents の結果(時刻の昇順)、ratingTimes: ★評価をつけた時刻(ms)の配列
// 返り値: { results: [{ def, progress, earnedAt(ms|null) }], visitedPrefectures: Set, triedOrigins: Set }
export function evaluateAchievements(events, ratingTimes) {
  const byKind = { rating: [...ratingTimes].sort((a, b) => a - b) };
  for (const kind of EVENT_KINDS) byKind[kind] = events.filter((e) => e.kind === kind).map((e) => e.t);
  const allTimes = events.map((e) => e.t);

  const prefSeen = firstSeen(events.filter((e) => e.kind === "register" || e.kind === "note").map((e) => ({ t: e.t, value: e.prefecture })));
  const originSeen = firstSeen(events.filter((e) => e.kind === "register" || e.kind === "log").map((e) => ({ t: e.t, value: (e.origin ?? "").trim() })));
  const prefTimes = [...prefSeen.values()].sort((a, b) => a - b);
  const originTimes = [...originSeen.values()].sort((a, b) => a - b);

  const results = ACHIEVEMENTS.map((def) => {
    const { rule, goal } = def;
    let progress = 0;
    let earnedAt = null;
    if (rule.type === "count") {
      const ts = byKind[rule.kind];
      progress = Math.min(ts.length, goal);
      earnedAt = ts.length >= goal ? ts[goal - 1] : null;
    } else if (rule.type === "window") {
      const ts = rule.kinds.flatMap((k) => byKind[k]).sort((a, b) => a - b);
      ({ progress, earnedAt } = windowResult(ts, goal));
    } else if (rule.type === "streak") {
      ({ progress, earnedAt } = streakResult(allTimes, goal));
    } else if (rule.type === "distinct") {
      progress = Math.min(originTimes.length, goal);
      earnedAt = originTimes.length >= goal ? originTimes[goal - 1] : null;
    } else if (rule.type === "prefs") {
      progress = Math.min(prefTimes.length, goal);
      earnedAt = prefTimes.length >= goal ? prefTimes[goal - 1] : null;
    } else if (rule.type === "region") {
      const times = rule.region.prefectures.map((p) => prefSeen.get(p)).filter((t) => t !== undefined);
      progress = times.length;
      earnedAt = times.length === goal ? Math.max(...times) : null;
    }
    return { def, progress: Math.min(progress, goal), earnedAt };
  });

  return { results, visitedPrefectures: new Set(prefSeen.keys()), triedOrigins: new Set(originSeen.keys()) };
}
