import { useCallback, useEffect, useState } from "react";
import { loadStoredJson } from "../utils/storage";
import { mergeEntries } from "../utils/backupMerge";

const STORAGE_KEY = "coffee-finder:tasting-logs";

function loadLogs() {
  // 読めなかった・形が違うときは、元の文字列を残してから、空で始める(utils/storage.js)
  return loadStoredJson(
    STORAGE_KEY,
    (parsed) => (parsed === null ? { value: {} } : typeof parsed === "object" && !Array.isArray(parsed) ? { value: parsed } : null),
    {}
  );
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

  // 商品の削除に合わせて、その商品のログをまとめて消す(サンプルの削除用)
  const clearLogs = useCallback((ids) => {
    const keys = ids.map(String);
    setLogsByProduct((prev) => {
      if (!keys.some((k) => k in prev)) return prev;
      const next = { ...prev };
      keys.forEach((k) => delete next[k]);
      return next;
    });
  }, []);

  // バックアップファイルからの復元用。上書きはせず、無い記録(idで判断)だけを足す
  const importLogs = useCallback(
    (incoming) => {
      const result = mergeEntries(logsByProduct, incoming);
      if (result.added > 0) setLogsByProduct(result.value);
      return { added: result.added };
    },
    [logsByProduct]
  );

  return { logsByProduct, getLogs, addLog, deleteLog, clearLogs, importLogs };
}
