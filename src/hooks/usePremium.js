import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "coffee-finder:is-premium";

// 現段階ではPlay Billing(Digital Goods API)との実課金連携は未実装のため、
// 「広告非表示」状態を端末内のフラグとして保持するだけの土台。
// 実際の購入検証は、TWAパッケージング確定後にDigital Goods APIの
// listPurchases()結果でこのフラグを更新する形に置き換える想定。
function loadIsPremium() {
  try {
    return localStorage.getItem(STORAGE_KEY) === "true";
  } catch {
    return false;
  }
}

export function usePremium() {
  const [isPremium, setIsPremium] = useState(loadIsPremium);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, String(isPremium));
    } catch {
      // プライベートブラウジング等でlocalStorageが使えない場合は保存をスキップ
    }
  }, [isPremium]);

  const setPremium = useCallback((value) => setIsPremium(value), []);

  return { isPremium, setPremium };
}
