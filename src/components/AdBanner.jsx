import { Megaphone } from "lucide-react";

// 広告SDK(AdMob等)は未統合。TWAパッケージング確定後にネイティブ広告SDKへ
// 差し替える前提の、表示位置・非表示条件だけを検証するためのプレースホルダー。
export function AdBannerPlaceholder() {
  return (
    <div className="fixed bottom-0 inset-x-0 z-20 bg-[#1C140D]/95 backdrop-blur-sm border-t border-[#4A3A2A]">
      <div className="max-w-xl mx-auto px-5 py-2">
        <div className="h-[50px] rounded-lg border border-dashed border-[#4A3A2A] flex items-center justify-center gap-2 text-[#8B7361]">
          <Megaphone size={13} strokeWidth={1.75} />
          <span className="text-[11px]">広告スペース(プレースホルダー)</span>
        </div>
      </div>
    </div>
  );
}
