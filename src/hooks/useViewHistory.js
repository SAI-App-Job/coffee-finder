import { useCallback, useEffect, useMemo, useState } from "react";

const STORAGE_KEY = "coffee-finder:view-history";
export const FREE_HISTORY_RETENTION_DAYS = 7;
// プランに関わらず適用する技術的な上限(無制限プランでも無限にストレージを
// 食い続けないための安全弁。無料プランの7日制限とは別物)。
const MAX_STORED_ENTRIES = 300;

function loadHistory() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

// 保存データ自体は削除せず(無料→有料への切替時に履歴が復活できるように)、
// 表示側でのみ「直近7日」にフィルタする方式にしている。
export function useViewHistory(isPremium) {
  const [rawHistory, setRawHistory] = useState(loadHistory);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(rawHistory));
    } catch {
      // プライベートブラウジング等でlocalStorageが使えない場合は保存をスキップ
    }
  }, [rawHistory]);

  const recordView = useCallback((id) => {
    const key = String(id);
    const viewedAt = new Date().toISOString();
    setRawHistory((prev) => {
      const withoutExisting = prev.filter((entry) => entry.id !== key);
      return [{ id: key, viewedAt }, ...withoutExisting].slice(0, MAX_STORED_ENTRIES);
    });
  }, []);

  const history = useMemo(() => {
    if (isPremium) return rawHistory;
    const cutoff = Date.now() - FREE_HISTORY_RETENTION_DAYS * 24 * 60 * 60 * 1000;
    return rawHistory.filter((entry) => new Date(entry.viewedAt).getTime() >= cutoff);
  }, [rawHistory, isPremium]);

  return { history, recordView };
}
