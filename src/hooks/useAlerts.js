import { useCallback, useEffect, useState } from "react";
import { buildAlertSnapshot, diffAlertSnapshot } from "../utils/alerts";

const SNAPSHOT_KEY = "coffee-finder:alert-snapshot";
const ALERTS_KEY = "coffee-finder:alerts";

function loadJSON(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

// 本物のプッシュ通知(OS通知センター)は使わず、「アプリを開いた時に前回訪問時
// からの変化をまとめて見せる」定期チェック型の通知。前回起動時点のスナップ
// ショットをlocalStorageに保存しておき、起動のたびに1回だけ現在のデータと
// 突き合わせて値下げ・在庫復活・(お気に入り店舗の)新商品を検出する。
export function useAlerts(products, favoriteIds, favoriteShopNames, ready) {
  const [alerts, setAlerts] = useState(() => loadJSON(ALERTS_KEY, []));
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    // remoteLoadedになる前(モックデータの段階)で診断すると、実データの
    // スナップショットと商品IDの体系が異なり誤判定・誤上書きするため待つ。
    if (!ready || checked) return;
    setChecked(true);

    const prevSnapshot = loadJSON(SNAPSHOT_KEY, null);
    const nextSnapshot = buildAlertSnapshot(products, favoriteIds, favoriteShopNames);

    if (prevSnapshot) {
      const newAlerts = diffAlertSnapshot(prevSnapshot, nextSnapshot, products);
      if (newAlerts.length > 0) {
        setAlerts((prev) => {
          const existingIds = new Set(prev.map((a) => a.id));
          const merged = [...newAlerts.filter((a) => !existingIds.has(a.id)), ...prev];
          try {
            localStorage.setItem(ALERTS_KEY, JSON.stringify(merged));
          } catch {
            // プライベートブラウジング等でlocalStorageが使えない場合は保存をスキップ
          }
          return merged;
        });
      }
    }

    try {
      localStorage.setItem(SNAPSHOT_KEY, JSON.stringify(nextSnapshot));
    } catch {
      // プライベートブラウジング等でlocalStorageが使えない場合は保存をスキップ
    }
  }, [ready, checked, products, favoriteIds, favoriteShopNames]);

  const dismissAlerts = useCallback(() => {
    setAlerts([]);
    try {
      localStorage.removeItem(ALERTS_KEY);
    } catch {
      // プライベートブラウジング等でlocalStorageが使えない場合は保存をスキップ
    }
  }, []);

  return { alerts, dismissAlerts };
}
