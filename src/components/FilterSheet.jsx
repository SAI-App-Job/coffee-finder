import { useState, useRef, useEffect } from "react";
import { Search, Check, X, ChevronDown } from "lucide-react";
import { ORIGIN_GUIDE, ORIGIN_ZONE_ORDER, ORIGIN_ZONE_LABELS } from "../data/originGuide";
import { FLAVOR_CATEGORIES } from "../data/flavorVocabulary";
import { FILTER_SEARCH_THRESHOLD } from "../data/navigation";
import { StarRating } from "./common";
import { useT } from "../i18n";

// 産地(国)フィルタの選択肢は、店舗の実データ(originCountryの表記ゆれが多い)
// ではなく、17ヶ国を整理済みのORIGIN_GUIDEを唯一の情報源とする。アフリカ/
// 中南米/アジアの3グループに分け、産地タブの地図と同じ見出し・順序で表示する。
const COUNTRIES_BY_ZONE = ORIGIN_ZONE_ORDER.map((zone) => ({
  zone,
  label: ORIGIN_ZONE_LABELS[zone],
  countries: ORIGIN_GUIDE.filter((o) => o.zone === zone).map((o) => o.country),
}));

const SELECT_CLASS =
  "w-full py-2.5 px-3 rounded-xl bg-[var(--c-surface-2)] border border-[var(--c-border)] text-[13px] text-[var(--c-text)] focus:outline-none focus:border-[var(--accent-label)]";

function FilterChip({ opt, active, onToggle, dotColor }) {
  const t = useT();
  return (
    <button
      onClick={() => onToggle(opt)}
      className={`flex items-center gap-1.5 text-[13px] px-3 py-1.5 rounded-full border-2 transition-all ${
        active
          ? "bg-[var(--c-chip-active)] text-[var(--c-chip-active-text)] border-[var(--c-chip-active)] font-medium shadow-[0_0_0_3px_var(--accent-glow)]"
          : "border-[var(--c-border)] text-[var(--c-text-2)] hover:border-[var(--accent-label)]"
      }`}
    >
      {dotColor && (
        <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: dotColor }} />
      )}
      {active && <Check size={12} strokeWidth={3} />}
      {t(opt)}
    </button>
  );
}

export function FilterSection({ title, options, selected, onToggle, getColor }) {
  const t = useT();
  const [query, setQuery] = useState("");
  const isSearchable = options.length > FILTER_SEARCH_THRESHOLD;

  const q = query.trim().toLowerCase();
  const visibleOptions = q ? options.filter((opt) => opt.toLowerCase().includes(q)) : options;

  // 検索で絞り込んでいても、既に選んでいる項目は見失わないよう常に上部に表示する
  const orderedOptions = [
    ...visibleOptions.filter((opt) => selected.has(opt)),
    ...visibleOptions.filter((opt) => !selected.has(opt)),
  ];

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <p className="text-[12px] text-[var(--c-text-3)]">{title}</p>
        {selected.size > 0 && (
          <span className="text-[11px] text-[var(--accent)] font-medium">{t("{n}件選択中", { n: selected.size })}</span>
        )}
      </div>

      {isSearchable && (
        <div className="relative mb-2">
          <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--c-text-3)]" strokeWidth={2} />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("{title}で検索({n}件)", { title, n: options.length })}
            className="w-full pl-7 pr-2.5 py-1.5 rounded-lg bg-[var(--c-surface-2)] border border-[var(--c-border)] text-[12px] text-[var(--c-text)] placeholder:text-[var(--c-text-3)] focus:outline-none focus:border-[var(--accent-label)]"
          />
        </div>
      )}

      <div className="flex flex-wrap gap-2 max-h-[240px] overflow-y-auto overscroll-contain">
        {orderedOptions.length === 0 && (
          <p className="text-[12px] text-[var(--c-text-3)] py-1">{t("「{query}」に一致する項目がありません", { query })}</p>
        )}
        {orderedOptions.map((opt) => (
          <FilterChip
            key={opt}
            opt={opt}
            active={selected.has(opt)}
            onToggle={onToggle}
            dotColor={getColor ? getColor(opt) : null}
          />
        ))}
      </div>
    </div>
  );
}

// 風味の絞り込み。大分類(カテゴリ)と詳細分類(語)のどちらも選べる(どれかに該当する商品を出す)。
// 詳細分類は、商品の説明文から自動で付く語だけを出す(酸味など、利用者が判断する語は、商品に付かないので出さない)。
function FlavorFilter({ selected, onToggle }) {
  const t = useT();
  const [openId, setOpenId] = useState(null);
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <p className="text-[12px] text-[var(--c-text-3)]">{t("風味(大分類・詳細分類)")}</p>
        {selected.size > 0 && (
          <span className="text-[11px] text-[var(--accent)] font-medium">{t("{n}件選択中", { n: selected.size })}</span>
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        {FLAVOR_CATEGORIES.map((cat) => (
          <FilterChip key={cat.id} opt={cat.ja} active={selected.has(cat.ja)} onToggle={onToggle} dotColor={cat.color} />
        ))}
      </div>
      <p className="text-[11px] text-[var(--c-text-3)] mt-3 mb-1.5">{t("詳細な風味から選ぶ")}</p>
      <div className="flex flex-col gap-1.5">
        {FLAVOR_CATEGORIES.map((cat) => {
          const terms = cat.terms.filter((term) => term.auto !== false);
          const open = openId === cat.id;
          const count = terms.filter((term) => selected.has(term.ja)).length;
          return (
            <div key={cat.id} className="rounded-xl bg-[var(--c-surface-2)] border border-[var(--c-border)] overflow-hidden">
              <button
                type="button"
                onClick={() => setOpenId(open ? null : cat.id)}
                aria-expanded={open}
                className="w-full flex items-center justify-between gap-3 px-3 py-2 text-left"
              >
                <span className="flex items-center gap-2 text-[12px] text-[var(--c-text)]">
                  <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: cat.color }} />
                  {t(cat.ja)}
                  {count > 0 && <span className="text-[11px] text-[var(--accent)] font-medium">{count}</span>}
                </span>
                <ChevronDown size={14} className={`shrink-0 text-[var(--accent-label)] transition-transform ${open ? "rotate-180" : ""}`} />
              </button>
              {open && (
                <div className="px-3 pb-3 pt-2 flex flex-wrap gap-2 border-t border-[var(--c-border)]">
                  {terms.map((term) => (
                    <FilterChip key={term.ja} opt={term.ja} active={selected.has(term.ja)} onToggle={onToggle} dotColor={cat.color} />
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function FilterSheet({
  open,
  onClose,
  filters,
  setFilters,
  resultCount,
  prefectureOptions,
  favoriteAreaPrefecture,
}) {
  const t = useT();
  // Claude Cowork/アプリ内WebViewのような組み込み表示環境では、CSSの
  // ビューポート単位(vh/dvh)が正しく解決されないことがあり、シートの
  // 表示位置がずれる不具合が実際に発生した。そのため、window.innerHeight
  // をJavaScriptで直接測定し、その値からピクセル単位で高さを算出する
  // (画面回転・アドレスバーの表示変化にはresizeイベントで追従する)。
  const [viewportH, setViewportH] = useState(
    typeof window !== "undefined" ? window.innerHeight : 800
  );
  useEffect(() => {
    const onResize = () => setViewportH(window.innerHeight);
    window.addEventListener("resize", onResize);
    window.visualViewport?.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      window.visualViewport?.removeEventListener("resize", onResize);
    };
  }, []);

  const sheetRef = useRef(null);

  // シート表示中は背後のページのスクロールをロックする。
  // 前回 overflow: hidden のみで対処したが、iOS Safariではこれだけでは
  // 背景ページのスクロールを完全には止められないケースがあり、実際に
  // 「シート内を下端までスクロールした後、動かせなくなる」不具合が
  // 再発した。iOSでも確実に効く方法として、bodyをposition: fixedで
  // 固定し、閉じた際に元のスクロール位置へ復帰させる方式に切り替えている。
  useEffect(() => {
    if (!open) return;
    const scrollY = window.scrollY;
    const body = document.body;
    const original = {
      position: body.style.position,
      top: body.style.top,
      width: body.style.width,
      overflow: body.style.overflow,
    };

    body.style.position = "fixed";
    body.style.top = `-${scrollY}px`;
    body.style.width = "100%";
    body.style.overflow = "hidden";

    return () => {
      body.style.position = original.position;
      body.style.top = original.top;
      body.style.width = original.width;
      body.style.overflow = original.overflow;
      window.scrollTo(0, scrollY);
    };
  }, [open]);

  // シートが開くたびに、スクロール位置を必ず先頭(産地の絞り込み)へ
  // リセットする。組み込みWebView環境で、シートが開いた瞬間から
  // 下端(結果を見るボタン)にスクロールした状態になってしまう不具合が
  // 報告されたための対策(原因を問わず確実に先頭から見せるための保険)。
  useEffect(() => {
    if (!open) return;
    const el = sheetRef.current;
    if (!el) return;
    el.scrollTop = 0;
    // 一部環境ではレイアウト確定が1フレーム遅れるため、次のフレームでも念のため実行する
    const raf = requestAnimationFrame(() => {
      if (el) el.scrollTop = 0;
    });
    return () => cancelAnimationFrame(raf);
  }, [open]);

  if (!open) return null;

  const toggle = (dim, value) => {
    setFilters((prev) => {
      const next = new Set(prev[dim]);
      next.has(value) ? next.delete(value) : next.add(value);
      return { ...prev, [dim]: next };
    });
  };

  const selectSingle = (dim, value) => setFilters((prev) => ({ ...prev, [dim]: value }));

  const clearAll = () =>
    setFilters({ country: "", prefecture: "", flavor: new Set(), minRating: 0 });

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        ref={sheetRef}
        className="w-full sm:w-[420px] overflow-y-auto overscroll-contain bg-[var(--c-surface)] border border-[var(--c-border)] rounded-t-2xl sm:rounded-2xl p-5"
        style={{ WebkitOverflowScrolling: "touch", maxHeight: Math.round(viewportH * 0.85) }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h4 className="font-serif text-[19px] text-[var(--c-text)]">{t("絞り込み")}</h4>
          <button
            onClick={onClose}
            className="text-[var(--c-text-3)] hover:text-[var(--c-text)] transition-colors min-w-[44px] min-h-[44px] flex items-center justify-center -m-2.5"
            aria-label={t("閉じる")}
          >
            <X size={18} />
          </button>
        </div>

        {/* 発見につながりやすい軸(産地・風味)を上に、地理的な絞り込み
            (都道府県)を下に配置している。産地・都道府県は単一選択のプル
            ダウン、風味カテゴリのみ複数選択のチップのままにしている。 */}
        <div className="flex flex-col gap-5">
          <div>
            <p className="text-[12px] text-[var(--c-text-3)] mb-2">{t("産地(国)")}</p>
            <select
              value={filters.country}
              onChange={(e) => selectSingle("country", e.target.value)}
              className={SELECT_CLASS}
            >
              <option value="">{t("すべて")}</option>
              {COUNTRIES_BY_ZONE.map((g) => (
                <optgroup key={g.zone} label={t(g.label)}>
                  {g.countries.map((c) => (
                    <option key={c} value={c}>
                      {t(c)}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>

          <FlavorFilter selected={filters.flavor} onToggle={(v) => toggle("flavor", v)} />

          <div>
            <div className="flex items-center justify-between mb-2">
              <p className="text-[12px] text-[var(--c-text-3)]">{t("自分の評価(★)")}</p>
              {filters.minRating > 0 && (
                <span className="text-[11px] text-[var(--accent)] font-medium">
                  {t("★{n}以上", { n: filters.minRating })}
                </span>
              )}
            </div>
            <StarRating
              value={filters.minRating}
              size={26}
              onChange={(stars) => selectSingle("minRating", stars)}
            />
            <p className="text-[11px] text-[var(--c-text-3)] mt-1.5">
              {t("選んだ星の数以上の評価をつけた商品だけを表示します(同じ星をもう一度押すと解除)")}
            </p>
          </div>

          <div>
            <p className="text-[12px] text-[var(--c-text-3)] mb-2">{t("都道府県")}</p>
            <select
              value={filters.prefecture}
              onChange={(e) => selectSingle("prefecture", e.target.value)}
              className={SELECT_CLASS}
            >
              <option value="">{t("すべて")}</option>
              {prefectureOptions.map(({ value, count }) => (
                <option key={value} value={value}>
                  {t(value)}({count})
                </option>
              ))}
            </select>
            {favoriteAreaPrefecture && filters.prefecture !== favoriteAreaPrefecture && (
              <button
                onClick={() => selectSingle("prefecture", favoriteAreaPrefecture)}
                className="mt-2 text-[12px] text-[var(--accent)] underline underline-offset-2"
              >
                {t("登録エリア({area})で絞り込む", { area: t(favoriteAreaPrefecture) })}
              </button>
            )}
          </div>
        </div>

        <div className="flex flex-col gap-2.5 mt-6 pt-4 border-t border-[var(--c-border)]">
          <button
            onClick={onClose}
            className="w-full py-3.5 rounded-xl bg-[var(--accent)] text-[var(--on-accent)] text-[15px] font-bold shadow-[0_4px_16px_var(--accent-glow)] hover:bg-[var(--accent-soft)] transition-colors"
          >
            {t("結果を見る({n}件)", { n: resultCount })}
          </button>
          <button
            onClick={clearAll}
            className="w-full py-2 text-[var(--c-text-3)] text-[12px] underline underline-offset-2 hover:text-[var(--c-text-2)] transition-colors"
          >
            {t("条件をクリア")}
          </button>
        </div>
      </div>
    </div>
  );
}
