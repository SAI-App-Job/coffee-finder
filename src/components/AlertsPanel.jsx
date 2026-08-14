import { X, Bell, TrendingDown, PackageCheck, Sparkles } from "lucide-react";

const TYPE_META = {
  priceDrop: { label: "値下げ", icon: TrendingDown },
  restock: { label: "在庫復活", icon: PackageCheck },
  newProduct: { label: "新商品", icon: Sparkles },
};

// ベルアイコンをタップすると開く、前回訪問時からの変化一覧。
// 値下げ・在庫復活はお気に入り商品、新商品はお気に入り店舗(派生方式)からのみ検出。
export function AlertsPanel({ open, alerts, products, onClose, onOpenDetail }) {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full sm:w-[440px] max-h-[85vh] overflow-y-auto bg-[#2F241A] border border-[#4A3A2A] rounded-t-2xl sm:rounded-2xl p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-1.5">
            <Bell size={16} className="text-[var(--accent)]" strokeWidth={1.75} />
            <h3 className="font-serif text-[18px] text-[#F2E9DD]">お知らせ</h3>
          </div>
          <button
            onClick={onClose}
            className="shrink-0 text-[#8B7361] hover:text-[#F2E9DD] transition-colors min-w-[36px] min-h-[36px] flex items-center justify-center -m-2"
            aria-label="閉じる"
          >
            <X size={18} />
          </button>
        </div>

        {alerts.length === 0 ? (
          <div className="text-center py-10 text-[#8B7361]">
            <Bell size={28} className="mx-auto mb-3 opacity-40" />
            <p className="text-[14px]">新しいお知らせはありません</p>
            <p className="text-[12px] mt-1 leading-relaxed">
              お気に入り商品の値下げ・在庫復活、お気に入り店舗の新商品をお知らせします
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {alerts.map((alert) => {
              const meta = TYPE_META[alert.type];
              const Icon = meta.icon;
              const product = products.find((p) => String(p.id) === alert.productId);
              return (
                <button
                  key={alert.id}
                  onClick={() => product && onOpenDetail(product)}
                  className="text-left rounded-xl bg-[#3B2211] border border-[#4A3A2A] px-3.5 py-3 hover:border-[var(--accent)] transition-colors flex items-start gap-2.5"
                >
                  <Icon size={15} className="text-[var(--accent)] shrink-0 mt-0.5" strokeWidth={1.75} />
                  <div className="min-w-0">
                    <p className="text-[10px] text-[var(--accent-label)] uppercase tracking-wide">
                      {meta.label} ・ {alert.shopName}
                    </p>
                    <p className="text-[13px] text-[#F2E9DD] mt-0.5 truncate">{alert.productName}</p>
                    <p className="text-[12px] text-[#B8A891] mt-0.5">{alert.detail}</p>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
