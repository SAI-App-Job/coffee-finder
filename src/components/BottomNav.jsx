import { useEffect, useState } from "react";
import { ChevronUp } from "lucide-react";
import { NAV_TABS, isNavTabActive, isNavTargetCurrent } from "../data/navigation";
import { useLang, useT } from "../i18n";

const POPUP_CELL_PX = 76;
const POPUP_MAX_COLUMNS = 4;
const POPUP_PADDING_PX = 12;
const POPUP_EDGE_GAP_PX = 8;

// 子メニューの位置: 押したタブの真上を中心にしつつ、画面の左右端からははみ出さないようにする。
// `100%` はどちらも「タブバーの幅」基準(width / left は同じ包含ブロックを基準にするため)。
function popupStyle(tabIndex, childCount) {
  const columns = Math.min(childCount, POPUP_MAX_COLUMNS);
  const naturalWidth = columns * POPUP_CELL_PX + POPUP_PADDING_PX * 2;
  const width = `min(${naturalWidth}px, 100% - ${POPUP_EDGE_GAP_PX * 2}px)`;
  const centerPct = ((tabIndex + 0.5) / NAV_TABS.length) * 100;
  return {
    "--popup-w": width,
    width: "var(--popup-w)",
    left: `clamp(${POPUP_EDGE_GAP_PX}px, calc(${centerPct}% - var(--popup-w) / 2), calc(100% - var(--popup-w) - ${POPUP_EDGE_GAP_PX}px))`,
    gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`,
  };
}

// 件数バッジ(お知らせの未確認件数)。親(relative)の右上に重ねる。
function CountBadge({ count, className = "" }) {
  if (!count) return null;
  return (
    <span
      className={`absolute min-w-[16px] h-4 px-1 rounded-full bg-[var(--accent)] text-[var(--on-accent)] text-[10px] font-bold leading-none flex items-center justify-center ${className}`}
    >
      {count > 9 ? "9+" : count}
    </span>
  );
}

// 画面下部のメインメニュー(タブバー)。子メニューを持つタブは、押すとそのタブの真上に
// アイコン付きの子メニューが重なって開く(画面のレイアウトは押し下げない)。
// 子メニューは、項目を選ぶ・外側を押す・同じタブをもう一度押す・Escapeで閉じる。
// alertCount: お知らせの件数(action: "alerts" の項目とその親タブにバッジで表示)。
// onAction: action を持つ子メニュー項目が押されたときに呼ぶ。
export function BottomNav({ page, triviaSub, onNavigate, alertCount = 0, onAction }) {
  const t = useT();
  const { lang } = useLang();
  const [openTabId, setOpenTabId] = useState(null);

  useEffect(() => {
    if (!openTabId) return;
    const onKey = (e) => e.key === "Escape" && setOpenTabId(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [openTabId]);

  const handleTabClick = (tab) => {
    if (tab.children) {
      setOpenTabId((prev) => (prev === tab.id ? null : tab.id));
    } else {
      setOpenTabId(null);
      onNavigate({ page: tab.page });
    }
  };

  const handleChildClick = (target) => {
    setOpenTabId(null);
    if (target.action) onAction?.(target.action);
    else onNavigate(target);
  };

  const badgeCountFor = (item) => (item.action === "alerts" ? alertCount : 0);

  return (
    <>
      {/* 子メニューの外側を押したら閉じるための、画面全体を覆う透明な面 */}
      {openTabId && <div className="fixed inset-0 z-0" onClick={() => setOpenTabId(null)} aria-hidden="true" />}

      <nav
        aria-label={t("メインメニュー")}
        className="relative z-10 border-t border-[var(--c-border)] bg-[var(--c-bar)] pb-[env(safe-area-inset-bottom)]"
      >
        <div className="relative max-w-xl mx-auto flex">
          {NAV_TABS.map((tab) => {
            const Icon = tab.icon;
            const open = openTabId === tab.id;
            const active = open || isNavTabActive(tab, page);
            return (
              <button
                key={tab.id}
                onClick={() => handleTabClick(tab)}
                aria-haspopup={tab.children ? "menu" : undefined}
                aria-expanded={tab.children ? open : undefined}
                aria-current={!tab.children && active ? "page" : undefined}
                className={`flex-1 flex flex-col items-center justify-center gap-0.5 pt-1.5 pb-1.5 transition-colors ${
                  active ? "text-[var(--accent)]" : "text-[var(--c-text-2)] hover:text-[var(--c-text)]"
                }`}
              >
                <span
                  className={`relative h-7 w-12 rounded-full flex items-center justify-center transition-colors ${
                    active ? "bg-[var(--accent-glow)]" : ""
                  }`}
                >
                  <Icon size={21} strokeWidth={active ? 2.1 : 1.75} />
                  <CountBadge
                    count={tab.children?.reduce((sum, c) => sum + badgeCountFor(c), 0)}
                    className="-top-1 -right-0.5"
                  />
                </span>
                <span className="flex items-center gap-0.5 text-[10px] font-medium leading-none">
                  {t(tab.ja)}
                  {tab.children && (
                    <ChevronUp
                      size={9}
                      strokeWidth={2.5}
                      className={`transition-transform ${open ? "rotate-180" : ""}`}
                    />
                  )}
                </span>
              </button>
            );
          })}

          {openTabId &&
            NAV_TABS.map((tab, index) =>
              tab.id === openTabId && tab.children ? (
                <div
                  key={tab.id}
                  role="menu"
                  aria-label={t("{name}のメニュー", { name: t(tab.ja) })}
                  className="nav-popup absolute bottom-full mb-2 grid gap-y-3 rounded-2xl bg-[var(--c-surface)] border border-[var(--c-border)] shadow-[0_8px_24px_rgba(0,0,0,0.3)]"
                  style={{ ...popupStyle(index, tab.children.length), padding: POPUP_PADDING_PX }}
                >
                  {tab.children.map((child) => {
                    const ChildIcon = child.icon;
                    const current = isNavTargetCurrent(child, page, triviaSub);
                    return (
                      <button
                        key={`${child.action ?? child.page}-${child.sub ?? ""}`}
                        role="menuitem"
                        onClick={() => handleChildClick(child)}
                        aria-current={current ? "page" : undefined}
                        className="flex flex-col items-center gap-1.5 px-0.5"
                      >
                        <span
                          className={`relative w-12 h-12 rounded-full flex items-center justify-center border transition-colors ${
                            current
                              ? "bg-[var(--accent)] text-[var(--on-accent)] border-[var(--accent)]"
                              : "bg-[var(--c-surface-2)] text-[var(--c-text-2)] border-[var(--c-border)]"
                          }`}
                        >
                          <ChildIcon size={20} strokeWidth={1.9} />
                          <CountBadge count={badgeCountFor(child)} className="-top-1 -right-1" />
                        </span>
                        <span
                          className={`text-[10px] leading-tight text-center whitespace-pre-line ${
                            current ? "text-[var(--accent)] font-medium" : "text-[var(--c-text-2)]"
                          }`}
                        >
                          {lang === "en" && child.en ? child.en : t(child.popupLabel ?? child.ja)}
                        </span>
                      </button>
                    );
                  })}
                </div>
              ) : null
            )}
        </div>
      </nav>
    </>
  );
}
