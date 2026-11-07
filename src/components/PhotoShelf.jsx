import { Frame } from "lucide-react";
import { useT } from "../i18n";

const PER_ROW = 3;

// 「ディスプレイ」。パッケージ写真のある豆を、棚に並べるように見せる。押すと、その豆の記録(ログ・詳細)を開く。
// items: { id, name, url, rating }[](新しい写真が先頭)、onOpen: 豆を押したとき
export function PhotoShelf({ items, onOpen }) {
  const t = useT();
  if (items.length === 0) {
    return (
      <div className="text-center py-14 px-5 text-[var(--c-text-3)]">
        <Frame size={28} className="mx-auto mb-3 opacity-40" />
        <p className="text-[14px]">{t("まだ飾る豆がありません")}</p>
        <p className="text-[12px] mt-1 leading-relaxed">
          {t("商品の登録や、商品詳細から、パッケージ写真を追加すると、ここに棚のように並びます")}
        </p>
      </div>
    );
  }

  const rows = [];
  for (let i = 0; i < items.length; i += PER_ROW) rows.push(items.slice(i, i + PER_ROW));

  return (
    <div className="px-5 py-5 flex flex-col gap-1">
      <p className="text-[12px] text-[var(--c-text-3)] mb-2">{t("写真のある豆 {n}件", { n: items.length })}</p>
      {rows.map((row, rowIndex) => (
        <div key={rowIndex} className="mb-4">
          <div className="grid grid-cols-3 gap-3 px-1 items-end">
            {row.map((item) => (
              <button
                key={item.id}
                onClick={() => onOpen(item)}
                aria-label={item.name}
                className="block aspect-[3/4] rounded-t-md overflow-hidden bg-[var(--c-surface-2)] shadow-[0_-2px_10px_rgba(0,0,0,0.35)] active:scale-[0.97] transition-transform"
              >
                <img src={item.url} alt={t("{name}のパッケージ写真", { name: item.name })} className="w-full h-full object-cover" />
              </button>
            ))}
          </div>
          {/* 棚板 */}
          <div className="h-2.5 rounded-sm bg-gradient-to-b from-[var(--c-border)] to-[var(--c-surface-2)] shadow-[0_6px_8px_-5px_rgba(0,0,0,0.5)]" />
          <div className="grid grid-cols-3 gap-3 px-1 mt-1.5">
            {row.map((item) => (
              <div key={item.id} className="min-w-0">
                <p className="text-[11px] text-[var(--c-text-2)] leading-snug line-clamp-2">{item.name}</p>
                {item.rating > 0 && <p className="text-[10px] text-[var(--accent)] mt-0.5">★{item.rating}</p>}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
