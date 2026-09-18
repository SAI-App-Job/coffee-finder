import { useMemo, useRef, useState } from "react";
import { Palette, Check, Sparkles, Heart, Download, Upload, Info, History, Shuffle, MapPinned } from "lucide-react";
import { SectionHeading } from "./common";
import { TasteProfile } from "./TasteProfile";
import { FREE_FAVORITES_LIMIT } from "../hooks/useFavorites";
import { FREE_COMPARE_LIMIT } from "../hooks/useComparison";
import { FREE_HISTORY_RETENTION_DAYS } from "../hooks/useViewHistory";
import { formatRelativeTime } from "../utils/format";
import { ALL_PREFECTURES } from "../data/prefectures";
import { filterByFavoriteArea } from "../utils/productSort";

export function MyPageView({
  themeId,
  setThemeId,
  themes,
  isPremium,
  setPremium,
  favoriteIds,
  importFavorites,
  historyItems,
  products,
  getRating,
  onOpenDetail,
  displayRadiusId,
  setDisplayRadiusId,
  displayRadiusOptions,
  favoriteArea,
  setFavoriteAreaPrefecture,
  setFavoriteAreaCity,
}) {
  const fileInputRef = useRef(null);
  const [importMessage, setImportMessage] = useState(null);

  // 入力(都道府県・市区町村)のたびに該当件数をその場で数える。ジオコーディング
  // 不要な住所文字列の部分一致のみなので、全商品数(数千件)規模でも軽い。
  const favoriteAreaMatchCount = useMemo(
    () => filterByFavoriteArea(products, favoriteArea).length,
    [products, favoriteArea]
  );

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
    <main className="px-5 py-5 flex flex-col gap-6 max-w-xl mx-auto">
      <SectionHeading en="My Page" ja="マイページ" />

      <section className="rounded-2xl bg-[#2F241A] border border-[#4A3A2A] p-4 flex flex-col gap-3">
        <div className="flex items-center gap-1.5">
          <Palette size={14} className="text-[var(--accent)]" strokeWidth={1.75} />
          <h3 className="text-[14px] font-medium text-[#F2E9DD]">アクセントカラー</h3>
        </div>
        <div className="flex flex-wrap gap-3">
          {themes.map((t) => (
            <button
              key={t.id}
              onClick={() => setThemeId(t.id)}
              className="flex flex-col items-center gap-1.5"
              aria-label={t.label}
              aria-pressed={themeId === t.id}
            >
              <span
                className="w-9 h-9 rounded-full flex items-center justify-center border-2"
                style={{ backgroundColor: t.accent, borderColor: themeId === t.id ? "#F2E9DD" : "transparent" }}
              >
                {themeId === t.id && <Check size={16} strokeWidth={2.5} color="#231810" />}
              </span>
              <span className="text-[10px] text-[#8B7361]">{t.label}</span>
            </button>
          ))}
        </div>
      </section>

      <section className="rounded-2xl bg-[#2F241A] border border-[#4A3A2A] p-4 flex flex-col gap-3">
        <div className="flex items-center gap-1.5">
          <MapPinned size={14} className="text-[var(--accent)]" strokeWidth={1.75} />
          <h3 className="text-[14px] font-medium text-[#F2E9DD]">登録エリア</h3>
        </div>
        <p className="text-[12px] text-[#8B7361] leading-relaxed">
          商品タブの「登録エリア」並べ替えで表示する地域です。都道府県は必須、市区町村は任意(未入力なら都道府県全体が対象)。郵便番号ではなく手入力で登録します。
        </p>
        <div className="flex flex-col gap-2.5">
          <label className="flex flex-col gap-1">
            <span className="text-[11px] text-[#8B7361]">都道府県</span>
            <select
              value={favoriteArea.prefecture}
              onChange={(e) => {
                const next = e.target.value;
                setFavoriteAreaPrefecture(next);
                if (!next) setFavoriteAreaCity(""); // 都道府県を未登録に戻す際は市区町村も一緒にクリアする
              }}
              className="w-full py-2.5 px-3 rounded-xl bg-[#3B2211] border border-[#4A3A2A] text-[13px] text-[#F2E9DD] focus:outline-none focus:border-[var(--accent-label)]"
            >
              <option value="">未登録</option>
              {ALL_PREFECTURES.map((pref) => (
                <option key={pref} value={pref}>
                  {pref}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[11px] text-[#8B7361]">市区町村(任意)</span>
            <input
              type="text"
              value={favoriteArea.city}
              onChange={(e) => setFavoriteAreaCity(e.target.value)}
              placeholder="例: 渋谷区、横浜市"
              disabled={!favoriteArea.prefecture}
              className="w-full py-2.5 px-3 rounded-xl bg-[#3B2211] border border-[#4A3A2A] text-[13px] text-[#F2E9DD] placeholder:text-[#8B7361] focus:outline-none focus:border-[var(--accent-label)] disabled:opacity-40"
            />
          </label>
        </div>
        <p className="text-[12px] text-[var(--accent)]">
          {favoriteArea.prefecture
            ? `現在の該当件数: ${favoriteAreaMatchCount}件`
            : "都道府県を選択すると該当件数が表示されます"}
        </p>
        {favoriteArea.prefecture && favoriteAreaMatchCount === 0 && (
          <p className="flex items-start gap-1.5 text-[11px] text-[#8B7361] leading-relaxed">
            <Info size={12} className="shrink-0 mt-0.5" strokeWidth={1.75} />
            <span>この条件では店舗がまだ見つかりません。市区町村を空にする、または隣接する地域を試してみてください。</span>
          </p>
        )}
      </section>

      <section className="rounded-2xl bg-[#2F241A] border border-[#4A3A2A] p-4 flex flex-col gap-3">
        <div className="flex items-center gap-1.5">
          <Shuffle size={14} className="text-[var(--accent)]" strokeWidth={1.75} />
          <h3 className="text-[14px] font-medium text-[#F2E9DD]">表示範囲(ランダム表示用)</h3>
        </div>
        <p className="text-[12px] text-[#8B7361] leading-relaxed">
          商品タブの「ランダム」並べ替えで表示する商品の範囲です。「自動(おすすめ)」は、現在地から近い範囲で件数が少ない場合に自動で範囲を広げます。近い順・新規掲載の並べ替えには影響しません。
        </p>
        <div className="flex flex-wrap gap-2">
          {displayRadiusOptions.map((o) => (
            <button
              key={o.id}
              onClick={() => setDisplayRadiusId(o.id)}
              aria-pressed={displayRadiusId === o.id}
              className={`text-[12px] px-3.5 py-2 rounded-full border transition-colors ${
                displayRadiusId === o.id
                  ? "bg-[var(--accent)] text-[#231810] border-[var(--accent)] font-medium"
                  : "border-[#4A3A2A] text-[#B8A891]"
              }`}
            >
              {o.label}
            </button>
          ))}
        </div>
      </section>

      <section className="rounded-2xl bg-[#2F241A] border border-[#4A3A2A] p-4 flex flex-col gap-3">
        <div className="flex items-center gap-1.5">
          <Sparkles size={14} className="text-[var(--accent)]" strokeWidth={1.75} />
          <h3 className="text-[14px] font-medium text-[#F2E9DD]">プレミアム(広告非表示)</h3>
        </div>
        <p className="text-[12px] text-[#8B7361] leading-relaxed">
          月額100円で、広告非表示に加えてお気に入り・閲覧履歴・比較の件数上限がすべて無制限になります(決済機能は準備中です)。
        </p>
        <ul className="text-[11px] text-[#8B7361] leading-relaxed list-disc pl-4 flex flex-col gap-0.5">
          <li>お気に入り: 無料{FREE_FAVORITES_LIMIT}件 → 有料は無制限</li>
          <li>閲覧履歴の保存期間: 無料{FREE_HISTORY_RETENTION_DAYS}日間 → 有料は無制限</li>
          <li>比較できる商品数: 無料{FREE_COMPARE_LIMIT}件 → 有料は無制限</li>
        </ul>
        <div className="flex items-center justify-between gap-3 rounded-xl bg-[#3B2211] border border-[#4A3A2A] px-3.5 py-3">
          <div>
            <p className="text-[13px] text-[#F2E9DD]">{isPremium ? "プレミアム有効" : "無料プラン"}</p>
            <p className="text-[11px] text-[#8B7361] mt-0.5">
              {isPremium ? "広告は表示されません" : "画面下部に広告が表示されます"}
            </p>
          </div>
          <button
            onClick={() => setPremium(!isPremium)}
            className={`shrink-0 text-[12px] px-3.5 py-2 rounded-full font-medium transition-colors ${
              isPremium ? "border border-[#4A3A2A] text-[#B8A891]" : "bg-[var(--accent)] text-[#231810]"
            }`}
          >
            {isPremium ? "解除する(開発用)" : "プレミアムを試す(開発用)"}
          </button>
        </div>
        <div className="flex items-start gap-1.5 text-[11px] text-[#8B7361] leading-relaxed">
          <Info size={12} className="shrink-0 mt-0.5" strokeWidth={1.75} />
          <span>現在は動作確認用のスイッチです。正式リリース時はストア課金に置き換わります。</span>
        </div>
      </section>

      <section className="rounded-2xl bg-[#2F241A] border border-[#4A3A2A] p-4 flex flex-col gap-3">
        <div className="flex items-center gap-1.5">
          <Heart size={14} className="text-[var(--accent)]" strokeWidth={1.75} />
          <h3 className="text-[14px] font-medium text-[#F2E9DD]">お気に入りのバックアップ</h3>
        </div>
        <p className="text-[12px] text-[#8B7361] leading-relaxed">
          お気に入りは端末内にのみ保存されています。機種変更前や念のためのバックアップとして、ファイルへの書き出し・読み込みができます。
          {!isPremium && `(無料プランは${FREE_FAVORITES_LIMIT}件まで保存できます)`}
        </p>
        <div className="flex gap-2">
          <button
            onClick={handleExport}
            disabled={favoriteIds.length === 0}
            className="flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-xl bg-[var(--accent)] text-[#231810] text-[13px] font-medium disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Download size={14} strokeWidth={2} />
            書き出す({favoriteIds.length}件)
          </button>
          <button
            onClick={() => fileInputRef.current?.click()}
            className="flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-xl border border-[#4A3A2A] text-[#B8A891] text-[13px]"
          >
            <Upload size={14} strokeWidth={2} />
            読み込む
          </button>
          <input ref={fileInputRef} type="file" accept="application/json" className="hidden" onChange={handleFileChange} />
        </div>
        {importMessage && (
          <p className={`text-[12px] ${importMessage.type === "error" ? "text-[#C9506B]" : "text-[var(--accent)]"}`}>
            {importMessage.text}
          </p>
        )}
      </section>

      <section className="rounded-2xl bg-[#2F241A] border border-[#4A3A2A] p-4 flex flex-col gap-3">
        <div className="flex items-center gap-1.5">
          <History size={14} className="text-[var(--accent)]" strokeWidth={1.75} />
          <h3 className="text-[14px] font-medium text-[#F2E9DD]">閲覧履歴</h3>
        </div>
        <p className="text-[12px] text-[#8B7361] leading-relaxed">
          {isPremium
            ? "閲覧履歴は無制限に保存されます。"
            : `無料プランでは直近${FREE_HISTORY_RETENTION_DAYS}日分のみ保存されます(有料プランでは無制限)。`}
        </p>
        {historyItems.length === 0 ? (
          <p className="text-[12px] text-[#8B7361]">商品をタップすると、ここに閲覧履歴が表示されます。</p>
        ) : (
          <div className="flex flex-col gap-2">
            {historyItems.slice(0, 8).map(({ product, viewedAt }) => (
              <div
                key={product.id}
                className="flex items-center justify-between gap-3 rounded-xl bg-[#3B2211] border border-[#4A3A2A] px-3.5 py-2.5"
              >
                <div className="min-w-0">
                  <p className="text-[12px] text-[#F2E9DD] truncate">{product.rawName}</p>
                  <p className="text-[11px] text-[#8B7361] mt-0.5">{product.shopName}</p>
                </div>
                <p className="text-[10px] text-[#8B7361] shrink-0">{formatRelativeTime(viewedAt)}</p>
              </div>
            ))}
          </div>
        )}
      </section>

      <TasteProfile products={products} getRating={getRating} onOpenDetail={onOpenDetail} />
    </main>
  );
}
