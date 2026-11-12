import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { loadStoredJson } from "../utils/storage";
import { evaluateAchievements } from "../utils/achievements";

const STORAGE_KEY = "coffee-finder:achievements";
// 獲得した直後(この時間内に条件を満たした)ものだけ、お知らせを出す。
// 過去の記録からさかのぼって獲得したもの(アップデート後の初回など)は、静かに記録する。
const FRESH_MS = 5 * 60 * 1000;

function load() {
  return loadStoredJson(
    STORAGE_KEY,
    (parsed) => {
      if (parsed === null) return { value: {} };
      if (typeof parsed !== "object" || Array.isArray(parsed)) return null;
      const entries = Object.entries(parsed);
      const kept = entries.filter(([, v]) => typeof v === "string");
      return { value: Object.fromEntries(kept), lossy: kept.length !== entries.length };
    },
    {}
  );
}

// 実績の獲得状況。条件は、記録(events・ratingTimes)から毎回計算する。
// 獲得した実績は、獲得日とともに端末に残す(あとで記録を消しても、獲得した実績は消えない)。
export function useAchievements({ events, ratingTimes }) {
  const [earned, setEarned] = useState(load);
  const [fresh, setFresh] = useState([]);
  const earnedRef = useRef(earned);
  earnedRef.current = earned;

  const { results, visitedPrefectures, triedOrigins } = useMemo(
    () => evaluateAchievements(events, ratingTimes),
    [events, ratingTimes]
  );

  useEffect(() => {
    const add = {};
    const freshIds = [];
    const now = Date.now();
    for (const { def, earnedAt } of results) {
      if (earnedAt === null || def.id in earnedRef.current) continue;
      add[def.id] = new Date(earnedAt).toISOString();
      if (now - earnedAt <= FRESH_MS) freshIds.push(def.id);
    }
    if (Object.keys(add).length === 0) return;
    earnedRef.current = { ...earnedRef.current, ...add };
    setEarned(earnedRef.current);
    if (freshIds.length > 0) setFresh((prev) => [...prev, ...freshIds]);
  }, [results]);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(earned));
    } catch {
      // 保存できない環境では、獲得状況の保存をスキップ
    }
  }, [earned]);

  const items = useMemo(
    () =>
      results.map(({ def, progress }) => {
        const earnedAt = earned[def.id] ?? null;
        return { ...def, earnedAt, progress: earnedAt ? def.goal : progress };
      }),
    [results, earned]
  );

  // お知らせを出し終えたら呼ぶ
  const consumeFresh = useCallback(() => setFresh([]), []);
  const freshItems = useMemo(() => items.filter((item) => fresh.includes(item.id)), [items, fresh]);

  return {
    items,
    earnedCount: items.filter((item) => item.earnedAt).length,
    visitedPrefectures,
    triedOrigins,
    freshItems,
    consumeFresh,
  };
}
