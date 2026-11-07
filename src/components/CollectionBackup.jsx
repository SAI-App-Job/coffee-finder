import { useEffect, useRef, useState } from "react";
import { Archive, Download, Upload } from "lucide-react";
import { FREE_FAVORITES_LIMIT } from "../hooks/useFavorites";
import { resizeImageToBlob } from "../utils/imageResize";

const BACKUP_VERSION = 2;
// base64 にすると、元のバイト数の約1.33倍になる
const BASE64_RATIO = 4 / 3;
// これを超える写真は、取り込む前に縮小する(このアプリが書き出す写真は数百KBなので、通常は該当しない)。
const RESIZE_THRESHOLD_BYTES = 3 * 1024 * 1024;
// 縮小前の段階で、これを超える写真は読み込まない(メモリを使い切るのを防ぐ)。
const MAX_PHOTO_BYTES = 25 * 1024 * 1024;
const PHOTO_DATA_URL = /^data:image\/(jpeg|png|webp);base64,/;

const formatMB = (bytes) => `${Math.max(0.1, bytes / 1024 / 1024).toFixed(1)}MB`;

const blobToDataUrl = (blob) =>
  new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });

// コレクション(お気に入り+登録した店舗・商品)のバックアップ(JSONファイルへの書き出し・読み込み)。
// version 1 のファイル(お気に入りのみ)も読み込める。
// パッケージ写真は大きいので、書き出すときに「写真も含める」を選んだ場合だけ、photos として入れる。
export function CollectionBackup({
  favoriteIds,
  importFavorites,
  isPremium,
  userShops,
  userProducts,
  importUserCollection,
  photos,
}) {
  const fileInputRef = useRef(null);
  const [importMessage, setImportMessage] = useState(null);
  const [includePhotos, setIncludePhotos] = useState(false);
  const [photoBytes, setPhotoBytes] = useState(0);
  const [busy, setBusy] = useState(null); // null | "export" | "import"
  const totalCount = favoriteIds.length + userProducts.length;

  // 写真の合計サイズ(書き出しファイルの大きさの目安)。写真が増減したら計算し直す
  const { count: photoCount, getBytes: getPhotoBytes } = photos;
  useEffect(() => {
    let cancelled = false;
    if (photoCount === 0) {
      setPhotoBytes(0);
      return undefined;
    }
    getPhotoBytes().then((bytes) => {
      if (!cancelled) setPhotoBytes(bytes);
    });
    return () => {
      cancelled = true;
    };
  }, [photoCount, getPhotoBytes]);

  const withPhotos = includePhotos && photos.count > 0;

  const handleExport = async () => {
    setBusy("export");
    setImportMessage(null);
    try {
      const payload = {
        version: BACKUP_VERSION,
        exportedAt: new Date().toISOString(),
        favorites: favoriteIds,
        userShops,
        userProducts,
      };
      if (withPhotos) {
        const entries = await photos.exportAll();
        const dataUrls = {};
        // 1枚ずつ変換する(全部を同時に処理しない)
        for (const { id, blob } of entries) dataUrls[id] = await blobToDataUrl(blob);
        payload.photos = dataUrls;
      }
      const blob = new Blob([JSON.stringify(payload, null, withPhotos ? 0 : 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `coffee-finder-collection-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      setImportMessage({ type: "error", text: "書き出しに失敗しました" });
    } finally {
      setBusy(null);
    }
  };

  // バックアップの photos を、写真として取り込める形({ id, blob }[])にする。
  // 画像でないもの・極端に大きいもの・縮小できないもの・行き先の商品が無いもの(手動登録商品のみ)は除く。
  // 3MBを超える写真は、アプリで追加した写真と同じ大きさ(長辺1024px・JPEG)に縮小する。
  const parsePhotos = async (rawPhotos, validUserProductIds) => {
    if (!rawPhotos || typeof rawPhotos !== "object" || Array.isArray(rawPhotos)) return [];
    const entries = [];
    for (const [id, dataUrl] of Object.entries(rawPhotos)) {
      if (typeof dataUrl !== "string" || !PHOTO_DATA_URL.test(dataUrl)) continue;
      if (id.startsWith("user-product-") && !validUserProductIds.has(id)) continue;
      try {
        let blob = await (await fetch(dataUrl)).blob();
        if (blob.size === 0 || blob.size > MAX_PHOTO_BYTES) continue;
        if (blob.size > RESIZE_THRESHOLD_BYTES) blob = await resizeImageToBlob(new File([blob], "photo", { type: blob.type }));
        entries.push({ id, blob });
      } catch {
        // 壊れた1枚(画像として読めない等)は飛ばして、残りを取り込む
      }
    }
    return entries;
  };

  const handleFileChange = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = ""; // 同じファイルを連続選択してもchangeが発火するようにリセット
    if (!file) return;
    setBusy("import");
    try {
      const parsed = JSON.parse(await file.text());
      const hasFavorites = Array.isArray(parsed.favorites);
      const hasUserData = Array.isArray(parsed.userShops) || Array.isArray(parsed.userProducts);
      if (!hasFavorites && !hasUserData) {
        setImportMessage({ type: "error", text: "対応していないファイル形式です" });
        return;
      }
      const fav = hasFavorites ? importFavorites(parsed.favorites) : { total: 0, added: 0 };
      const user = hasUserData
        ? importUserCollection({ shops: parsed.userShops, products: parsed.userProducts })
        : { shopsAdded: 0, productsAdded: 0, productIds: userProducts.map((p) => p.id) };
      const photoEntries = await parsePhotos(parsed.photos, new Set(user.productIds));
      const photoResult = photoEntries.length > 0 ? await photos.importAll(photoEntries) : null;

      const parts = [];
      if (hasFavorites) parts.push(`保存した商品${fav.total}件中${fav.added}件`);
      if (hasUserData) parts.push(`店舗${user.shopsAdded}件・商品${user.productsAdded}件`);
      if (photoResult) parts.push(`写真${photoResult.added}枚`);
      const failed = photoResult?.failed ?? 0;
      setImportMessage({
        type: failed > 0 ? "error" : "success",
        text:
          `${parts.join("、")}を追加しました(登録済みのものは追加していません)` +
          (failed > 0 ? `。写真${failed}枚は保存できませんでした(端末の空き容量や設定をご確認ください)` : ""),
      });
    } catch {
      setImportMessage({ type: "error", text: "ファイルの読み込みに失敗しました" });
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="rounded-2xl bg-[var(--c-surface)] border border-[var(--c-border)] p-4 flex flex-col gap-3">
      <div className="flex items-center gap-1.5">
        <Archive size={14} className="text-[var(--accent)]" strokeWidth={1.75} />
        <h3 className="text-[14px] font-medium text-[var(--c-text)]">コレクションのバックアップ</h3>
      </div>
      <p className="text-[12px] text-[var(--c-text-3)] leading-relaxed">
        コレクション(保存した商品と、登録した店舗・商品)は、端末内にのみ保存されています。機種変更前や念のためのバックアップとして、ファイルへの書き出し・読み込みができます(評価とテイスティングログは含まれません。パッケージ写真は、書き出すときに選んだ場合だけ含まれます)。
        {!isPremium && `(無料プランは、商品を${FREE_FAVORITES_LIMIT}件までコレクションに保存できます)`}
      </p>

      {photos.count > 0 && (
        <label className="flex items-start gap-2 text-[12px] text-[var(--c-text-2)] leading-relaxed cursor-pointer">
          <input
            type="checkbox"
            checked={includePhotos}
            onChange={(e) => setIncludePhotos(e.target.checked)}
            className="mt-0.5 accent-[var(--accent)]"
          />
          <span>
            パッケージ写真も含める({photos.count}枚・ファイルが約{formatMB(photoBytes * BASE64_RATIO)}増えます)
            <span className="block text-[11px] text-[var(--c-text-3)]">
              ファイルが大きいと、メールで送れなかったり、読み込みに時間がかかったりすることがあります。
            </span>
          </span>
        </label>
      )}

      <div className="flex gap-2">
        <button
          onClick={handleExport}
          disabled={(totalCount === 0 && userShops.length === 0) || busy !== null}
          className="flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-xl bg-[var(--accent)] text-[var(--on-accent)] text-[13px] font-medium disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <Download size={14} strokeWidth={2} />
          {busy === "export" ? "書き出し中…" : `書き出す(${totalCount}件)`}
        </button>
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={busy !== null}
          className="flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-xl border border-[var(--c-border)] text-[var(--c-text-2)] text-[13px] disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <Upload size={14} strokeWidth={2} />
          {busy === "import" ? "読み込み中…" : "読み込む"}
        </button>
        <input ref={fileInputRef} type="file" accept="application/json" className="hidden" onChange={handleFileChange} />
      </div>
      {importMessage && (
        <p className={`text-[12px] ${importMessage.type === "error" ? "text-[var(--c-danger)]" : "text-[var(--accent)]"}`}>
          {importMessage.text}
        </p>
      )}
    </section>
  );
}
