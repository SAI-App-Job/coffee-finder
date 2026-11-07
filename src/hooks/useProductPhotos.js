import { useCallback, useEffect, useRef, useState } from "react";

const DB_NAME = "coffee-finder-photos";
const STORE = "photos";
// 写真を追加した日(日記・実績の集計用)。この記録を始める前から保存していた写真・バックアップから戻した写真は、日付を持たない。
const DATES_KEY = "coffee-finder:photo-dates";

function loadDates() {
  try {
    const parsed = JSON.parse(localStorage.getItem(DATES_KEY) ?? "null");
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    return Object.fromEntries(Object.entries(parsed).filter(([, v]) => typeof v === "string" && !Number.isNaN(new Date(v).getTime())));
  } catch {
    return {};
  }
}

function openDb() {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") {
      reject(new Error("indexeddb-unavailable"));
      return;
    }
    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(STORE);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function run(db, mode, action) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, mode);
    const request = action(tx.objectStore(STORE));
    tx.oncomplete = () => resolve(request?.result);
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error);
  });
}

// 商品のパッケージ写真。localStorage は容量が小さい(約5MB)うえ、あふれると他のデータの保存まで
// 失敗するので、写真は IndexedDB に別保存する。キーは商品ID(アプリ収録の商品も、手動登録した商品も同じ)。
// 値は縮小済みの JPEG(Blob)。表示用には、読み込んだ Blob から作った URL を使う。
export function useProductPhotos() {
  const [urls, setUrls] = useState({});
  const [dates, setDates] = useState(loadDates);
  const dbRef = useRef(null);
  const urlsRef = useRef({});
  urlsRef.current = urls;

  useEffect(() => {
    let cancelled = false;
    const created = [];
    (async () => {
      try {
        const db = await openDb();
        if (cancelled) {
          db.close();
          return;
        }
        dbRef.current = db;
        const [keys, blobs] = await Promise.all([
          run(db, "readonly", (s) => s.getAllKeys()),
          run(db, "readonly", (s) => s.getAll()),
        ]);
        if (cancelled) return;
        const loaded = {};
        keys.forEach((key, i) => {
          const url = URL.createObjectURL(blobs[i]);
          created.push(url);
          loaded[key] = url;
        });
        setUrls((prev) => ({ ...loaded, ...prev }));
      } catch {
        // IndexedDB が使えない環境(プライベートブラウジング等)では、写真機能は使えない
      }
    })();
    return () => {
      cancelled = true;
      created.forEach((u) => URL.revokeObjectURL(u));
    };
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(DATES_KEY, JSON.stringify(dates));
    } catch {
      // 保存できない環境では、日付の保存をスキップ
    }
  }, [dates]);

  const getPhotoUrl = useCallback((productId) => urls[productId] ?? null, [urls]);

  // 保存できたら true。失敗(容量不足・IndexedDB 非対応など)は false を返す。
  // restore: バックアップからの復元。追加した日として数えない(日付を付けない)。
  const setPhoto = useCallback(async (productId, blob, { restore = false } = {}) => {
    try {
      const db = dbRef.current ?? (dbRef.current = await openDb());
      await run(db, "readwrite", (s) => s.put(blob, productId));
      const url = URL.createObjectURL(blob);
      const old = urlsRef.current[productId];
      setUrls((prev) => ({ ...prev, [productId]: url }));
      if (old) URL.revokeObjectURL(old);
      if (!restore) setDates((prev) => (prev[productId] ? prev : { ...prev, [productId]: new Date().toISOString() }));
      return true;
    } catch {
      return false;
    }
  }, []);

  const removePhotos = useCallback(async (productIds) => {
    const ids = productIds.filter((id) => id in urlsRef.current);
    if (ids.length === 0) return;
    try {
      const db = dbRef.current ?? (dbRef.current = await openDb());
      await run(db, "readwrite", (s) => {
        ids.forEach((id) => s.delete(id));
      });
    } catch {
      // 消せなくても、画面からは外す(次回起動時に残っていれば再び表示されるだけ)
    }
    ids.forEach((id) => URL.revokeObjectURL(urlsRef.current[id]));
    setUrls((prev) => {
      const next = { ...prev };
      ids.forEach((id) => delete next[id]);
      return next;
    });
    setDates((prev) => {
      if (!ids.some((id) => id in prev)) return prev;
      const next = { ...prev };
      ids.forEach((id) => delete next[id]);
      return next;
    });
  }, []);

  const removePhoto = useCallback((productId) => removePhotos([productId]), [removePhotos]);

  // --- バックアップ用 ---

  // 保存されている写真すべて({ id, blob }[])
  const exportPhotos = useCallback(async () => {
    try {
      const db = dbRef.current ?? (dbRef.current = await openDb());
      const [keys, blobs] = await Promise.all([
        run(db, "readonly", (s) => s.getAllKeys()),
        run(db, "readonly", (s) => s.getAll()),
      ]);
      return keys.map((id, i) => ({ id, blob: blobs[i] }));
    } catch {
      return [];
    }
  }, []);

  // 保存されている写真の合計バイト数(バックアップに含めたときの目安の計算用)
  const getPhotoBytes = useCallback(async () => {
    const entries = await exportPhotos();
    return entries.reduce((sum, e) => sum + e.blob.size, 0);
  }, [exportPhotos]);

  // バックアップからの復元。すでに写真がある商品は上書きしない。1枚ずつ書き込む
  // (途中で止まっても、そこまでの分は残る)。
  const importPhotos = useCallback(
    async (entries) => {
      const result = { added: 0, skipped: 0, failed: 0 };
      for (const { id, blob } of entries) {
        if (id in urlsRef.current) {
          result.skipped += 1;
        } else if (await setPhoto(id, blob, { restore: true })) {
          result.added += 1;
        } else {
          result.failed += 1;
        }
      }
      return result;
    },
    [setPhoto]
  );

  const photoIds = Object.keys(urls);
  const photoCount = photoIds.length;

  return { getPhotoUrl, setPhoto, removePhoto, removePhotos, photoIds, photoDates: dates, photoCount, exportPhotos, getPhotoBytes, importPhotos };
}
