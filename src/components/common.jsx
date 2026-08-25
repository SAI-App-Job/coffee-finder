import { MapPin, Star, X } from "lucide-react";

export function SectionHeading({ en, ja, className = "" }) {
  return (
    <div className={className}>
      <p className="text-[11px] tracking-[0.2em] text-[var(--accent-label)] uppercase">{en}</p>
      <h2 className="font-serif text-[22px] leading-tight text-[#F2E9DD] mt-1">{ja}</h2>
    </div>
  );
}

export function Toast({ message, onDismiss }) {
  if (!message) return null;
  return (
    <div className="fixed top-3 inset-x-0 z-50 flex justify-center px-5 pointer-events-none">
      <div className="pointer-events-auto max-w-xl w-full flex items-center gap-3 bg-[#100b07] border border-[var(--accent)] rounded-xl px-4 py-3 shadow-[0_8px_24px_rgba(0,0,0,0.55)]">
        <p className="text-[13px] text-[#F2E9DD] leading-snug flex-1">{message}</p>
        <button
          onClick={onDismiss}
          className="text-[#8B7361] hover:text-[#F2E9DD] transition-colors shrink-0"
          aria-label="閉じる"
        >
          <X size={14} />
        </button>
      </div>
    </div>
  );
}

export function StarRating({ value = 0, onChange, size = 20, readOnly = false }) {
  return (
    <div className="flex items-center gap-1">
      {[1, 2, 3, 4, 5].map((star) => (
        <button
          key={star}
          type="button"
          disabled={readOnly}
          onClick={(e) => {
            e.stopPropagation();
            onChange?.(star === value ? 0 : star);
          }}
          aria-label={`${star}つ星`}
          aria-pressed={star <= value}
          className={readOnly ? "cursor-default" : "p-0.5 -m-0.5"}
        >
          <Star
            size={size}
            strokeWidth={1.75}
            className={star <= value ? "fill-[var(--accent)] text-[var(--accent)]" : "text-[#8B7361]"}
          />
        </button>
      ))}
    </div>
  );
}

// Dial-in Score(0〜100)を半円のアークゲージで表示する。読み取り専用表示にも、
// スライダー入力のライブプレビューにも同じコンポーネントを使う。
export function DialInGauge({ value = 0, size = 120 }) {
  const clamped = Math.max(0, Math.min(100, value));
  const strokeWidth = 10;
  const radius = size / 2 - strokeWidth;
  const center = size / 2;
  const circumference = Math.PI * radius;
  const offset = circumference * (1 - clamped / 100);
  const arcPath = `M ${strokeWidth} ${center} A ${radius} ${radius} 0 0 1 ${size - strokeWidth} ${center}`;

  return (
    <svg width={size} height={size / 2 + strokeWidth} viewBox={`0 0 ${size} ${size / 2 + strokeWidth}`}>
      <path d={arcPath} fill="none" stroke="#3B2211" strokeWidth={strokeWidth} strokeLinecap="round" />
      <path
        d={arcPath}
        fill="none"
        stroke="var(--accent)"
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        style={{ transition: "stroke-dashoffset 0.2s ease" }}
      />
      <text x={center} y={center - 4} textAnchor="middle" fontSize="20" fontWeight="600" fill="#F2E9DD">
        {clamped}
      </text>
      <text x={center} y={center + 12} textAnchor="middle" fontSize="9" fill="#8B7361">
        / 100
      </text>
    </svg>
  );
}

// 広告の表示有無(プレミアム会員かどうか)とは無関係に、常時表示する著作権表示。
// 無断複製・再配布を禁じる旨をLICENSEで定めているため、アプリ内でも権利者を
// 明示しておく。
export function CopyrightFooter() {
  return (
    <div className="max-w-xl mx-auto w-full px-5 py-1.5 border-t border-[#4A3A2A]">
      <p className="text-[10px] text-[#8B7361] text-center">
        © 2026 SAI. All Rights Reserved.
      </p>
    </div>
  );
}

export function SourceCredit({ sources }) {
  return (
    <div className="mt-2 pt-3 border-t border-[#4A3A2A]">
      <p className="text-[11px] text-[#8B7361] leading-relaxed">
        出典: {sources.join(" / ")}
      </p>
    </div>
  );
}

export function MapLinkModal({ target, onClose }) {
  if (!target) return null;
  const mapUrl = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(
    target.mapQuery
  )}`;
  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full sm:w-[380px] bg-[#2F241A] border border-[#4A3A2A] rounded-t-2xl sm:rounded-2xl p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between mb-3">
          <div>
            <p className="text-[11px] text-[var(--accent-label)] uppercase tracking-wider">店舗へ行く</p>
            <h4 className="font-serif text-[18px] text-[#F2E9DD] mt-0.5">{target.shopName}</h4>
            <p className="text-[13px] text-[#8B7361] mt-0.5">{target.shopAddress}</p>
          </div>
          <button
            onClick={onClose}
            className="text-[#8B7361] hover:text-[#F2E9DD] transition-colors min-w-[44px] min-h-[44px] flex items-center justify-center -m-2.5"
            aria-label="閉じる"
          >
            <X size={18} />
          </button>
        </div>
        <a
          href={mapUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center justify-center gap-2 w-full py-3 rounded-xl bg-[var(--accent)] text-[#231810] font-medium text-[14px] hover:bg-[var(--accent-soft)] transition-colors"
        >
          <MapPin size={16} strokeWidth={2} />
          Googleマップで開く
        </a>
      </div>
    </div>
  );
}
