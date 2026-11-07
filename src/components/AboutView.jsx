import { Info, X, Compass, Store, MessageCircle, ShieldCheck } from "lucide-react";

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
        className="w-full sm:w-[480px] max-h-[85vh] overflow-y-auto bg-[var(--c-surface)] border border-[var(--c-border)] rounded-t-2xl sm:rounded-2xl p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-1.5">
            <Info size={16} className="text-[var(--accent)]" strokeWidth={1.75} />
            <h3 className="font-serif text-[18px] text-[var(--c-text)]">このアプリについて</h3>
          </div>
          <button
            onClick={onClose}
            className="shrink-0 text-[var(--c-text-3)] hover:text-[var(--c-text)] transition-colors min-w-[36px] min-h-[36px] flex items-center justify-center -m-2"
            aria-label="閉じる"
          >
            <X size={18} />
          </button>
        </div>

        <div className="flex flex-col gap-5">
          <section className="flex flex-col gap-3">
            <div className="flex items-center gap-1.5">
              <Compass size={14} className="text-[var(--accent)]" strokeWidth={1.75} />
              <h4 className="text-[14px] font-medium text-[var(--c-text)]">アプリのコンセプト</h4>
            </div>
            <p className="text-[12px] text-[var(--c-text-3)] leading-relaxed">
              このアプリは「コーヒー豆を発見すること」を何より優先しています。価格の安さや話題性ではなく、まだ知られていない一杯・一袋との出会いを増やすことが目的です。
            </p>
            <p className="text-[12px] text-[var(--c-text-3)] leading-relaxed">
              そのため、オンライン販売の有無や価格情報の掲載状況は掲載可否の基準にしていません。店頭限定販売の店舗や、Instagram・Googleマップのみで営業している店舗も、産地・価格等の商品情報が何らかの形で確認できれば対象に含めています。
            </p>
            <p className="text-[12px] text-[var(--c-text-3)] leading-relaxed">
              産地・グレード・精選方法などの情報は、できる限り一次資料(各店舗・生産者の公式発表、業界団体の公式資料等)に基づいて記載するよう努めています。
            </p>
          </section>

          <section className="flex flex-col gap-3">
            <div className="flex items-center gap-1.5">
              <Store size={14} className="text-[var(--accent)]" strokeWidth={1.75} />
              <h4 className="text-[14px] font-medium text-[var(--c-text)]">掲載基準について</h4>
            </div>
            <p className="text-[12px] text-[var(--c-text-3)] leading-relaxed">
              個人〜小規模の自家焙煎店を中心に掲載しています。11店舗以上を展開する大手チェーンは対象外です(日本チェーンストア協会の定義に基づく)。ただし11店舗未満の複数拠点展開(例:
              FUGLEN、PHILOCOFFEA)は対象に含みます。
            </p>
          </section>

          <section className="flex flex-col gap-3">
            <div className="flex items-center gap-1.5">
              <ShieldCheck size={14} className="text-[var(--accent)]" strokeWidth={1.75} />
              <h4 className="text-[14px] font-medium text-[var(--c-text)]">データの取り扱い(プライバシー)</h4>
            </div>
            <ul className="list-disc pl-4 flex flex-col gap-2 text-[12px] text-[var(--c-text-3)] leading-relaxed marker:text-[var(--c-text-3)]">
              <li>
                コレクション、★評価、テイスティングログ・ノート、閲覧履歴、設定などの記録は、お使いの端末(ブラウザ)内にのみ保存され、運営者が取得することはありません。
              </li>
              <li>
                パッケージ写真は、お使いの端末内にのみ保存され、運営者がサーバー等へ送信・取得・公開することはありません。
              </li>
              <li>
                位置情報は、「近い順」の並べ替えにだけ使います。端末内で計算し、サーバーへの送信や保存はしません。許可しなくても、アプリはお使いいただけます。
              </li>
              <li>
                表示に必要な外部サービス(商品・店舗データの配信元の GitHub、地図の OpenStreetMap、フォントの Google Fonts)とは通信します。通信の仕組み上、これらのサービスには、お使いの端末のIPアドレス等が届きます。
              </li>
              <li>
                ブラウザのサイトデータを削除したり、端末を変更したりすると、これらの記録は失われます。「コレクションのバックアップ」で、ファイルに書き出して保管できます(パッケージ写真は、書き出すときに選んだ場合だけ含まれます)。
              </li>
            </ul>
            <p className="text-[11px] text-[var(--c-text-3)]">最終更新: 2026年11月8日</p>
            <a
              href={`${import.meta.env.BASE_URL}privacy-policy.html`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 self-start text-[12px] text-[var(--accent-label)] hover:text-[var(--accent)] transition-colors underline underline-offset-2"
            >
              プライバシーポリシー(全文)
            </a>
          </section>

          <section className="flex flex-col gap-3">
            <div className="flex items-center gap-1.5">
              <MessageCircle size={14} className="text-[var(--accent)]" strokeWidth={1.75} />
              <h4 className="text-[14px] font-medium text-[var(--c-text)]">掲載店舗の方へ</h4>
            </div>
            <p className="text-[12px] text-[var(--c-text-3)] leading-relaxed">
              内容の修正・削除等のご希望は、こちらのXアカウント(DM)までご連絡ください。
            </p>
            <a
              href="https://x.com/SaiCoffea"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 self-start text-[12px] text-[var(--accent-label)] hover:text-[var(--accent)] transition-colors underline underline-offset-2"
            >
              @SaiCoffea (X)
            </a>
          </section>
        </div>
      </div>
    </div>
  );
}
