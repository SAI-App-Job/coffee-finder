import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "coffee-finder:shop-tasting-notes";

function loadNotes() {
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

// 店舗だけで出会った豆(アプリに商品として載っていない豆)のテイスティングノート。
// レコードは { [shopName]: { id, recordedAt, productName, note, flavors }[] }。
// 商品に紐づくテイスティングログ(useTastingLog.js)とは別のストレージで、
// 商品IDではなく店舗名をキーにする。
export function useShopTastingNotes() {
  const [notesByShop, setNotesByShop] = useState(loadNotes);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(notesByShop));
    } catch {
      // プライベートブラウジング等でlocalStorageが使えない場合は保存をスキップ
    }
  }, [notesByShop]);

  const getNotes = useCallback((shopName) => notesByShop[shopName] ?? [], [notesByShop]);

  const addNote = useCallback((shopName, entry) => {
    const record = { id: generateId(), recordedAt: new Date().toISOString(), ...entry };
    setNotesByShop((prev) => ({ ...prev, [shopName]: [record, ...(prev[shopName] ?? [])] }));
  }, []);

  const deleteNote = useCallback((shopName, noteId) => {
    setNotesByShop((prev) => {
      const remaining = (prev[shopName] ?? []).filter((n) => n.id !== noteId);
      const next = { ...prev };
      if (remaining.length === 0) {
        delete next[shopName];
      } else {
        next[shopName] = remaining;
      }
      return next;
    });
  }, []);

  return { notesByShop, getNotes, addNote, deleteNote };
}
