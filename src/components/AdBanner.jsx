import { Megaphone } from "lucide-react";

// 広告SDK(AdMob等)は未統合。TWAパッケージング確定後にネイティブ広告SDKへ
// 差し替える前提の、表示位置・非表示条件だけを検証するためのプレースホルダー。
// 位置固定(fixed)は呼び出し側(App.jsx)の共通下部バーが担うため、ここでは
// 中身のスタイルのみを持つ。
export function AdBannerPlaceholder() {
  return (
    <div className="max-w-xl mx-auto px-5 py-2">
      <div className="h-[50px] rounded-lg border border-dashed border-[#4A3A2A] flex items-center justify-center gap-2 text-[#8B7361]">
        <Megaphone size={13} strokeWidth={1.75} />
        <span className="text-[11px]">広告スペース(プレースホルダー)</span>
      </div>
    </div>
  );
}
