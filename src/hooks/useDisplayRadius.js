import { useEffect, useState } from "react";

const STORAGE_KEY = "coffee-finder:display-radius";

// ランダム表示にのみ適用する表示範囲設定(マイページ)。値はkm単位の数値、
// または"auto"(段階的拡大方式)・"all"(全国、絞り込み無し)。
export const DISPLAY_RADIUS_OPTIONS = [
  { id: "auto", label: "自動(おすすめ)" },
  { id: "5", label: "5km" },
  { id: "20", label: "20km" },
  { id: "50", label: "50km" },
  { id: "all", label: "全国" },
];
export const DEFAULT_DISPLAY_RADIUS_ID = "auto";

function loadDisplayRadiusId() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return DISPLAY_RADIUS_OPTIONS.some((o) => o.id === raw) ? raw : DEFAULT_DISPLAY_RADIUS_ID;
  } catch {
    return DEFAULT_DISPLAY_RADIUS_ID;
  }
}

export function useDisplayRadius() {
  const [displayRadiusId, setDisplayRadiusId] = useState(loadDisplayRadiusId);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, displayRadiusId);
    } catch {
      // プライベートブラウジング等でlocalStorageが使えない場合は保存をスキップ
    }
  }, [displayRadiusId]);

  return { displayRadiusId, setDisplayRadiusId, options: DISPLAY_RADIUS_OPTIONS };
}
