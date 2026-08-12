import { MapPin, X } from "lucide-react";

export function SectionHeading({ en, ja, className = "" }) {
  return (
    <div className={className}>
      <p className="text-[11px] tracking-[0.2em] text-[var(--accent-label)] uppercase">{en}</p>
      <h2 className="font-serif text-[22px] leading-tight text-[#F2E9DD] mt-1">{ja}</h2>
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
