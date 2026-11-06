import { History } from "lucide-react";
import { SectionHeading } from "./common";
import { FREE_HISTORY_RETENTION_DAYS } from "../hooks/useViewHistory";
import { formatRelativeTime } from "../utils/format";

// 「履歴」画面: 商品詳細を開いた閲覧履歴(新しい順)。行を押すと商品詳細を開く。
export function HistoryView({ historyItems, isPremium, onOpenDetail }) {
  return (
    <main className="px-5 py-5 flex flex-col gap-3 max-w-xl mx-auto">
      <SectionHeading en="History" ja="履歴" />
      <p className="text-[12px] text-[var(--c-text-3)] leading-relaxed">
        {isPremium
          ? "閲覧履歴は無制限に保存されます。"
          : `無料プランでは直近${FREE_HISTORY_RETENTION_DAYS}日分のみ保存されます(有料プランでは無制限)。`}
      </p>
      {historyItems.length === 0 ? (
        <div className="text-center py-16 text-[var(--c-text-3)]">
          <History size={28} className="mx-auto mb-3 opacity-40" />
          <p className="text-[14px]">まだ閲覧履歴がありません</p>
          <p className="text-[12px] mt-1">商品をタップすると、ここに履歴が表示されます</p>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          <p className="text-[12px] text-[var(--c-text-3)]">{historyItems.length}件</p>
          {historyItems.map(({ product, viewedAt }) => (
            <button
              key={product.id}
              onClick={() => onOpenDetail(product)}
              className="w-full text-left flex items-center justify-between gap-3 rounded-xl bg-[var(--c-surface)] border border-[var(--c-border)] px-3.5 py-3 hover:border-[var(--accent-label)] transition-colors"
            >
              <div className="min-w-0">
                <p className="text-[13px] text-[var(--c-text)] truncate">{product.rawName}</p>
                <p className="text-[11px] text-[var(--c-text-3)] mt-0.5 truncate">{product.shopName}</p>
              </div>
              <p className="text-[10px] text-[var(--c-text-3)] shrink-0">{formatRelativeTime(viewedAt)}</p>
            </button>
          ))}
        </div>
      )}
    </main>
  );
}
