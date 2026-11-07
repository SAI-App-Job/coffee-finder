import { useEffect, useMemo, useState } from "react";
import { X, Search, Plus, ChevronRight } from "lucide-react";
import { INPUT_CLASS } from "./formStyles";
import { useT } from "../i18n";

const MAX_RESULTS = 30;
const MAX_RECENT = 5;

const normalize = (s) => s.normalize("NFKC").toLowerCase();

function ShopRow({ name, address, badge, onClick }) {
  return (
    <button
      onClick={onClick}
      className="w-full text-left flex items-center justify-between gap-3 rounded-xl bg-[var(--c-surface-2)] border border-[var(--c-border)] px-3.5 py-2.5 hover:border-[var(--accent-label)] transition-colors"
    >
      <span className="min-w-0">
        <span className="block text-[13px] text-[var(--c-text)] truncate">{name}</span>
        {(address || badge) && (
          <span className="block text-[11px] text-[var(--c-text-3)] mt-0.5 truncate">
            {badge && <span className="text-[var(--accent-muted)]">{badge} </span>}
            {address}
          </span>
        )}
      </span>
      <ChevronRight size={14} className="shrink-0 text-[var(--c-text-3)]" strokeWidth={1.75} />
    </button>
  );
}

// 商品登録の最初のステップ「どのお店?」。アプリに載っている店舗を検索して選ぶか、
// 載っていないお店を新規登録する。登録済みの店舗(最近のもの)は、検索なしで選べる。
export function UserShopPickerModal({ open, appShops, userShops, onPickAppShop, onPickUserShop, onNewShop, onClose }) {
  const t = useT();
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (open) setQuery("");
  }, [open]);

  // 店名・住所を検索用に正規化しておく(全角/半角・大文字小文字の違いを吸収)
  const indexed = useMemo(
    () => appShops.map((s) => ({ ...s, key: normalize(`${s.name} ${s.address}`) })),
    [appShops]
  );

  if (!open) return null;

  const q = normalize(query.trim());
  const matches = q ? indexed.filter((s) => s.key.includes(q)) : [];
  const recent = [...userShops].sort((a, b) => b.createdAt.localeCompare(a.createdAt)).slice(0, MAX_RECENT);

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full sm:w-[440px] max-h-[85vh] overflow-y-auto bg-[var(--c-surface)] border border-[var(--c-border)] rounded-t-2xl sm:rounded-2xl p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 mb-4">
          <div className="min-w-0">
            <p className="text-[11px] tracking-wider text-[var(--accent-label)] uppercase">Step 1</p>
            <h3 className="font-serif text-[17px] text-[var(--c-text)] mt-0.5">{t("どのお店の商品?")}</h3>
          </div>
          <button
            onClick={onClose}
            className="shrink-0 text-[var(--c-text-3)] hover:text-[var(--c-text)] transition-colors min-w-[36px] min-h-[36px] flex items-center justify-center -m-2"
            aria-label={t("閉じる")}
          >
            <X size={18} />
          </button>
        </div>

        <div className="relative mb-3">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--c-text-3)]" strokeWidth={2} />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("アプリに載っている店舗を、店名・住所で検索")}
            autoFocus
            className={`${INPUT_CLASS} pl-9`}
          />
        </div>

        <div className="flex flex-col gap-2">
          {q ? (
            matches.length === 0 ? (
              <p className="text-[12px] text-[var(--c-text-3)] py-3 text-center">
                {t("「{query}」に一致する店舗がありません。下の「リストにないお店を新規登録」から登録できます。", { query: query.trim() })}
              </p>
            ) : (
              <>
                <p className="text-[11px] text-[var(--c-text-3)]">
                  {matches.length > MAX_RESULTS
                    ? t("{total}件中{shown}件を表示(絞り込んでください)", { total: matches.length, shown: MAX_RESULTS })
                    : t("{n}件", { n: matches.length })}
                </p>
                {matches.slice(0, MAX_RESULTS).map((s) => (
                  <ShopRow key={s.name} name={s.name} address={s.address} onClick={() => onPickAppShop(s)} />
                ))}
              </>
            )
          ) : (
            recent.length > 0 && (
              <>
                <p className="text-[11px] text-[var(--c-text-3)]">{t("最近の登録先")}</p>
                {recent.map((s) => (
                  <ShopRow
                    key={s.id}
                    name={s.name}
                    address={s.address}
                    badge={s.appShopName ? t("アプリ掲載店") : t("登録した店舗")}
                    onClick={() => onPickUserShop(s)}
                  />
                ))}
              </>
            )
          )}
        </div>

        <button
          onClick={onNewShop}
          className="w-full mt-4 flex items-center justify-center gap-1.5 py-2.5 rounded-xl border border-dashed border-[var(--accent-label)] text-[var(--accent-on-glow)] text-[13px] font-medium hover:bg-[var(--c-surface-2)] transition-colors"
        >
          <Plus size={14} strokeWidth={2.2} />
          {t("リストにないお店を新規登録")}
        </button>
      </div>
    </div>
  );
}
