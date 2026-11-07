import { Sparkles } from "lucide-react";
import { computeFlavorPreferenceScores, recommendByFlavorCategories } from "../utils/flavor";
import { formatPrice } from "../utils/format";
import { useT } from "../i18n";

const TOP_CATEGORY_COUNT = 3;
const SHOWN_CATEGORY_COUNT = 6;
const RECOMMEND_LIMIT = 6;

// 評価(★)を軸にした「好みの傾向」分析。お気に入りとは独立した評価データを
// 使い、flavorNotesのカテゴリを星の数で重み付け集計してレーダー的な傾向を出し、
// 傾向上位カテゴリに合致する未評価商品をレコメンドする。
export function TasteProfile({ products, getRating, onOpenDetail }) {
  const t = useT();
  const ratedEntries = products
    .map((product) => ({ product, rating: getRating(product.id) }))
    .filter((entry) => entry.rating > 0);

  const categoryScores = computeFlavorPreferenceScores(ratedEntries);
  const topCategoryEns = categoryScores.slice(0, TOP_CATEGORY_COUNT).map((c) => c.category.en);
  const topCategoryLabels = categoryScores.slice(0, TOP_CATEGORY_COUNT).map((c) => c.category.ja);

  const unratedProducts = products.filter((p) => !getRating(p.id));
  const recommendations = recommendByFlavorCategories(unratedProducts, topCategoryEns, RECOMMEND_LIMIT);

  const maxScore = categoryScores[0]?.score ?? 0;

  return (
    <section className="rounded-2xl bg-[var(--c-surface)] border border-[var(--c-border)] p-4 flex flex-col gap-3">
      <div className="flex items-center gap-1.5">
        <Sparkles size={14} className="text-[var(--accent)]" strokeWidth={1.75} />
        <h3 className="text-[14px] font-medium text-[var(--c-text)]">{t("好みの傾向")}</h3>
      </div>

      {ratedEntries.length === 0 ? (
        <p className="text-[12px] text-[var(--c-text-3)]">
          {t("商品詳細で★評価すると、ここに好みの傾向とおすすめが表示されます。")}
        </p>
      ) : (
        <>
          <p className="text-[12px] text-[var(--c-text-3)] leading-relaxed">
            {t("評価した{n}件の商品のフレーバーノートを、星の数を重みにして集計しています。", { n: ratedEntries.length })}
          </p>

          <div className="flex flex-col gap-2">
            {categoryScores.slice(0, SHOWN_CATEGORY_COUNT).map(({ category, score, count }) => (
              <div key={category.en} className="flex items-center gap-2.5">
                <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: category.color }} />
                <span className="text-[12px] text-[var(--c-text)] w-[104px] shrink-0 truncate">{t(category.ja)}</span>
                <div className="flex-1 h-1.5 rounded-full bg-[var(--c-surface-2)] overflow-hidden">
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${maxScore ? (score / maxScore) * 100 : 0}%`,
                      backgroundColor: category.color,
                    }}
                  />
                </div>
                <span className="text-[10px] text-[var(--c-text-3)] w-9 text-right shrink-0">{t("{n}件", { n: count })}</span>
              </div>
            ))}
          </div>

          {recommendations.length > 0 && (
            <div className="mt-2 pt-3 border-t border-[var(--c-border)]">
              <p className="text-[11px] tracking-wide text-[var(--accent-label)] uppercase mb-2">
                {t("{cats}が好きなあなたにおすすめ", { cats: topCategoryLabels.map((l) => t(l)).join(t("・")) })}
              </p>
              <div className="flex flex-col gap-2">
                {recommendations.map((product) => (
                  <button
                    key={product.id}
                    onClick={() => onOpenDetail?.(product)}
                    className="text-left rounded-xl bg-[var(--c-surface-2)] border border-[var(--c-border)] px-3.5 py-2.5 hover:border-[var(--accent)] transition-colors"
                  >
                    <p className="text-[12px] text-[var(--c-text)]">{product.rawName}</p>
                    <div className="flex items-center justify-between gap-2 mt-0.5">
                      <p className="text-[11px] text-[var(--c-text-3)] truncate">{product.shopName}</p>
                      <p className="font-mono text-[11px] text-[var(--c-text-3)] shrink-0">
                        {formatPrice(product) ?? ""}
                      </p>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
