import { useRef, useState } from "react";
import { Archive, Download, Upload } from "lucide-react";
import { FREE_FAVORITES_LIMIT } from "../hooks/useFavorites";

const BACKUP_VERSION = 2;

// コレクション(お気に入り+登録した店舗・商品)のバックアップ(JSONファイルへの書き出し・読み込み)。
// version 1 のファイル(お気に入りのみ)も読み込める。
export function CollectionBackup({ favoriteIds, importFavorites, isPremium, userShops, userProducts, importUserCollection }) {
  const fileInputRef = useRef(null);
  const [importMessage, setImportMessage] = useState(null);
  const totalCount = favoriteIds.length + userProducts.length;

  const handleExport = () => {
    const payload = {
      version: BACKUP_VERSION,
      exportedAt: new Date().toISOString(),
      favorites: favoriteIds,
      userShops,
      userProducts,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `coffee-finder-collection-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  const handleFileChange = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = ""; // 同じファイルを連続選択してもchangeが発火するようにリセット
    if (!file) return;
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
        : { shopsAdded: 0, productsAdded: 0 };
      const parts = [];
      if (hasFavorites) parts.push(`保存した商品${fav.total}件中${fav.added}件`);
      if (hasUserData) parts.push(`店舗${user.shopsAdded}件・商品${user.productsAdded}件`);
      setImportMessage({
        type: "success",
        text: `${parts.join("、")}を追加しました(登録済みのものは追加していません)`,
      });
    } catch {
      setImportMessage({ type: "error", text: "ファイルの読み込みに失敗しました" });
    }
  };

  return (
    <section className="rounded-2xl bg-[var(--c-surface)] border border-[var(--c-border)] p-4 flex flex-col gap-3">
      <div className="flex items-center gap-1.5">
        <Archive size={14} className="text-[var(--accent)]" strokeWidth={1.75} />
        <h3 className="text-[14px] font-medium text-[var(--c-text)]">コレクションのバックアップ</h3>
      </div>
      <p className="text-[12px] text-[var(--c-text-3)] leading-relaxed">
        コレクション(保存した商品と、登録した店舗・商品)は、端末内にのみ保存されています。機種変更前や念のためのバックアップとして、ファイルへの書き出し・読み込みができます(評価とテイスティングログは含まれません)。
        {!isPremium && `(無料プランは、商品を${FREE_FAVORITES_LIMIT}件までコレクションに保存できます)`}
      </p>
      <div className="flex gap-2">
        <button
          onClick={handleExport}
          disabled={totalCount === 0 && userShops.length === 0}
          className="flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-xl bg-[var(--accent)] text-[var(--on-accent)] text-[13px] font-medium disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <Download size={14} strokeWidth={2} />
          書き出す({totalCount}件)
        </button>
        <button
          onClick={() => fileInputRef.current?.click()}
          className="flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-xl border border-[var(--c-border)] text-[var(--c-text-2)] text-[13px]"
        >
          <Upload size={14} strokeWidth={2} />
          読み込む
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
