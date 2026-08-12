import { useCallback, useState } from "react";

export const FREE_COMPARE_LIMIT = 3;

// 比較の選択状態は「今セッションで見比べたい商品」という一時的なものなので、
// お気に入りとは異なりlocalStorageへの永続化はしない(アプリを開き直したら空に戻る)。
export function useComparison(isPremium, showToast) {
  const [compareIds, setCompareIds] = useState([]);
  const limit = isPremium ? Infinity : FREE_COMPARE_LIMIT;

  const isComparing = useCallback((id) => compareIds.includes(String(id)), [compareIds]);

  const toggleCompare = useCallback(
    (id) => {
      const key = String(id);
      setCompareIds((prev) => {
        if (prev.includes(key)) return prev.filter((existing) => existing !== key);
        if (!isPremium && prev.length >= FREE_COMPARE_LIMIT) {
          showToast?.(
            `比較は無料プランで${FREE_COMPARE_LIMIT}件までです。有料プランでは無制限に比較できます。`
          );
          return prev;
        }
        return [...prev, key];
      });
    },
    [isPremium, showToast]
  );

  const removeFromCompare = useCallback((id) => {
    const key = String(id);
    setCompareIds((prev) => prev.filter((existing) => existing !== key));
  }, []);

  const clearCompare = useCallback(() => setCompareIds([]), []);

  return { compareIds, isComparing, toggleCompare, removeFromCompare, clearCompare, limit };
}
