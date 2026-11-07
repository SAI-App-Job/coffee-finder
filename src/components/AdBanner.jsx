import { Megaphone } from "lucide-react";
import { useT } from "../i18n";

// 広告SDK(AdMob等)は未統合。TWAパッケージング確定後にネイティブ広告SDKへ
// 差し替える前提の、表示位置・非表示条件だけを検証するためのプレースホルダー。
// 表示位置はページ最上部(ヘッダーの上)で、固定せずスクロールで流れる(App.jsx)。
// 下部メニューの誤タップを避けるため、下部には置かない。ここでは中身のスタイルのみを持つ。
export function AdBannerPlaceholder() {
  const t = useT();
  return (
    <div className="max-w-xl mx-auto px-5 pt-3 pb-1">
      <div className="h-[50px] rounded-lg border border-dashed border-[var(--c-border)] flex items-center justify-center gap-2 text-[var(--c-text-3)]">
        <Megaphone size={13} strokeWidth={1.75} />
        <span className="text-[11px]">{t("広告スペース(プレースホルダー)")}</span>
      </div>
    </div>
  );
}
