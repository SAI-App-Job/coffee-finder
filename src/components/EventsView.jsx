import { Calendar, MapPin, ExternalLink } from "lucide-react";
import { SectionHeading, SourceCredit } from "./common";
import { EVENT_TYPE_LABELS } from "../data/events";

export function EventCard({ event, onLearnOrigin }) {
  const typeInfo = EVENT_TYPE_LABELS[event.eventType] || { ja: event.eventType, color: "#8B7361" };
  return (
    <div className="rounded-2xl bg-[#2F241A] border border-[#4A3A2A] p-4 flex flex-col gap-2">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-[11px] tracking-[0.1em] text-[#8B5E2E] uppercase">{event.source}</p>
          <h3 className="font-serif text-[16px] text-[#F2E9DD] mt-0.5">{event.name}</h3>
        </div>
        <span
          className="shrink-0 text-[11px] px-2 py-0.5 rounded-full font-medium"
          style={{ backgroundColor: typeInfo.color, color: "#231810" }}
        >
          {typeInfo.ja}
        </span>
      </div>

      <div className="flex flex-col gap-1 text-[12px] text-[#B8A891]">
        <div className="flex items-center gap-1.5">
          <Calendar size={12} className="text-[#8B5E2E] shrink-0" strokeWidth={1.75} />
          <span>{event.dateRange}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <MapPin size={12} className="text-[#8B5E2E] shrink-0" strokeWidth={1.75} />
          <span>{event.venue}</span>
        </div>
      </div>

      <p className="text-[12px] text-[#8B7361] leading-relaxed border-t border-[#4A3A2A] pt-2">{event.note}</p>

      <div className="flex items-center justify-between pt-1">
        {event.relatedCountry ? (
          <button
            onClick={() => onLearnOrigin(event.relatedCountry)}
            className="text-[11px] text-[#D4A24E] hover:text-[#E8C89A] transition-colors"
          >
            産地タブで{event.relatedCountry}を見る →
          </button>
        ) : (
          <span />
        )}
        <a
          href={event.sourceUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1 text-[11px] text-[#8B7361] hover:text-[#B8A891] transition-colors"
        >
          公式サイト
          <ExternalLink size={11} />
        </a>
      </div>
    </div>
  );
}

export function EventsView({ hideHeading = false, onLearnOrigin, events }) {
  return (
    <main className="px-5 py-5 flex flex-col gap-3 max-w-xl mx-auto">
      {!hideHeading && <SectionHeading en="Competitions & Events" ja="大会・イベント" />}
      <p className="text-[13px] text-[#8B7361]">
        世界大会・国内展示会・国際品評会の開催情報をまとめました。産地に関連するイベントはタップして産地タブへ移動できます。
      </p>
      <div className="flex flex-col gap-2.5">
        {events.map((event) => (
          <EventCard key={event.name} event={event} onLearnOrigin={onLearnOrigin} />
        ))}
      </div>
      <SourceCredit
        sources={[
          "WCC(World Coffee Championships、wcc.coffee)",
          "SCAJ(scajconference.jp)",
          "ACE / Cup of Excellence(cupofexcellence.org)",
        ]}
      />
    </main>
  );
}
