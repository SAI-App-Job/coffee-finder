import { useMemo } from "react";
import { Palette, Check, Sparkles, Info, Shuffle, MapPinned, ChevronRight } from "lucide-react";
import { SectionHeading } from "./common";
import { FREE_FAVORITES_LIMIT } from "../hooks/useFavorites";
import { FREE_COMPARE_LIMIT } from "../hooks/useComparison";
import { FREE_HISTORY_RETENTION_DAYS } from "../hooks/useViewHistory";
import { ALL_PREFECTURES } from "../data/prefectures";
import { filterByFavoriteArea } from "../utils/productSort";

// 「設定」画面: カラーテーマ・登録エリア・表示範囲・プレミアム・このアプリについて(末尾)
export function SettingsView({
  themeId,
  setThemeId,
  themes,
  isPremium,
  setPremium,
  products,
  displayRadiusId,
  setDisplayRadiusId,
  displayRadiusOptions,
  favoriteArea,
  setFavoriteAreaPrefecture,
  setFavoriteAreaCity,
  onOpenAbout,
}) {
  // 入力(都道府県・市区町村)のたびに該当件数をその場で数える。ジオコーディング
  // 不要な住所文字列の部分一致のみなので、全商品数(数千件)規模でも軽い。
  const favoriteAreaMatchCount = useMemo(
    () => filterByFavoriteArea(products, favoriteArea).length,
    [products, favoriteArea]
  );

  return (
    <main className="px-5 py-5 flex flex-col gap-6 max-w-xl mx-auto">
      <SectionHeading en="Settings" ja="設定" />

      <section className="rounded-2xl bg-[var(--c-surface)] border border-[var(--c-border)] p-4 flex flex-col gap-3">
        <div className="flex items-center gap-1.5">
          <Palette size={14} className="text-[var(--accent)]" strokeWidth={1.75} />
          <h3 className="text-[14px] font-medium text-[var(--c-text)]">カラーテーマ</h3>
        </div>
        <div className="grid grid-cols-2 gap-3">
          {themes.map((t) => {
            const selected = themeId === t.id;
            return (
              <button
                key={t.id}
                onClick={() => setThemeId(t.id)}
                aria-pressed={selected}
                className={`flex flex-col gap-2 p-2.5 rounded-xl border-2 text-left transition-colors ${
                  selected ? "border-[var(--accent)]" : "border-[var(--c-border)] hover:border-[var(--accent-label)]"
                }`}
              >
                {/* 選択前でも見た目が分かるよう、テーマごとの固定色で見本を描く */}
                <span
                  className="h-14 rounded-lg border flex flex-col justify-between p-2"
                  style={{ backgroundColor: t.preview.bg, borderColor: t.preview.surface }}
                >
                  <span className="h-2 w-2/3 rounded-full" style={{ backgroundColor: t.preview.text }} />
                  <span className="flex items-center gap-1.5">
                    <span className="h-3 w-8 rounded-md" style={{ backgroundColor: t.preview.surface }} />
                    <span className="h-3 w-3 rounded-full" style={{ backgroundColor: t.preview.accent }} />
                  </span>
                </span>
                <span className="flex items-center justify-between gap-1">
                  <span className="text-[13px] font-medium text-[var(--c-text)]">{t.label}</span>
                  {selected && <Check size={14} strokeWidth={2.5} className="text-[var(--accent)]" />}
                </span>
                <span className="text-[11px] leading-snug text-[var(--c-text-3)]">{t.description}</span>
              </button>
            );
          })}
        </div>
      </section>

      <section className="rounded-2xl bg-[var(--c-surface)] border border-[var(--c-border)] p-4 flex flex-col gap-3">
        <div className="flex items-center gap-1.5">
          <MapPinned size={14} className="text-[var(--accent)]" strokeWidth={1.75} />
          <h3 className="text-[14px] font-medium text-[var(--c-text)]">登録エリア</h3>
        </div>
        <p className="text-[12px] text-[var(--c-text-3)] leading-relaxed">
          商品タブの「登録エリア」並べ替えで表示する地域です。都道府県は必須、市区町村は任意(未入力なら都道府県全体が対象)。郵便番号ではなく手入力で登録します。
        </p>
        <div className="flex flex-col gap-2.5">
          <label className="flex flex-col gap-1">
            <span className="text-[11px] text-[var(--c-text-3)]">都道府県</span>
            <select
              value={favoriteArea.prefecture}
              onChange={(e) => {
                const next = e.target.value;
                setFavoriteAreaPrefecture(next);
                if (!next) setFavoriteAreaCity(""); // 都道府県を未登録に戻す際は市区町村も一緒にクリアする
              }}
              className="w-full py-2.5 px-3 rounded-xl bg-[var(--c-surface-2)] border border-[var(--c-border)] text-[13px] text-[var(--c-text)] focus:outline-none focus:border-[var(--accent-label)]"
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
            <span className="text-[11px] text-[var(--c-text-3)]">市区町村(任意)</span>
            <input
              type="text"
              value={favoriteArea.city}
              onChange={(e) => setFavoriteAreaCity(e.target.value)}
              placeholder="例: 渋谷区、横浜市"
              disabled={!favoriteArea.prefecture}
              className="w-full py-2.5 px-3 rounded-xl bg-[var(--c-surface-2)] border border-[var(--c-border)] text-[13px] text-[var(--c-text)] placeholder:text-[var(--c-text-3)] focus:outline-none focus:border-[var(--accent-label)] disabled:opacity-40"
            />
          </label>
        </div>
        <p className="text-[12px] text-[var(--accent)]">
          {favoriteArea.prefecture
            ? `現在の該当件数: ${favoriteAreaMatchCount}件`
            : "都道府県を選択すると該当件数が表示されます"}
        </p>
        {favoriteArea.prefecture && favoriteAreaMatchCount === 0 && (
          <p className="flex items-start gap-1.5 text-[11px] text-[var(--c-text-3)] leading-relaxed">
            <Info size={12} className="shrink-0 mt-0.5" strokeWidth={1.75} />
            <span>この条件では店舗がまだ見つかりません。市区町村を空にする、または隣接する地域を試してみてください。</span>
          </p>
        )}
      </section>

      <section className="rounded-2xl bg-[var(--c-surface)] border border-[var(--c-border)] p-4 flex flex-col gap-3">
        <div className="flex items-center gap-1.5">
          <Shuffle size={14} className="text-[var(--accent)]" strokeWidth={1.75} />
          <h3 className="text-[14px] font-medium text-[var(--c-text)]">表示範囲(ランダム表示用)</h3>
        </div>
        <p className="text-[12px] text-[var(--c-text-3)] leading-relaxed">
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
                  ? "bg-[var(--accent)] text-[var(--on-accent)] border-[var(--accent)] font-medium"
                  : "border-[var(--c-border)] text-[var(--c-text-2)]"
              }`}
            >
              {o.label}
            </button>
          ))}
        </div>
      </section>

      <section className="rounded-2xl bg-[var(--c-surface)] border border-[var(--c-border)] p-4 flex flex-col gap-3">
        <div className="flex items-center gap-1.5">
          <Sparkles size={14} className="text-[var(--accent)]" strokeWidth={1.75} />
          <h3 className="text-[14px] font-medium text-[var(--c-text)]">プレミアム(広告非表示)</h3>
        </div>
        <p className="text-[12px] text-[var(--c-text-3)] leading-relaxed">
          月額100円で、広告非表示に加えてお気に入り・閲覧履歴・比較の件数上限がすべて無制限になります(決済機能は準備中です)。
        </p>
        <ul className="text-[11px] text-[var(--c-text-3)] leading-relaxed list-disc pl-4 flex flex-col gap-0.5">
          <li>お気に入り: 無料{FREE_FAVORITES_LIMIT}件 → 有料は無制限</li>
          <li>閲覧履歴の保存期間: 無料{FREE_HISTORY_RETENTION_DAYS}日間 → 有料は無制限</li>
          <li>比較できる商品数: 無料{FREE_COMPARE_LIMIT}件 → 有料は無制限</li>
        </ul>
        <div className="flex items-center justify-between gap-3 rounded-xl bg-[var(--c-surface-2)] border border-[var(--c-border)] px-3.5 py-3">
          <div>
            <p className="text-[13px] text-[var(--c-text)]">{isPremium ? "プレミアム有効" : "無料プラン"}</p>
            <p className="text-[11px] text-[var(--c-text-3)] mt-0.5">
              {isPremium ? "広告は表示されません" : "画面上部に広告が表示されます"}
            </p>
          </div>
          <button
            onClick={() => setPremium(!isPremium)}
            className={`shrink-0 text-[12px] px-3.5 py-2 rounded-full font-medium transition-colors ${
              isPremium ? "border border-[var(--c-border)] text-[var(--c-text-2)]" : "bg-[var(--accent)] text-[var(--on-accent)]"
            }`}
          >
            {isPremium ? "解除する(開発用)" : "プレミアムを試す(開発用)"}
          </button>
        </div>
        <div className="flex items-start gap-1.5 text-[11px] text-[var(--c-text-3)] leading-relaxed">
          <Info size={12} className="shrink-0 mt-0.5" strokeWidth={1.75} />
          <span>現在は動作確認用のスイッチです。正式リリース時はストア課金に置き換わります。</span>
        </div>
      </section>

      <button
        onClick={onOpenAbout}
        className="w-full flex items-center justify-between gap-3 rounded-2xl bg-[var(--c-surface)] border border-[var(--c-border)] p-4 text-left hover:border-[var(--accent-label)] transition-colors"
      >
        <span className="flex items-center gap-1.5">
          <Info size={14} className="text-[var(--accent)]" strokeWidth={1.75} />
          <span className="text-[14px] font-medium text-[var(--c-text)]">このアプリについて</span>
        </span>
        <ChevronRight size={16} className="text-[var(--c-text-3)]" strokeWidth={1.75} />
      </button>
    </main>
  );
}
