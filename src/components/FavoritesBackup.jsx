import { useRef, useState } from "react";
import { Heart, Download, Upload } from "lucide-react";
import { FREE_FAVORITES_LIMIT } from "../hooks/useFavorites";

// お気に入りのバックアップ(JSONファイルへの書き出し・読み込み)。お気に入り画面の下部に置く。
export function FavoritesBackup({ favoriteIds, importFavorites, isPremium }) {
  const fileInputRef = useRef(null);
  const [importMessage, setImportMessage] = useState(null);

  const handleExport = () => {
    const payload = {
      version: 1,
      exportedAt: new Date().toISOString(),
      favorites: favoriteIds,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `coffee-finder-favorites-${new Date().toISOString().slice(0, 10)}.json`;
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
      if (!Array.isArray(parsed.favorites)) {
        setImportMessage({ type: "error", text: "対応していないファイル形式です" });
        return;
      }
      const { total, added } = importFavorites(parsed.favorites);
      setImportMessage({
        type: "success",
        text: `${total}件中${added}件を追加しました(${total - added}件は登録済みでした)`,
      });
    } catch {
      setImportMessage({ type: "error", text: "ファイルの読み込みに失敗しました" });
    }
  };

  return (
    <section className="rounded-2xl bg-[var(--c-surface)] border border-[var(--c-border)] p-4 flex flex-col gap-3">
      <div className="flex items-center gap-1.5">
        <Heart size={14} className="text-[var(--accent)]" strokeWidth={1.75} />
        <h3 className="text-[14px] font-medium text-[var(--c-text)]">お気に入りのバックアップ</h3>
      </div>
      <p className="text-[12px] text-[var(--c-text-3)] leading-relaxed">
        お気に入りは端末内にのみ保存されています。機種変更前や念のためのバックアップとして、ファイルへの書き出し・読み込みができます。
        {!isPremium && `(無料プランは${FREE_FAVORITES_LIMIT}件まで保存できます)`}
      </p>
      <div className="flex gap-2">
        <button
          onClick={handleExport}
          disabled={favoriteIds.length === 0}
          className="flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-xl bg-[var(--accent)] text-[var(--on-accent)] text-[13px] font-medium disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <Download size={14} strokeWidth={2} />
          書き出す({favoriteIds.length}件)
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
