import { Award } from "lucide-react";
import { ACHIEVEMENT_ICONS } from "./achievementIcons";
import { SectionHeading } from "./common";
import { ACHIEVEMENT_GROUPS, achievementParams } from "../utils/achievements";
import { PREFECTURE_REGIONS } from "../data/prefectures";
import { getLang, getLocale, useT } from "../i18n";


const formatEarned = (iso) =>
  new Date(iso).toLocaleDateString(getLocale(), { year: "numeric", month: "2-digit", day: "2-digit" });

function Badge({ item }) {
  const t = useT();
  const Icon = ACHIEVEMENT_ICONS[item.icon] ?? Award;
  const earned = Boolean(item.earnedAt);
  const params = achievementParams(item);
  return (
    <div
      className={`rounded-xl border p-3 flex flex-col gap-2 ${
        earned ? "bg-[var(--c-surface)] border-[var(--accent)]" : "bg-[var(--c-surface)] border-[var(--c-border)]"
      }`}
    >
      <div className="flex items-start gap-2.5">
        <span
          className={`shrink-0 w-9 h-9 rounded-full flex items-center justify-center border ${
            earned
              ? "bg-[var(--accent)] text-[var(--on-accent)] border-[var(--accent)]"
              : "bg-[var(--c-surface-2)] text-[var(--c-text-3)] border-[var(--c-border)]"
          }`}
        >
          <Icon size={16} strokeWidth={1.9} />
        </span>
        <div className="min-w-0">
          <p className={`text-[13px] font-medium leading-snug ${earned ? "text-[var(--c-text)]" : "text-[var(--c-text-2)]"}`}>
            {t(item.title, params)}
          </p>
          <p className="text-[11px] text-[var(--c-text-3)] leading-snug mt-0.5">{t(item.desc, params)}</p>
        </div>
      </div>
      {earned ? (
        <p className="text-[11px] text-[var(--accent)] font-medium">
          {t("獲得: {date}", { date: formatEarned(item.earnedAt) })}
        </p>
      ) : (
        <div className="flex items-center gap-2">
          <div className="flex-1 h-1.5 rounded-full bg-[var(--c-surface-2)] overflow-hidden">
            <div
              className="h-full rounded-full bg-[var(--accent-label)]"
              style={{ width: `${Math.round((item.progress / item.goal) * 100)}%` }}
            />
          </div>
          <span className="font-mono text-[11px] text-[var(--c-text-3)]">
            {item.progress}/{item.goal}
          </span>
        </div>
      )}
    </div>
  );
}

// 都道府県スタンプ。お店を訪れた(商品登録・テイスティングノートのある)都道府県が色づく。
function PrefectureStamps({ visited }) {
  const t = useT();
  return (
    <div className="rounded-2xl bg-[var(--c-surface)] border border-[var(--c-border)] p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <p className="text-[13px] font-medium text-[var(--c-text)]">{t("都道府県スタンプ")}</p>
        <span className="font-mono text-[12px] text-[var(--accent)]">{visited.size}/47</span>
      </div>
      {PREFECTURE_REGIONS.map((region) => (
        <div key={region.id}>
          <p className="text-[11px] text-[var(--c-text-3)] mb-1.5">{getLang() === "en" ? region.en : region.name}</p>
          <div className="flex flex-wrap gap-1.5">
            {region.prefectures.map((pref) => {
              const on = visited.has(pref);
              return (
                <span
                  key={pref}
                  className={`text-[11px] px-2 py-0.5 rounded-full border ${
                    on
                      ? "bg-[var(--accent)] text-[var(--on-accent)] border-[var(--accent)] font-medium"
                      : "text-[var(--c-text-3)] border-dashed border-[var(--c-border)]"
                  }`}
                >
                  {t(pref)}
                </span>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

// 「実績」。記録に応じて獲得するバッジ(チャレンジ)と、都道府県スタンプ。
export function AchievementsView({ items, earnedCount, visitedPrefectures }) {
  const t = useT();
  return (
    <main className="px-5 py-5 flex flex-col gap-5 max-w-xl mx-auto">
      <SectionHeading en="Achievements" ja="実績" />

      <section className="rounded-2xl bg-[var(--c-surface)] border border-[var(--c-border)] p-4 flex flex-col gap-2">
        <div className="flex items-end justify-between">
          <p className="text-[12px] text-[var(--c-text-3)]">{t("獲得した実績")}</p>
          <p className="font-mono text-[var(--c-text)]">
            <span className="text-[22px] text-[var(--accent)] font-semibold">{earnedCount}</span>
            <span className="text-[13px] text-[var(--c-text-3)]"> / {items.length}</span>
          </p>
        </div>
        <div className="h-1.5 rounded-full bg-[var(--c-surface-2)] overflow-hidden">
          <div
            className="h-full rounded-full bg-[var(--accent)]"
            style={{ width: `${items.length ? Math.round((earnedCount / items.length) * 100) : 0}%` }}
          />
        </div>
        <p className="text-[11px] text-[var(--c-text-3)] leading-relaxed">
          {t("ログ・ノート・商品登録・写真などの記録から、自動で獲得します。サンプルのデータは含まれません。獲得した実績は、記録を消しても残ります。")}
        </p>
      </section>

      {ACHIEVEMENT_GROUPS.map((group) => {
        const groupItems = items.filter((item) => item.group === group.id);
        return (
          <section key={group.id} className="flex flex-col gap-2.5">
            <div className="flex items-center justify-between">
              <h3 className="text-[14px] font-medium text-[var(--c-text)]">{t(group.title)}</h3>
              <span className="font-mono text-[11px] text-[var(--c-text-3)]">
                {groupItems.filter((i) => i.earnedAt).length}/{groupItems.length}
              </span>
            </div>
            {group.id === "prefecture" && <PrefectureStamps visited={visitedPrefectures} />}
            <div className="grid grid-cols-2 gap-2.5">
              {groupItems.map((item) => (
                <Badge key={item.id} item={item} />
              ))}
            </div>
          </section>
        );
      })}
    </main>
  );
}
