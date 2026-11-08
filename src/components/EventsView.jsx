import { Calendar, MapPin, ExternalLink, Trophy, Globe2 } from "lucide-react";
import { SectionHeading, SourceCredit } from "./common";
import { EVENT_TYPE_LABELS } from "../data/events";
import { JAPAN_COMPETITIONS } from "../data/japanCompetitions";
import { localizeCompetition, localizeEvent } from "../data/localize";
import { getLang } from "../i18n";
import { useT } from "../i18n";

export function EventCard({ event: rawEvent, onLearnOrigin }) {
  const t = useT();
  const event = localizeEvent(rawEvent);
  const typeInfo = EVENT_TYPE_LABELS[event.eventType] || { ja: event.eventType, color: "var(--c-text-3)" };
  return (
    <div className="rounded-2xl bg-[var(--c-surface)] border border-[var(--c-border)] p-4 flex flex-col gap-2">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-[11px] tracking-[0.1em] text-[var(--accent-label)] uppercase">
            {event.source}
            {event.shopLocationLabel ? ` ・ ${event.shopLocationLabel}` : ""}
          </p>
          <h3 className="font-serif text-[16px] text-[var(--c-text)] mt-0.5">{event.name}</h3>
        </div>
        <span
          className="shrink-0 text-[11px] px-2 py-0.5 rounded-full font-medium"
          style={{ backgroundColor: typeInfo.color, color: "#231810" }}
        >
          {getLang() === "en" && typeInfo.en ? typeInfo.en : typeInfo.ja}
        </span>
      </div>

      <div className="flex flex-col gap-1 text-[12px] text-[var(--c-text-2)]">
        <div className="flex items-center gap-1.5">
          <Calendar size={12} className="text-[var(--accent-label)] shrink-0" strokeWidth={1.75} />
          <span>{event.dateRange}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <MapPin size={12} className="text-[var(--accent-label)] shrink-0" strokeWidth={1.75} />
          <span>{event.venue}</span>
        </div>
      </div>

      <p className="text-[12px] text-[var(--c-text-3)] leading-relaxed border-t border-[var(--c-border)] pt-2">{event.note}</p>

      <div className="flex items-center justify-between pt-1">
        {event.relatedCountry && event.relatedCountry !== "日本" ? (
          <button
            onClick={() => onLearnOrigin(event.relatedCountry)}
            className="text-[11px] text-[var(--accent)] hover:text-[var(--accent-soft)] transition-colors"
          >
            {t("産地タブで{country}を見る →", { country: t(event.relatedCountry) })}
          </button>
        ) : (
          <span />
        )}
        <a
          href={event.sourceUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1 text-[11px] text-[var(--c-text-3)] hover:text-[var(--c-text-2)] transition-colors"
        >
          {t("公式サイト")}
          <ExternalLink size={11} />
        </a>
      </div>
    </div>
  );
}

export function JapanCompetitionCard({ competition: rawCompetition }) {
  const competition = localizeCompetition(rawCompetition);
  return (
    <div className="rounded-2xl bg-[var(--c-surface)] border border-[var(--c-border)] p-4 flex flex-col gap-2.5">
      <div className="flex items-center gap-2">
        <span className="shrink-0 text-[11px] px-2 py-0.5 rounded-full bg-[var(--accent)] text-[var(--on-accent)] font-medium font-mono">
          {competition.abbr}
        </span>
        <h3 className="font-serif text-[16px] text-[var(--c-text)]">{competition.name}</h3>
      </div>
      <p className="text-[13px] text-[var(--accent)]">{competition.tagline}</p>

      <p className="text-[12px] text-[var(--c-text-2)] leading-relaxed border-t border-[var(--c-border)] pt-2.5">
        {competition.history}
      </p>
      {competition.format && (
        <p className="text-[12px] text-[var(--c-text-2)] leading-relaxed">{competition.format}</p>
      )}
      {competition.latestResult && (
        <p className="text-[12px] text-[var(--c-text-3)] leading-relaxed bg-[var(--c-surface-2)] rounded-lg p-2.5">
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
            className="flex items-center gap-1 text-[11px] text-[var(--c-text-3)] hover:text-[var(--c-text-2)] transition-colors"
          >
            {source.label}
            <ExternalLink size={11} />
          </a>
        ))}
      </div>
    </div>
  );
}

// WCC(World Coffee Championships)の1大会分。開催済み(優勝者情報あり)かどうかを
// event.note(優勝者テキストが入っていれば開催済み)の有無で判定し、バッジで
// 明示的に区別する。
export function WorldChampionshipCard({ event: rawEvent }) {
  const t = useT();
  const event = localizeEvent(rawEvent);
  const concluded = Boolean(event.note);
  return (
    <div className="rounded-2xl bg-[var(--c-surface)] border border-[var(--c-border)] p-4 flex flex-col gap-2">
      <div className="flex items-start justify-between gap-2">
        <h4 className="font-serif text-[15px] text-[var(--c-text)]">{event.name}</h4>
        <span
          className={`shrink-0 text-[11px] px-2 py-0.5 rounded-full font-medium ${
            concluded
              ? "bg-[var(--c-surface-2)] text-[var(--c-text-3)] border border-[var(--c-border)]"
              : "bg-[var(--accent)] text-[var(--on-accent)]"
          }`}
        >
          {concluded ? t("開催済み") : t("開催予定")}
        </span>
      </div>
      <div className="flex flex-col gap-1 text-[12px] text-[var(--c-text-2)]">
        <div className="flex items-center gap-1.5">
          <Calendar size={12} className="text-[var(--accent-label)] shrink-0" strokeWidth={1.75} />
          <span>{event.dateRange}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <MapPin size={12} className="text-[var(--accent-label)] shrink-0" strokeWidth={1.75} />
          <span>{event.venue}</span>
        </div>
      </div>
      {event.note && (
        <p className="text-[12px] text-[var(--c-text-3)] leading-relaxed border-t border-[var(--c-border)] pt-2">{event.note}</p>
      )}
      <a
        href={event.sourceUrl}
        target="_blank"
        rel="noopener noreferrer"
        className="self-end flex items-center gap-1 text-[11px] text-[var(--c-text-3)] hover:text-[var(--c-text-2)] transition-colors"
      >
        {t("公式サイト")}
        <ExternalLink size={11} />
      </a>
    </div>
  );
}

export function EventsView({ hideHeading = false, onLearnOrigin, events }) {
  const t = useT();
  // WCC(世界大会)は「競技会」タブの世界大会セクションに表示するため、
  // ここでは展示会・オークション・フェスティバル等のスケジュールのみを扱う
  const scheduleEvents = events.filter((event) => event.sourceId !== "wcc");

  return (
    <main className="px-5 py-5 flex flex-col gap-3 max-w-xl mx-auto">
      {!hideHeading && <SectionHeading en="Events" ja="イベント" />}
      <p className="text-[13px] text-[var(--c-text-3)]">
        {t("国内展示会・フェスティバル・国際品評会の開催スケジュールをまとめました。世界大会(WCC)は競技会タブでご覧いただけます。産地に関連するイベントはタップして産地タブへ移動できます。")}
      </p>
      {getLang() === "en" && (
        <p className="text-[11px] text-[var(--c-text-3)] leading-relaxed -mt-1">
          {t("イベントの名称・会場・説明は、主催者が掲載した内容のまま表示しています(日本語のものがあります)。")}
        </p>
      )}
      <div className="flex flex-col gap-2.5">
        {scheduleEvents.map((event) => (
          <EventCard key={event.id ?? event.name} event={event} onLearnOrigin={onLearnOrigin} />
        ))}
      </div>
      <SourceCredit
        sources={[
          "SCAJ(scajconference.jp)",
          "ACE / Cup of Excellence(cupofexcellence.org)",
          "Japan Coffee Festival(japancoffeefestival.com)",
          "TOKYO COFFEE FESTIVAL(tokyocoffeefestival.co)",
          "NAGOYA COFFEE FES.(nagoyacoffeefes.com)",
          t("珈琲博覧日(onedaycoffeeexpo.com)"),
          "COFFEE CITY FESTIVAL(coffee-city-fes.com)",
          "27 COFFEE ROASTERS(27coffee.jp)",
          "Roast Design Coffee(roast-design-coffee.com)",
          "COFFEE ROASTERY MEGURO(roasterymeguro.com)",
        ]}
      />
    </main>
  );
}

export function CompetitionsView({ hideHeading = false, events = [] }) {
  const t = useT();
  const worldChampionships = [...events]
    .filter((event) => event.sourceId === "wcc")
    .sort((a, b) => (a.startDate || "9999-99-99").localeCompare(b.startDate || "9999-99-99"));

  return (
    <main className="px-5 py-5 flex flex-col gap-4 max-w-xl mx-auto">
      {!hideHeading && <SectionHeading en="Competitions" ja="競技会" />}

      {worldChampionships.length > 0 && (
        <div className="flex flex-col gap-2.5">
          <div className="flex items-center gap-1.5">
            <Globe2 size={14} className="text-[var(--accent)]" strokeWidth={1.75} />
            <h3 className="text-[14px] font-medium text-[var(--c-text)]">{t("世界大会(WCC)")}</h3>
          </div>
          <p className="text-[13px] text-[var(--c-text-3)] -mt-1">
            {t("World Coffee Championshipsが年間を通じて世界各地で開催する大会。開催日順に並んでいます。")}
          </p>
          <div className="flex flex-col gap-2.5">
            {worldChampionships.map((event) => (
              <WorldChampionshipCard key={event.id ?? event.name} event={event} />
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-col gap-2.5 pt-2 border-t border-[var(--c-border)]">
        <div className="flex items-center gap-1.5">
          <Trophy size={14} className="text-[var(--accent)]" strokeWidth={1.75} />
          <h3 className="text-[14px] font-medium text-[var(--c-text)]">{t("日本国内の主要競技会(SCAJ主催)")}</h3>
        </div>
        <p className="text-[13px] text-[var(--c-text-3)] -mt-1">
          {t("SCAJ(日本スペシャルティコーヒー協会)が主催する国内競技会9大会。優勝者の多くは世界大会へ日本代表として出場する。")}
        </p>
        <div className="flex flex-col gap-2.5">
          {JAPAN_COMPETITIONS.map((competition) => (
            <JapanCompetitionCard key={competition.id} competition={competition} />
          ))}
        </div>
      </div>
    </main>
  );
}
