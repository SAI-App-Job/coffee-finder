import { useCallback, useEffect, useState } from "react";
import { loadStoredJson } from "../utils/storage";

const STORAGE_KEY = "coffee-finder:product-snapshots";

// 利用者が「保存・評価・記録」した、アプリ収録の商品の、名前・店名・産地の控え。
// 商品データ(GitHub上のJSON)は、販売が終わった商品が、取得し直すと消えることがある。その商品の、お気に入り・★・テイスティングログが、
// 端末に残っていても、名前が分からないと、日記などで空になる。そのため、商品が見えているうちに、名前を控えておく。
// レコード: { [商品ID]: { name, shopName, originCountry, savedAt } }
// 商品が見えている間は、最新の名前に更新する。消えたあとは、最後に控えた内容を残す。
const asText = (v) => (typeof v === "string" ? v.trim() : "");

function sanitize(raw) {
  if (!raw || typeof raw !== "object") return null;
  const name = asText(raw.name);
  if (!name) return null;
  return { name, shopName: asText(raw.shopName), originCountry: asText(raw.originCountry), savedAt: asText(raw.savedAt) || new Date().toISOString() };
}

function load() {
  return loadStoredJson(
    STORAGE_KEY,
    (parsed) => {
      if (parsed === null) return { value: {} };
      if (typeof parsed !== "object" || Array.isArray(parsed)) return null;
      const entries = Object.entries(parsed);
      const kept = entries.map(([id, v]) => [id, sanitize(v)]).filter(([, v]) => v);
      return { value: Object.fromEntries(kept), lossy: kept.length !== entries.length };
    },
    {}
  );
}

// ids: 利用者が、保存・評価・記録した商品のID。productsById: いま収録されている商品(Map)
export function useProductSnapshots(ids, productsById) {
  const [snapshots, setSnapshots] = useState(load);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshots));
    } catch {
      // 保存できない環境では、控えの保存をスキップ
    }
  }, [snapshots]);

  useEffect(() => {
    const updates = {};
    for (const id of ids) {
      const p = productsById.get(id);
      if (!p) continue;
      const next = sanitize({ name: p.rawName, shopName: p.shopName, originCountry: p.originCountry });
      if (!next) continue;
      const cur = snapshots[id];
      if (cur && cur.name === next.name && cur.shopName === next.shopName && cur.originCountry === next.originCountry) continue;
      updates[id] = { ...next, savedAt: new Date().toISOString() };
    }
    if (Object.keys(updates).length > 0) setSnapshots((prev) => ({ ...prev, ...updates }));
  }, [ids, productsById, snapshots]);

  // バックアップファイルからの復元用。すでにある控えは、そのまま(新しいものを優先)
  const importSnapshots = useCallback((raw) => {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return 0;
    const incoming = Object.fromEntries(Object.entries(raw).map(([id, v]) => [id, sanitize(v)]).filter(([, v]) => v));
    let added = 0;
    setSnapshots((prev) => {
      const merged = { ...prev };
      for (const [id, v] of Object.entries(incoming)) {
        if (!merged[id]) {
          merged[id] = v;
          added++;
        }
      }
      return added > 0 ? merged : prev;
    });
    return Object.keys(incoming).length;
  }, []);

  return { snapshots, importSnapshots };
}
