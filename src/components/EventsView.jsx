import { Calendar, MapPin, ExternalLink, Trophy } from "lucide-react";
import { SectionHeading, SourceCredit } from "./common";
import { EVENT_TYPE_LABELS } from "../data/events";
import { JAPAN_COMPETITIONS } from "../data/japanCompetitions";

export function EventCard({ event, onLearnOrigin }) {
  const typeInfo = EVENT_TYPE_LABELS[event.eventType] || { ja: event.eventType, color: "#8B7361" };
  return (
    <div className="rounded-2xl bg-[#2F241A] border border-[#4A3A2A] p-4 flex flex-col gap-2">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-[11px] tracking-[0.1em] text-[var(--accent-label)] uppercase">{event.source}</p>
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
          <Calendar size={12} className="text-[var(--accent-label)] shrink-0" strokeWidth={1.75} />
          <span>{event.dateRange}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <MapPin size={12} className="text-[var(--accent-label)] shrink-0" strokeWidth={1.75} />
          <span>{event.venue}</span>
        </div>
      </div>

      <p className="text-[12px] text-[#8B7361] leading-relaxed border-t border-[#4A3A2A] pt-2">{event.note}</p>

      <div className="flex items-center justify-between pt-1">
        {event.relatedCountry ? (
          <button
            onClick={() => onLearnOrigin(event.relatedCountry)}
            className="text-[11px] text-[var(--accent)] hover:text-[var(--accent-soft)] transition-colors"
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

export function JapanCompetitionCard({ competition }) {
  return (
    <div className="rounded-2xl bg-[#2F241A] border border-[#4A3A2A] p-4 flex flex-col gap-2.5">
      <div className="flex items-center gap-2">
        <span className="shrink-0 text-[11px] px-2 py-0.5 rounded-full bg-[var(--accent)] text-[#231810] font-medium font-mono">
          {competition.abbr}
        </span>
        <h3 className="font-serif text-[16px] text-[#F2E9DD]">{competition.name}</h3>
      </div>
      <p className="text-[13px] text-[var(--accent)]">{competition.tagline}</p>

      <p className="text-[12px] text-[#B8A891] leading-relaxed border-t border-[#4A3A2A] pt-2.5">
        {competition.history}
      </p>
      {competition.format && (
        <p className="text-[12px] text-[#B8A891] leading-relaxed">{competition.format}</p>
      )}
      {competition.latestResult && (
        <p className="text-[12px] text-[#8B7361] leading-relaxed bg-[#3B2211] rounded-lg p-2.5">
          {competition.latestResult}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 pt-1">
        {competition.sources.map((source) => (
          <a
            key={source.url}
            href={source.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-[11px] text-[#8B7361] hover:text-[#B8A891] transition-colors"
          >
            {source.label}
            <ExternalLink size={11} />
          </a>
        ))}
      </div>
    </div>
  );
}

export function EventsView({ hideHeading = false, onLearnOrigin, events }) {
  return (
    <main className="px-5 py-5 flex flex-col gap-3 max-w-xl mx-auto">
      {!hideHeading && <SectionHeading en="Events" ja="イベント" />}
      <p className="text-[13px] text-[#8B7361]">
        世界大会・国内展示会・フェスティバル・国際品評会の開催スケジュールをまとめました。産地に関連するイベントはタップして産地タブへ移動できます。
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
          "Japan Coffee Festival(japancoffeefestival.com)",
        ]}
      />
    </main>
  );
}

export function CompetitionsView({ hideHeading = false }) {
  return (
    <main className="px-5 py-5 flex flex-col gap-3 max-w-xl mx-auto">
      {!hideHeading && <SectionHeading en="Competitions" ja="競技会" />}
      <div className="flex items-center gap-1.5">
        <Trophy size={14} className="text-[var(--accent)]" strokeWidth={1.75} />
        <h3 className="text-[14px] font-medium text-[#F2E9DD]">日本国内の主要競技会(SCAJ主催)</h3>
      </div>
      <p className="text-[13px] text-[#8B7361] -mt-1">
        SCAJ(日本スペシャルティコーヒー協会)が主催する国内競技会9大会。優勝者の多くは世界大会へ日本代表として出場する。
      </p>
      <div className="flex flex-col gap-2.5">
        {JAPAN_COMPETITIONS.map((competition) => (
          <JapanCompetitionCard key={competition.id} competition={competition} />
        ))}
      </div>
    </main>
  );
}
