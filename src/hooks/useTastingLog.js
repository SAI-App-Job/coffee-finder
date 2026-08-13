import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "coffee-finder:tasting-logs";

function loadLogs() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return typeof parsed === "object" && parsed !== null && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

function generateId() {
  return typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

// 商品(豆)1件に対して複数件の抽出記録を持てるテイスティングログ。
// レコードは { [productId]: TastingLogEntry[] }。★評価(useRatings.js)とは
// 完全に独立したストレージ・軸だが、同じ商品IDをキーにしているため、
// 商品詳細画面で評価とログをまとめて振り返ることができる。
export function useTastingLog() {
  const [logsByProduct, setLogsByProduct] = useState(loadLogs);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(logsByProduct));
    } catch {
      // プライベートブラウジング等でlocalStorageが使えない場合は保存をスキップ
    }
  }, [logsByProduct]);

  const getLogs = useCallback((id) => logsByProduct[String(id)] ?? [], [logsByProduct]);

  const addLog = useCallback((id, entry) => {
    const key = String(id);
    const record = { id: generateId(), recordedAt: new Date().toISOString(), ...entry };
    setLogsByProduct((prev) => ({ ...prev, [key]: [record, ...(prev[key] ?? [])] }));
  }, []);

  const deleteLog = useCallback((id, entryId) => {
    const key = String(id);
    setLogsByProduct((prev) => {
      const remaining = (prev[key] ?? []).filter((entry) => entry.id !== entryId);
      const next = { ...prev };
      if (remaining.length === 0) {
        delete next[key];
      } else {
        next[key] = remaining;
      }
      return next;
    });
  }, []);

  return { logsByProduct, getLogs, addLog, deleteLog };
}
