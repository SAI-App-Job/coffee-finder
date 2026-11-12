import { useCallback, useEffect, useState } from "react";
import { loadStoredJson } from "../utils/storage";
import { mergeEntries } from "../utils/backupMerge";

const STORAGE_KEY = "coffee-finder:shop-tasting-notes";

function loadNotes() {
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

  // バックアップファイルからの復元用。上書きはせず、無い記録(idで判断)だけを足す
  const importNotes = useCallback(
    (incoming) => {
      const result = mergeEntries(notesByShop, incoming);
      if (result.added > 0) setNotesByShop(result.value);
      return { added: result.added };
    },
    [notesByShop]
  );

  return { notesByShop, getNotes, addNote, deleteNote, importNotes };
}
