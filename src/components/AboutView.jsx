import { Info, X, Compass, Store } from "lucide-react";

// ヘッダーのⓘアイコンから開く、アプリ全体の説明パネル。
// AlertsPanelと同じボトムシート/モーダルの型を踏襲している。
export function AboutView({ open, onClose }) {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full sm:w-[480px] max-h-[85vh] overflow-y-auto bg-[#2F241A] border border-[#4A3A2A] rounded-t-2xl sm:rounded-2xl p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-1.5">
            <Info size={16} className="text-[var(--accent)]" strokeWidth={1.75} />
            <h3 className="font-serif text-[18px] text-[#F2E9DD]">このアプリについて</h3>
          </div>
          <button
            onClick={onClose}
            className="shrink-0 text-[#8B7361] hover:text-[#F2E9DD] transition-colors min-w-[36px] min-h-[36px] flex items-center justify-center -m-2"
            aria-label="閉じる"
          >
            <X size={18} />
          </button>
        </div>

        <div className="flex flex-col gap-5">
          <section className="flex flex-col gap-3">
            <div className="flex items-center gap-1.5">
              <Compass size={14} className="text-[var(--accent)]" strokeWidth={1.75} />
              <h4 className="text-[14px] font-medium text-[#F2E9DD]">アプリのコンセプト</h4>
            </div>
            <p className="text-[12px] text-[#8B7361] leading-relaxed">
              このアプリは「コーヒー豆を発見すること」を何より優先しています。価格の安さや話題性ではなく、まだ知られていない一杯・一袋との出会いを増やすことが目的です。
            </p>
            <p className="text-[12px] text-[#8B7361] leading-relaxed">
              そのため、オンライン販売の有無や価格情報の掲載状況は掲載可否の基準にしていません。店頭限定販売の店舗や、Instagram・Googleマップのみで営業している店舗も、産地・価格等の商品情報が何らかの形で確認できれば対象に含めています。
            </p>
            <p className="text-[12px] text-[#8B7361] leading-relaxed">
              産地・グレード・精選方法などの情報は、できる限り一次資料(各店舗・生産者の公式発表、業界団体の公式資料等)に基づいて記載するよう努めています。
            </p>
          </section>

          <section className="flex flex-col gap-3">
            <div className="flex items-center gap-1.5">
              <Store size={14} className="text-[var(--accent)]" strokeWidth={1.75} />
              <h4 className="text-[14px] font-medium text-[#F2E9DD]">掲載基準について</h4>
            </div>
            <p className="text-[12px] text-[#8B7361] leading-relaxed">
              個人〜小規模の自家焙煎店を中心に掲載しています。11店舗以上を展開する大手チェーンは対象外です(日本チェーンストア協会の定義に基づく)。ただし11店舗未満の複数拠点展開(例:
              FUGLEN、PHILOCOFFEA)は対象に含みます。
            </p>
          </section>
        </div>
      </div>
    </div>
  );
}
