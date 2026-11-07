import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { FLAVOR_WHEEL_DATA } from "../data/flavorWheel";
import { useT } from "../i18n";

// 用語 → 大分類の色。記録に保存するのは用語(例: "糖蜜")だけで、色は表示時に引く。
const TERM_COLOR = (() => {
  const map = new Map();
  FLAVOR_WHEEL_DATA.forEach((cat) => {
    cat.sub.forEach((s) => s.terms.forEach((t) => !map.has(t) && map.set(t, cat.color)));
  });
  return map;
})();

// 色の末尾に透明度(`33`等)を付けて使うため、変数ではなく16進の固定色で返す
const termColor = (term) => TERM_COLOR.get(term) ?? "#8b7361";

// 分類の色を背景に塗ったときに、コントラストが高くなる方の文字色(白/濃い茶)を返す。
// 分類色は明るいもの(ゴールド等)から暗いもの(ロースト)まであるため、テーマとは無関係に色から決める。
function readableOn(hex) {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const v = parseInt(hex.slice(i, i + 2), 16) / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  });
  const lum = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  const contrastWithDark = (lum + 0.05) / (0.0095 + 0.05); // 濃い茶 #231810
  const contrastWithWhite = 1.05 / (lum + 0.05);
  return contrastWithDark >= contrastWithWhite ? "#231810" : "#ffffff";
}

// 記録済みの風味を色付きのチップで並べる(一覧表示用)
export function FlavorChips({ flavors }) {
  const t = useT();
  if (!Array.isArray(flavors) || flavors.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {flavors.map((term) => (
        <span
          key={term}
          className="text-[11px] px-2 py-0.5 rounded-full border text-[var(--c-text)]"
          style={{ borderColor: termColor(term), backgroundColor: `${termColor(term)}33` }}
        >
          {t(term)}
        </span>
      ))}
    </div>
  );
}

// 豆知識タブのフレーバーホイールと同じ9大分類・詳細項目から、複数の風味を選ぶ入力部品。
// value: 選択中の用語の配列、onChange: 新しい配列を受け取る。
export function FlavorPicker({ value, onChange }) {
  const t = useT();
  const [openCat, setOpenCat] = useState(null);

  const toggle = (term) => {
    onChange(value.includes(term) ? value.filter((t) => t !== term) : [...value, term]);
  };

  return (
    <div className="flex flex-col gap-2">
      {value.length > 0 && (
        <div className="flex items-start justify-between gap-2">
          <FlavorChips flavors={value} />
          <button
            type="button"
            onClick={() => onChange([])}
            className="shrink-0 text-[11px] text-[var(--c-text-3)] hover:text-[var(--c-text)] underline underline-offset-2"
          >
            {t("すべて外す")}
          </button>
        </div>
      )}
      {FLAVOR_WHEEL_DATA.map((cat) => {
        const open = openCat === cat.en;
        const selectedCount = cat.sub.reduce(
          (n, s) => n + s.terms.filter((t) => value.includes(t)).length,
          0
        );
        return (
          <div
            key={cat.en}
            className="rounded-xl bg-[var(--c-surface-2)] border overflow-hidden"
            style={{ borderColor: open || selectedCount > 0 ? cat.color : "var(--c-border)" }}
          >
            <button
              type="button"
              onClick={() => setOpenCat(open ? null : cat.en)}
              aria-expanded={open}
              className="w-full flex items-center justify-between gap-3 px-3 py-2.5 text-left"
            >
              <span className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: cat.color }} />
                <span className="text-[13px] text-[var(--c-text)]">{t(cat.ja)}</span>
                {selectedCount > 0 && (
                  <span
                    className="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
                    style={{ backgroundColor: cat.color, color: readableOn(cat.color) }}
                  >
                    {selectedCount}
                  </span>
                )}
              </span>
              <ChevronDown
                size={14}
                className={`shrink-0 text-[var(--accent-label)] transition-transform ${open ? "rotate-180" : ""}`}
              />
            </button>
            {open && (
              <div className="px-3 pb-3 pt-2.5 flex flex-col gap-2.5 border-t border-[var(--c-border)]">
                {cat.sub.map((s) => (
                  <div key={s.group}>
                    <p className="text-[11px] text-[var(--c-text-3)] mb-1">{t(s.group)}</p>
                    <div className="flex flex-wrap gap-1.5">
                      {s.terms.map((term) => {
                        const selected = value.includes(term);
                        return (
                          <button
                            key={term}
                            type="button"
                            onClick={() => toggle(term)}
                            aria-pressed={selected}
                            className={`text-[12px] px-2.5 py-1 rounded-full border transition-colors ${
                              selected
                                ? "font-medium"
                                : "bg-[var(--c-surface)] text-[var(--accent-muted)] border-[var(--c-border)] hover:border-[var(--accent-label)]"
                            }`}
                            style={
                              selected
                                ? { backgroundColor: cat.color, borderColor: cat.color, color: readableOn(cat.color) }
                                : undefined
                            }
                          >
                            {t(term)}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
