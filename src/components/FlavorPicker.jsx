import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { FLAVOR_WHEEL_DATA } from "../data/flavorWheel";

// 用語 → 大分類の色。記録に保存するのは用語(例: "糖蜜")だけで、色は表示時に引く。
const TERM_COLOR = (() => {
  const map = new Map();
  FLAVOR_WHEEL_DATA.forEach((cat) => {
    cat.sub.forEach((s) => s.terms.forEach((t) => !map.has(t) && map.set(t, cat.color)));
  });
  return map;
})();

const termColor = (term) => TERM_COLOR.get(term) ?? "#8B7361";

// 記録済みの風味を色付きのチップで並べる(一覧表示用)
export function FlavorChips({ flavors }) {
  if (!Array.isArray(flavors) || flavors.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {flavors.map((term) => (
        <span
          key={term}
          className="text-[11px] px-2 py-0.5 rounded-full border text-[#F2E9DD]"
          style={{ borderColor: termColor(term), backgroundColor: `${termColor(term)}33` }}
        >
          {term}
        </span>
      ))}
    </div>
  );
}

// 豆知識タブのフレーバーホイールと同じ9大分類・詳細項目から、複数の風味を選ぶ入力部品。
// value: 選択中の用語の配列、onChange: 新しい配列を受け取る。
export function FlavorPicker({ value, onChange }) {
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
            className="shrink-0 text-[11px] text-[#8B7361] hover:text-[#F2E9DD] underline underline-offset-2"
          >
            すべて外す
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
            className="rounded-xl bg-[#3B2211] border overflow-hidden"
            style={{ borderColor: open || selectedCount > 0 ? cat.color : "#4A3A2A" }}
          >
            <button
              type="button"
              onClick={() => setOpenCat(open ? null : cat.en)}
              aria-expanded={open}
              className="w-full flex items-center justify-between gap-3 px-3 py-2.5 text-left"
            >
              <span className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: cat.color }} />
                <span className="text-[13px] text-[#F2E9DD]">{cat.ja}</span>
                {selectedCount > 0 && (
                  <span
                    className="text-[10px] px-1.5 py-0.5 rounded-full text-[#231810] font-medium"
                    style={{ backgroundColor: cat.color }}
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
              <div className="px-3 pb-3 pt-2.5 flex flex-col gap-2.5 border-t border-[#4A3A2A]">
                {cat.sub.map((s) => (
                  <div key={s.group}>
                    <p className="text-[11px] text-[#8B7361] mb-1">{s.group}</p>
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
                                ? "text-[#231810] font-medium"
                                : "bg-[#2F241A] text-[var(--accent-muted)] border-[#4A3A2A] hover:border-[var(--accent-label)]"
                            }`}
                            style={selected ? { backgroundColor: cat.color, borderColor: cat.color } : undefined}
                          >
                            {term}
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
