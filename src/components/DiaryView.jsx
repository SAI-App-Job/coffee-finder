import { useMemo, useState } from "react";
import { Award, BookOpenText, Camera, ChevronRight, Flame, NotebookPen, PackagePlus, PenLine } from "lucide-react";
import { SectionHeading } from "./common";
import { HistoryView } from "./HistoryView";
import { ACHIEVEMENT_ICONS } from "./achievementIcons";
import { countByPeriod, groupByDay, localDateKey, PERIODS } from "../utils/diary";
import { achievementParams, currentStreak, nextGoals } from "../utils/achievements";
import { getLocale, useT } from "../i18n";

const KIND_META = {
  log: { icon: NotebookPen, label: "テイスティングログ" },
  note: { icon: PenLine, label: "テイスティングノート" },
  register: { icon: PackagePlus, label: "商品登録" },
  photo: { icon: Camera, label: "パッケージ写真" },
};
const KINDS = ["log", "note", "register", "photo"];
const PERIOD_LABEL = { week: "今週", month: "今月", year: "今年" };
const DAY_GROUPS_STEP = 7;

// 「コーヒー日記」。今週・今月・今年に、ログ・ノート・商品登録・写真をいくつ記録したかと、
// 日付ごとの記録の流れ(タイムライン)を見られる。
// events: buildDiaryEvents の結果(サンプルは含まない)、onOpenLog: ログの行を押したときに、その商品のログを開く
// history: 閲覧履歴(見た商品)。「閲覧履歴」タブに表示する(記録の件数・実績には含めない)
// achievements: useAchievements の結果(items・earnedCount)、onOpenAchievements: 実績の画面を開く
export function DiaryView({ events, onOpenLog, history, achievements, onOpenAchievements }) {
  const t = useT();
  const [view, setView] = useState("records");
  const [dayGroupCount, setDayGroupCount] = useState(DAY_GROUPS_STEP);
  // 表示した時点の日時で、今週・今月・今年を決める(記録が増えたら数え直す)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const now = useMemo(() => new Date(), [events]);
  const counts = useMemo(() => countByPeriod(events, now), [events, now]);
  const groups = useMemo(() => groupByDay(events.filter((e) => e.t <= now.getTime())), [events, now]);
  const streak = useMemo(() => currentStreak(events, now), [events, now]);
  const goals = useMemo(() => nextGoals(achievements.items, 3), [achievements.items]);
  const streakGoal = achievements.items.filter((i) => i.rule.type === "streak" && !i.earnedAt).sort((a, b) => a.goal - b.goal)[0];
  // 日付ごとの、その日に獲得した実績
  const earnedByDay = useMemo(() => {
    const map = new Map();
    for (const item of achievements.items) {
      if (!item.earnedAt) continue;
      const key = localDateKey(Date.parse(item.earnedAt));
      map.set(key, [...(map.get(key) ?? []), item]);
    }
    return map;
  }, [achievements.items]);
  const dayFormat = new Intl.DateTimeFormat(getLocale(), { month: "numeric", day: "numeric", weekday: "short" });
  const timeFormat = new Intl.DateTimeFormat(getLocale(), { hour: "2-digit", minute: "2-digit" });

  return (
    <main className="px-5 py-5 flex flex-col gap-4 max-w-xl mx-auto">
      <SectionHeading en="Diary" ja="コーヒー日記" />

      <div className="grid grid-cols-2 gap-1 p-1 rounded-full bg-[var(--c-surface-2)]">
        {[
          { id: "records", label: "記録" },
          { id: "viewed", label: "閲覧履歴" },
        ].map(({ id, label }) => (
          <button
            key={id}
            onClick={() => setView(id)}
            aria-pressed={view === id}
            className={`py-2 rounded-full text-[12px] font-medium transition-colors ${
              view === id ? "bg-[var(--accent)] text-[var(--on-accent)]" : "text-[var(--c-text-2)]"
            }`}
          >
            {t(label)}
          </button>
        ))}
      </div>

      {view === "viewed" ? (
        <HistoryView historyItems={history.items} isPremium={history.isPremium} onOpenDetail={history.onOpenDetail} />
      ) : (
        <>

      <section className="rounded-2xl bg-[var(--c-surface)] border border-[var(--c-border)] p-4 flex flex-col gap-3">
        <div className="grid grid-cols-[1fr_repeat(3,3.25rem)] items-center gap-x-2 gap-y-2.5">
          <span />
          {PERIODS.map((period) => (
            <span key={period} className="text-[11px] text-[var(--accent-label)] text-center font-medium">
              {t(PERIOD_LABEL[period])}
            </span>
          ))}
          {KINDS.map((kind) => {
            const { icon: Icon, label } = KIND_META[kind];
            return (
              <div key={kind} className="contents">
                <span className="flex items-center gap-1.5 text-[12px] text-[var(--c-text-2)] min-w-0">
                  <Icon size={13} strokeWidth={1.75} className="shrink-0 text-[var(--accent)]" />
                  <span className="truncate">{t(label)}</span>
                </span>
                {PERIODS.map((period) => (
                  <span key={period} className="font-mono text-[15px] text-[var(--c-text)] text-center">
                    {counts[period][kind]}
                  </span>
                ))}
              </div>
            );
          })}
          <span className="text-[12px] font-medium text-[var(--c-text)] border-t border-[var(--c-border)] pt-2.5">
            {t("合計")}
          </span>
          {PERIODS.map((period) => (
            <span
              key={period}
              className="font-mono text-[17px] font-semibold text-[var(--accent)] text-center border-t border-[var(--c-border)] pt-2"
            >
              {counts[period].total}
            </span>
          ))}
        </div>
        <p className="text-[11px] text-[var(--c-text-3)] leading-relaxed">
          {t("今週は月曜日から数えます。サンプルのデータは、集計に含まれません。")}
        </p>
      </section>

      <section className="rounded-2xl bg-[var(--c-surface)] border border-[var(--c-border)] p-4 flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <p className="text-[13px] font-medium text-[var(--c-text)]">{t("実績")}</p>
          <button onClick={onOpenAchievements} className="flex items-center gap-0.5 text-[12px] text-[var(--accent)]">
            {t("実績を見る")}
            <ChevronRight size={13} />
          </button>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-xl bg-[var(--c-surface-2)] px-3 py-2.5">
            <p className="flex items-center gap-1 text-[11px] text-[var(--c-text-3)]">
              <Award size={12} className="text-[var(--accent)]" />
              {t("獲得した実績")}
            </p>
            <p className="font-mono mt-0.5">
              <span className="text-[20px] font-semibold text-[var(--accent)]">{achievements.earnedCount}</span>
              <span className="text-[12px] text-[var(--c-text-3)]"> / {achievements.items.length}</span>
            </p>
          </div>
          <div className="rounded-xl bg-[var(--c-surface-2)] px-3 py-2.5">
            <p className="flex items-center gap-1 text-[11px] text-[var(--c-text-3)]">
              <Flame size={12} className="text-[var(--accent)]" />
              {t("連続で記録")}
            </p>
            <p className="font-mono mt-0.5">
              <span className="text-[20px] font-semibold text-[var(--accent)]">{streak}</span>
              <span className="text-[12px] text-[var(--c-text-3)]"> {t("日")}</span>
            </p>
            {streakGoal && (
              <p className="text-[10px] text-[var(--c-text-3)] mt-0.5">
                {t("{n}日連続まで、あと{rest}日", { n: streakGoal.goal, rest: Math.max(streakGoal.goal - streak, 0) })}
              </p>
            )}
          </div>
        </div>
        {goals.length > 0 && (
          <div className="flex flex-col gap-2">
            <p className="text-[11px] text-[var(--c-text-3)]">{t("次の目標")}</p>
            {goals.map((item) => {
              const Icon = ACHIEVEMENT_ICONS[item.icon] ?? Award;
              return (
                <button key={item.id} onClick={onOpenAchievements} className="flex items-center gap-2.5 text-left">
                  <span className="shrink-0 w-7 h-7 rounded-full bg-[var(--c-surface-2)] border border-[var(--c-border)] flex items-center justify-center text-[var(--c-text-3)]">
                    <Icon size={13} strokeWidth={1.9} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-[12px] text-[var(--c-text)] truncate">{t(item.title, achievementParams(item))}</span>
                    <span className="flex items-center gap-2 mt-1">
                      <span className="flex-1 h-1.5 rounded-full bg-[var(--c-surface-2)] overflow-hidden">
                        <span
                          className="block h-full rounded-full bg-[var(--accent-label)]"
                          style={{ width: `${Math.round((item.progress / item.goal) * 100)}%` }}
                        />
                      </span>
                      <span className="font-mono text-[11px] text-[var(--c-text-3)]">
                        {item.progress}/{item.goal}
                      </span>
                    </span>
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </section>

      {groups.length === 0 ? (
        <div className="text-center py-12 text-[var(--c-text-3)]">
          <BookOpenText size={28} className="mx-auto mb-3 opacity-40" />
          <p className="text-[14px]">{t("まだ記録がありません")}</p>
          <p className="text-[12px] mt-1 leading-relaxed">
            {t("テイスティングログ・ノート、商品の登録、パッケージ写真を追加すると、ここに日記として並びます")}
          </p>
        </div>
      ) : (
        <section className="flex flex-col gap-4">
          <p className="text-[12px] text-[var(--c-text-3)]">{t("最近の記録")}</p>
          {groups.slice(0, dayGroupCount).map((group) => (
            <div key={group.key} className="flex flex-col gap-2">
              <p className="text-[12px] font-medium text-[var(--accent-label)]">{dayFormat.format(group.t)}</p>
              {(earnedByDay.get(group.key) ?? []).length > 0 && (
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[11px] text-[var(--c-text-3)]">{t("この日に獲得")}</span>
                  {earnedByDay.get(group.key).slice(0, 3).map((item) => {
                    const Icon = ACHIEVEMENT_ICONS[item.icon] ?? Award;
                    return (
                      <button
                        key={item.id}
                        onClick={onOpenAchievements}
                        className="flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-[var(--accent)] text-[var(--on-accent)] font-medium"
                      >
                        <Icon size={11} strokeWidth={2} />
                        {t(item.title, achievementParams(item))}
                      </button>
                    );
                  })}
                  {earnedByDay.get(group.key).length > 3 && (
                    <span className="text-[11px] text-[var(--c-text-3)]">
                      {t("ほか{n}件", { n: earnedByDay.get(group.key).length - 3 })}
                    </span>
                  )}
                </div>
              )}
              {group.items.map((item) => {
                const { icon: Icon, label } = KIND_META[item.kind];
                const detail = [item.shopName, item.kind === "log" && item.place === "shop" ? t("店舗で飲んだ") : null]
                  .filter(Boolean)
                  .join(" ・ ");
                const body = (
                  <>
                    <span className="shrink-0 w-8 h-8 rounded-full bg-[var(--c-surface-2)] border border-[var(--c-border)] flex items-center justify-center text-[var(--accent)]">
                      <Icon size={14} strokeWidth={1.75} />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-[11px] text-[var(--c-text-3)]">
                        {t(label)} ・ {timeFormat.format(item.t)}
                      </span>
                      <span className="block text-[13px] text-[var(--c-text)] truncate">
                        {item.title || t("(名前なし)")}
                      </span>
                      {detail && <span className="block text-[11px] text-[var(--c-text-3)] truncate">{detail}</span>}
                    </span>
                  </>
                );
                const rowClass =
                  "w-full text-left flex items-center gap-3 rounded-xl bg-[var(--c-surface)] border border-[var(--c-border)] px-3 py-2.5";
                return item.kind === "log" && item.productId ? (
                  <button
                    key={item.id}
                    onClick={() => onOpenLog(item)}
                    className={`${rowClass} hover:border-[var(--accent-label)] transition-colors`}
                  >
                    {body}
                  </button>
                ) : (
                  <div key={item.id} className={rowClass}>
                    {body}
                  </div>
                );
              })}
            </div>
          ))}
          {groups.length > dayGroupCount && (
            <button
              onClick={() => setDayGroupCount((n) => n + DAY_GROUPS_STEP)}
              className="py-2.5 rounded-xl border border-[var(--c-border)] text-[var(--c-text-2)] text-[13px]"
            >
              {t("もっと見る")}
            </button>
          )}
        </section>
      )}
        </>
      )}
    </main>
  );
}
