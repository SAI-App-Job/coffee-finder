import { useEffect, useRef, useState } from "react";
import { Archive, Download, Upload } from "lucide-react";
import { FREE_FAVORITES_LIMIT } from "../hooks/useFavorites";
import { resizeImageToBlob } from "../utils/imageResize";
import { useT } from "../i18n";

// 版 1: お気に入りだけ / 版 2: + 登録した店舗・商品・写真 / 版 3: + ★評価・テイスティングログ・店舗のテイスティングノート・マイツール・商品名の控え
// 古い版のファイルも、読み込める(無い項目は、飛ばす)。docs/user-data-storage.md
const BACKUP_VERSION = 3;
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

// 利用者のデータ(コレクション・★評価・テイスティングログ・テイスティングノート・マイツール)のバックアップ(JSONファイルへの書き出し・読み込み)。
// 読み込みは「追加のみ」で、いまのデータは上書きしない(評価だけは、日時が新しい方を残す)。
// 含めないもの: プレミアムの状態(ファイルの編集で回避できてしまうため)・実績(記録から再計算される)・閲覧履歴・設定。
// パッケージ写真は大きいので、書き出すときに「写真も含める」を選んだ場合だけ、photos として入れる。
export function DataBackup({
  favoriteIds,
  favoriteDates,
  importFavorites,
  isPremium,
  userShops,
  userProducts,
  importUserCollection,
  photos,
  ratings,
  importRatings,
  logsByProduct,
  importLogs,
  notesByShop,
  importNotes,
  tools,
  importTools,
  productSnapshots,
  importSnapshots,
}) {
  const t = useT();
  const fileInputRef = useRef(null);
  const [importMessage, setImportMessage] = useState(null);
  const [includePhotos, setIncludePhotos] = useState(false);
  const [photoBytes, setPhotoBytes] = useState(0);
  const [busy, setBusy] = useState(null); // null | "export" | "import"
  const countEntries = (byKey) => Object.values(byKey).reduce((n, list) => n + list.length, 0);
  const totalCount =
    favoriteIds.length + userProducts.length + Object.keys(ratings).length + countEntries(logsByProduct) + countEntries(notesByShop) + tools.length;

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
        favoriteDates: Object.fromEntries(Object.entries(favoriteDates).filter(([id]) => favoriteIds.includes(id))),
        userShops,
        userProducts,
        ratings,
        tastingLogs: logsByProduct,
        shopTastingNotes: notesByShop,
        myTools: tools,
        productSnapshots,
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
      a.download = `coffee-finder-backup-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      setImportMessage({ type: "error", text: t("書き出しに失敗しました") });
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
      const isObj = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
      const hasRecords = isObj(parsed.ratings) || isObj(parsed.tastingLogs) || isObj(parsed.shopTastingNotes) || Array.isArray(parsed.myTools);
      if (parsed === null || typeof parsed !== "object" || (!hasFavorites && !hasUserData && !hasRecords)) {
        setImportMessage({ type: "error", text: t("対応していないファイル形式です") });
        return;
      }
      const fav = hasFavorites ? importFavorites(parsed.favorites, parsed.favoriteDates) : { total: 0, added: 0 };
      const user = hasUserData
        ? importUserCollection({ shops: parsed.userShops, products: parsed.userProducts })
        : { shopsAdded: 0, productsAdded: 0, productIds: userProducts.map((p) => p.id) };
      // ★評価・ログ・ノート・マイツール・商品名の控え(版 3 から)
      const rated = isObj(parsed.ratings) ? importRatings(parsed.ratings) : null;
      const logged = isObj(parsed.tastingLogs) ? importLogs(parsed.tastingLogs) : null;
      const noted = isObj(parsed.shopTastingNotes) ? importNotes(parsed.shopTastingNotes) : null;
      const toolResult = Array.isArray(parsed.myTools) ? importTools(parsed.myTools) : null;
      if (isObj(parsed.productSnapshots)) importSnapshots(parsed.productSnapshots);
      const photoEntries = await parsePhotos(parsed.photos, new Set(user.productIds));
      const photoResult = photoEntries.length > 0 ? await photos.importAll(photoEntries) : null;

      const parts = [];
      if (hasFavorites) parts.push(t("保存した商品{total}件中{added}件", { total: fav.total, added: fav.added }));
      if (hasUserData) parts.push(t("店舗{shops}件・商品{products}件", { shops: user.shopsAdded, products: user.productsAdded }));
      if (rated) parts.push(t("★評価{n}件", { n: rated.added + rated.updated }));
      if (logged) parts.push(t("テイスティングログ{n}件", { n: logged.added }));
      if (noted) parts.push(t("テイスティングノート{n}件", { n: noted.added }));
      if (toolResult) parts.push(t("マイツール{n}件", { n: toolResult.added }));
      if (photoResult) parts.push(t("写真{n}枚", { n: photoResult.added }));
      const failed = photoResult?.failed ?? 0;
      setImportMessage({
        type: failed > 0 ? "error" : "success",
        text:
          t("{parts}を追加しました(登録済みのものは追加していません)", { parts: parts.join(t("、")) }) +
          (failed > 0 ? t("。写真{n}枚は保存できませんでした(端末の空き容量や設定をご確認ください)", { n: failed }) : ""),
      });
    } catch {
      setImportMessage({ type: "error", text: t("ファイルの読み込みに失敗しました") });
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="rounded-2xl bg-[var(--c-surface)] border border-[var(--c-border)] p-4 flex flex-col gap-3">
      <div className="flex items-center gap-1.5">
        <Archive size={14} className="text-[var(--accent)]" strokeWidth={1.75} />
        <h3 className="text-[14px] font-medium text-[var(--c-text)]">{t("データのバックアップ")}</h3>
      </div>
      <p className="text-[12px] text-[var(--c-text-3)] leading-relaxed">
        {t("コレクション(保存した商品と、登録した店舗・商品)・★評価・テイスティングログ・テイスティングノート・マイツールは、端末内にのみ保存されています。機種変更前や念のためのバックアップとして、1つのファイルへの書き出し・読み込みができます(パッケージ写真は、書き出すときに選んだ場合だけ含まれます)。読み込みは追加のみで、いまのデータは上書きしません。")}
        {!isPremium && t("(無料プランは、商品を{n}件までコレクションに保存できます)", { n: FREE_FAVORITES_LIMIT })}
      </p>

      <p className="text-[11px] text-[var(--c-text-3)] leading-relaxed">
        {t("ファイルには、あなたのメモや感想が入っています。他の人に渡すときは、ご注意ください。")}
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
            {t("パッケージ写真も含める({n}枚・ファイルが約{size}増えます)", { n: photos.count, size: formatMB(photoBytes * BASE64_RATIO) })}
            <span className="block text-[11px] text-[var(--c-text-3)]">
              {t("ファイルが大きいと、メールで送れなかったり、読み込みに時間がかかったりすることがあります。")}
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
          {busy === "export" ? t("書き出し中…") : t("書き出す({n}件)", { n: totalCount })}
        </button>
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={busy !== null}
          className="flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-xl border border-[var(--c-border)] text-[var(--c-text-2)] text-[13px] disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <Upload size={14} strokeWidth={2} />
          {busy === "import" ? t("読み込み中…") : t("読み込む")}
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
