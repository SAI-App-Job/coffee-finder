import { useState, useRef, useEffect } from "react";
import { Search, Check, X } from "lucide-react";
import { ROAST_LEVELS } from "../data/roastLevels";
import { PREFECTURES } from "../data/products";
import { ORIGIN_GUIDE, ORIGIN_ZONE_ORDER, ORIGIN_ZONE_LABELS } from "../data/originGuide";
import { FLAVOR_WHEEL_DATA, FLAVOR_CATEGORY_OPTIONS } from "../data/flavorWheel";
import { FILTER_SEARCH_THRESHOLD } from "../data/navigation";

// 産地(国)フィルタの選択肢は、店舗の実データ(originCountryの表記ゆれが多い)
// ではなく、17ヶ国を整理済みのORIGIN_GUIDEを唯一の情報源とする。アフリカ/
// 中南米/アジアの3グループに分け、産地タブの地図と同じ見出し・順序で表示する。
const COUNTRIES_BY_ZONE = ORIGIN_ZONE_ORDER.map((zone) => ({
  zone,
  label: ORIGIN_ZONE_LABELS[zone],
  countries: ORIGIN_GUIDE.filter((o) => o.zone === zone).map((o) => o.country),
}));

function FilterChip({ opt, active, onToggle, dotColor }) {
  return (
    <button
      onClick={() => onToggle(opt)}
      className={`flex items-center gap-1.5 text-[13px] px-3 py-1.5 rounded-full border-2 transition-all ${
        active
          ? "bg-white text-[#231810] border-white font-medium shadow-[0_0_0_3px_var(--accent-glow)]"
          : "border-[#4A3A2A] text-[#B8A891] hover:border-[var(--accent-label)]"
      }`}
    >
      {dotColor && (
        <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: dotColor }} />
      )}
      {active && <Check size={12} strokeWidth={3} />}
      {opt}
    </button>
  );
}

export function FilterSection({ title, options, selected, onToggle, getColor }) {
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
        <p className="text-[12px] text-[#8B7361]">{title}</p>
        {selected.size > 0 && (
          <span className="text-[11px] text-[var(--accent)] font-medium">{selected.size}件選択中</span>
        )}
      </div>

      {isSearchable && (
        <div className="relative mb-2">
          <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#8B7361]" strokeWidth={2} />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={`${title}で検索(${options.length}件)`}
            className="w-full pl-7 pr-2.5 py-1.5 rounded-lg bg-[#3B2211] border border-[#4A3A2A] text-[12px] text-[#F2E9DD] placeholder:text-[#8B7361] focus:outline-none focus:border-[var(--accent-label)]"
          />
        </div>
      )}

      <div className="flex flex-wrap gap-2 max-h-[240px] overflow-y-auto overscroll-contain">
        {orderedOptions.length === 0 && (
          <p className="text-[12px] text-[#8B7361] py-1">「{query}」に一致する項目がありません</p>
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

// 産地(国)専用の絞り込みセクション。アフリカ/中南米/アジアの見出しごとに
// 国を分けて表示することで、17ヶ国が並んでも見渡しやすくする(産地タブの
// マップと同じグルーピング)。検索時は各グループ内で絞り込み、該当なしの
// グループは見出しごと非表示にする。
function CountryFilterSection({ title, selected, onToggle }) {
  const [query, setQuery] = useState("");
  const totalCount = COUNTRIES_BY_ZONE.reduce((sum, g) => sum + g.countries.length, 0);
  const isSearchable = totalCount > FILTER_SEARCH_THRESHOLD;
  const q = query.trim().toLowerCase();

  const visibleGroups = COUNTRIES_BY_ZONE.map((g) => ({
    ...g,
    countries: q ? g.countries.filter((c) => c.toLowerCase().includes(q)) : g.countries,
  })).filter((g) => g.countries.length > 0);

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <p className="text-[12px] text-[#8B7361]">{title}</p>
        {selected.size > 0 && (
          <span className="text-[11px] text-[var(--accent)] font-medium">{selected.size}件選択中</span>
        )}
      </div>

      {isSearchable && (
        <div className="relative mb-2">
          <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#8B7361]" strokeWidth={2} />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={`${title}で検索(${totalCount}件)`}
            className="w-full pl-7 pr-2.5 py-1.5 rounded-lg bg-[#3B2211] border border-[#4A3A2A] text-[12px] text-[#F2E9DD] placeholder:text-[#8B7361] focus:outline-none focus:border-[var(--accent-label)]"
          />
        </div>
      )}

      <div className="flex flex-col gap-3 max-h-[280px] overflow-y-auto overscroll-contain">
        {visibleGroups.length === 0 && (
          <p className="text-[12px] text-[#8B7361] py-1">「{query}」に一致する項目がありません</p>
        )}
        {visibleGroups.map((g) => (
          <div key={g.zone}>
            <p className="text-[10px] tracking-wide text-[#8B7361] uppercase mb-1.5">{g.label}</p>
            <div className="flex flex-wrap gap-2">
              {g.countries.map((opt) => (
                <FilterChip key={opt} opt={opt} active={selected.has(opt)} onToggle={onToggle} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function FilterSheet({ open, onClose, filters, setFilters, resultCount }) {
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

  const clearAll = () =>
    setFilters({ country: new Set(), prefecture: new Set(), flavorCategory: new Set(), roast: new Set() });

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        ref={sheetRef}
        className="w-full sm:w-[420px] overflow-y-auto overscroll-contain bg-[#2F241A] border border-[#4A3A2A] rounded-t-2xl sm:rounded-2xl p-5"
        style={{ WebkitOverflowScrolling: "touch", maxHeight: Math.round(viewportH * 0.85) }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h4 className="font-serif text-[19px] text-[#F2E9DD]">絞り込み</h4>
          <button
            onClick={onClose}
            className="text-[#8B7361] hover:text-[#F2E9DD] transition-colors min-w-[44px] min-h-[44px] flex items-center justify-center -m-2.5"
            aria-label="閉じる"
          >
            <X size={18} />
          </button>
        </div>

        {/* 発見につながりやすい軸(産地・風味・焙煎度)を上に、地理的な絞り込み
            (都道府県)を下に配置している */}
        <div className="flex flex-col gap-5">
          <CountryFilterSection
            title="産地(国)"
            selected={filters.country}
            onToggle={(v) => toggle("country", v)}
          />
          <FilterSection
            title="風味カテゴリ(フレーバーホイール)"
            options={FLAVOR_CATEGORY_OPTIONS}
            selected={filters.flavorCategory}
            onToggle={(v) => toggle("flavorCategory", v)}
            getColor={(opt) => FLAVOR_WHEEL_DATA.find((c) => c.ja === opt)?.color}
          />
          <FilterSection
            title="焙煎度(浅→深)"
            options={ROAST_LEVELS.map((r) => r.key)}
            selected={filters.roast}
            onToggle={(v) => toggle("roast", v)}
            getColor={(opt) => ROAST_LEVELS.find((r) => r.key === opt)?.color}
          />
          <FilterSection
            title="都道府県"
            options={PREFECTURES}
            selected={filters.prefecture}
            onToggle={(v) => toggle("prefecture", v)}
          />
        </div>

        <div className="flex flex-col gap-2.5 mt-6 pt-4 border-t border-[#4A3A2A]">
          <button
            onClick={onClose}
            className="w-full py-3.5 rounded-xl bg-[var(--accent)] text-[#231810] text-[15px] font-bold shadow-[0_4px_16px_var(--accent-glow)] hover:bg-[var(--accent-soft)] transition-colors"
          >
            結果を見る({resultCount}件)
          </button>
          <button
            onClick={clearAll}
            className="w-full py-2 text-[#8B7361] text-[12px] underline underline-offset-2 hover:text-[#B8A891] transition-colors"
          >
            条件をクリア
          </button>
        </div>
      </div>
    </div>
  );
}
