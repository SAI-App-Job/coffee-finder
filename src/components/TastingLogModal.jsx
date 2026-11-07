import { useEffect, useState } from "react";
import { X, ArrowLeft, Plus, Trash2, NotebookPen, Gauge } from "lucide-react";
import { DialInGauge } from "./common";
import { FlavorChips, FlavorPicker } from "./FlavorPicker";
import { formatDateTime } from "../utils/format";
import { useT } from "../i18n";

// 記録の場所。"home"=自宅などで自分で淹れた記録(抽出条件+Dial-in Score+ノート)、
// "shop"=店舗で飲んだ記録(ノートのみ)。place未設定の既存記録は"home"として扱う。
const PLACES = [
  { value: "home", label: "自宅で淹れた" },
  { value: "shop", label: "店舗で飲んだ" },
];

const EMPTY_FORM = {
  place: "home",
  brewMethod: "",
  doseG: "",
  waterG: "",
  grindSize: "",
  waterTempC: "",
  brewTime: "",
  dialInScore: 50,
  note: "",
  flavors: [],
};

function computeRatio(doseG, waterG) {
  const dose = Number(doseG);
  const water = Number(waterG);
  if (!dose || !water) return null;
  return `1 : ${(water / dose).toFixed(1)}`;
}

function LogEntryCard({ entry, onDelete }) {
  const t = useT();
  const isShop = entry.place === "shop";
  const ratio = computeRatio(entry.doseG, entry.waterG);
  const recipeParts = [
    entry.brewMethod,
    entry.doseG && `${entry.doseG}g`,
    entry.waterG && `${entry.waterG}g`,
    ratio,
    entry.grindSize,
    entry.waterTempC && `${entry.waterTempC}℃`,
    entry.brewTime,
  ].filter(Boolean);

  return (
    <div className="rounded-xl bg-[var(--c-surface-2)] border border-[var(--c-border)] p-3.5 flex flex-col gap-2.5">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <span
            className={`px-2 py-0.5 rounded-full text-[10px] border ${
              isShop
                ? "border-[var(--accent)] text-[var(--accent)]"
                : "border-[var(--c-border)] text-[var(--c-text-2)]"
            }`}
          >
            {isShop ? t("店舗") : t("自宅")}
          </span>
          <p className="text-[11px] text-[var(--c-text-3)]">{t("登録日 {date}", { date: formatDateTime(entry.recordedAt) })}</p>
        </div>
        <button
          onClick={() => onDelete(entry.id)}
          className="text-[var(--c-text-3)] hover:text-[var(--c-text)] transition-colors -m-1 p-1"
          aria-label={t("このログを削除")}
        >
          <Trash2 size={13} />
        </button>
      </div>
      {!isShop && recipeParts.length > 0 && (
        <p className="text-[12px] text-[var(--c-text)] leading-relaxed">{recipeParts.join(" ・ ")}</p>
      )}
      {!isShop && (
        <div className="flex items-center gap-3">
          <DialInGauge value={entry.dialInScore ?? 0} size={72} />
          <div className="flex-1">
            <p className="text-[10px] text-[var(--accent-label)] uppercase tracking-wide">Dial-in Score</p>
            <p className="text-[11px] text-[var(--c-text-3)] mt-0.5">{t("目指した味にどれだけ近づけたか")}</p>
          </div>
        </div>
      )}
      {entry.note && <p className="text-[12px] text-[var(--c-text-2)] leading-relaxed">{entry.note}</p>}
      <FlavorChips flavors={entry.flavors} />
    </div>
  );
}

// 商品詳細モーダルの「テイスティングログを記録」から開く、記録一覧+新規記録フォーム。
// 同じ豆に対する複数の抽出記録を並べて見返せるようにし(条件を変えた比較)、
// Dial-in Score(=目指した味にどれだけ近づけたか)をゲージで直感的に示す。
export function TastingLogModal({ product, logs, onAddLog, onDeleteLog, onClose }) {
  const t = useT();
  const [mode, setMode] = useState("list");
  const [form, setForm] = useState(EMPTY_FORM);

  useEffect(() => {
    setMode("list");
    setForm(EMPTY_FORM);
  }, [product?.id]);

  if (!product) return null;

  const ratio = computeRatio(form.doseG, form.waterG);
  const isShopForm = form.place === "shop";
  // 店舗の記録はノートと風味だけが中身なので、どちらも空のまま保存できないようにする
  const canSubmit = !isShopForm || form.note.trim() !== "" || form.flavors.length > 0;

  const handleSubmit = () => {
    if (!canSubmit) return;
    if (isShopForm) {
      onAddLog({ place: "shop", note: form.note.trim() || null, flavors: form.flavors });
      setForm(EMPTY_FORM);
      setMode("list");
      return;
    }
    onAddLog({
      place: "home",
      brewMethod: form.brewMethod.trim() || null,
      doseG: form.doseG ? Number(form.doseG) : null,
      waterG: form.waterG ? Number(form.waterG) : null,
      grindSize: form.grindSize.trim() || null,
      waterTempC: form.waterTempC ? Number(form.waterTempC) : null,
      brewTime: form.brewTime.trim() || null,
      dialInScore: Number(form.dialInScore),
      note: form.note.trim() || null,
      flavors: form.flavors,
    });
    setForm(EMPTY_FORM);
    setMode("list");
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full sm:w-[440px] max-h-[85vh] overflow-y-auto bg-[var(--c-surface)] border border-[var(--c-border)] rounded-t-2xl sm:rounded-2xl p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 mb-4">
          <div className="flex items-center gap-2 min-w-0">
            {mode === "form" && (
              <button
                onClick={() => setMode("list")}
                className="shrink-0 text-[var(--c-text-3)] hover:text-[var(--c-text)] transition-colors -m-1 p-1"
                aria-label={t("一覧に戻る")}
              >
                <ArrowLeft size={18} />
              </button>
            )}
            <div className="min-w-0">
              <p className="text-[11px] tracking-wider text-[var(--accent-label)] uppercase">
                {mode === "list" ? "Tasting Log" : "New Log"}
              </p>
              <h3 className="font-serif text-[17px] text-[var(--c-text)] mt-0.5 leading-snug truncate">
                {product.rawName}
              </h3>
            </div>
          </div>
          <button
            onClick={onClose}
            className="shrink-0 text-[var(--c-text-3)] hover:text-[var(--c-text)] transition-colors min-w-[36px] min-h-[36px] flex items-center justify-center -m-2"
            aria-label={t("閉じる")}
          >
            <X size={18} />
          </button>
        </div>

        {mode === "list" ? (
          <div className="flex flex-col gap-3">
            <button
              onClick={() => setMode("form")}
              className="flex items-center justify-center gap-1.5 py-2.5 rounded-xl bg-[var(--accent)] text-[var(--on-accent)] text-[13px] font-medium hover:bg-[var(--accent-soft)] transition-colors"
            >
              <Plus size={14} strokeWidth={2} />
              {t("新しく記録する")}
            </button>
            {logs.length === 0 ? (
              <p className="text-[12px] text-[var(--c-text-3)] text-center py-8">
                {t("まだ記録がありません。自宅で淹れたときは抽出条件とDial-in Score、店舗で飲んだときはテイスティングノートを記録できます。")}
              </p>
            ) : (
              <>
                <p className="text-[11px] text-[var(--c-text-3)]">
                  {t("同じ豆の記録を見比べられます({n}件)", { n: logs.length })}
                </p>
                {logs.map((entry) => (
                  <LogEntryCard key={entry.id} entry={entry} onDelete={onDeleteLog} />
                ))}
              </>
            )}
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            <div className="grid grid-cols-2 gap-1 p-1 rounded-xl bg-[var(--c-surface-2)] border border-[var(--c-border)]">
              {PLACES.map((place) => (
                <button
                  key={place.value}
                  type="button"
                  onClick={() => setForm((f) => ({ ...f, place: place.value }))}
                  aria-pressed={form.place === place.value}
                  className={`py-2 rounded-lg text-[12px] transition-colors ${
                    form.place === place.value
                      ? "bg-[var(--accent)] text-[var(--on-accent)] font-medium"
                      : "text-[var(--c-text-2)] hover:text-[var(--c-text)]"
                  }`}
                >
                  {t(place.label)}
                </button>
              ))}
            </div>

            {!isShopForm && (
              <>
            <div>
              <label className="text-[11px] tracking-wide text-[var(--accent-label)] uppercase mb-1 block">
                {t("抽出方法")}
              </label>
              <input
                type="text"
                value={form.brewMethod}
                onChange={(e) => setForm((f) => ({ ...f, brewMethod: e.target.value }))}
                placeholder={t("例: V60、エアロプレス、エスプレッソ")}
                className="w-full px-3 py-2 rounded-lg bg-[var(--c-surface-2)] border border-[var(--c-border)] text-[13px] text-[var(--c-text)] placeholder:text-[var(--c-text-3)] focus:outline-none focus:border-[var(--accent)]"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[11px] tracking-wide text-[var(--accent-label)] uppercase mb-1 block">
                  {t("粉量(g)")}
                </label>
                <input
                  type="number"
                  inputMode="decimal"
                  value={form.doseG}
                  onChange={(e) => setForm((f) => ({ ...f, doseG: e.target.value }))}
                  className="w-full px-3 py-2 rounded-lg bg-[var(--c-surface-2)] border border-[var(--c-border)] text-[13px] text-[var(--c-text)] focus:outline-none focus:border-[var(--accent)]"
                />
              </div>
              <div>
                <label className="text-[11px] tracking-wide text-[var(--accent-label)] uppercase mb-1 block">
                  {t("湯量(g)")}
                </label>
                <input
                  type="number"
                  inputMode="decimal"
                  value={form.waterG}
                  onChange={(e) => setForm((f) => ({ ...f, waterG: e.target.value }))}
                  className="w-full px-3 py-2 rounded-lg bg-[var(--c-surface-2)] border border-[var(--c-border)] text-[13px] text-[var(--c-text)] focus:outline-none focus:border-[var(--accent)]"
                />
              </div>
            </div>
            {ratio && <p className="text-[12px] text-[var(--c-text-3)] -mt-2">{t("比率(自動計算): {ratio}", { ratio })}</p>}

            <div>
              <label className="text-[11px] tracking-wide text-[var(--accent-label)] uppercase mb-1 block">
                {t("挽き目")}
              </label>
              <input
                type="text"
                value={form.grindSize}
                onChange={(e) => setForm((f) => ({ ...f, grindSize: e.target.value }))}
                placeholder={t("例: 中細挽き、コマンダンテ20クリック")}
                className="w-full px-3 py-2 rounded-lg bg-[var(--c-surface-2)] border border-[var(--c-border)] text-[13px] text-[var(--c-text)] placeholder:text-[var(--c-text-3)] focus:outline-none focus:border-[var(--accent)]"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[11px] tracking-wide text-[var(--accent-label)] uppercase mb-1 block">
                  {t("湯温(℃)")}
                </label>
                <input
                  type="number"
                  inputMode="decimal"
                  value={form.waterTempC}
                  onChange={(e) => setForm((f) => ({ ...f, waterTempC: e.target.value }))}
                  className="w-full px-3 py-2 rounded-lg bg-[var(--c-surface-2)] border border-[var(--c-border)] text-[13px] text-[var(--c-text)] focus:outline-none focus:border-[var(--accent)]"
                />
              </div>
              <div>
                <label className="text-[11px] tracking-wide text-[var(--accent-label)] uppercase mb-1 block">
                  {t("抽出時間")}
                </label>
                <input
                  type="text"
                  value={form.brewTime}
                  onChange={(e) => setForm((f) => ({ ...f, brewTime: e.target.value }))}
                  placeholder={t("例: 2:30")}
                  className="w-full px-3 py-2 rounded-lg bg-[var(--c-surface-2)] border border-[var(--c-border)] text-[13px] text-[var(--c-text)] placeholder:text-[var(--c-text-3)] focus:outline-none focus:border-[var(--accent)]"
                />
              </div>
            </div>

            <div>
              <div className="flex items-center gap-1.5 mb-1">
                <Gauge size={13} className="text-[var(--accent)]" strokeWidth={1.75} />
                <label className="text-[11px] tracking-wide text-[var(--accent-label)] uppercase">
                  Dial-in Score
                </label>
              </div>
              <p className="text-[11px] text-[var(--c-text-3)] mb-3">{t("目指した味にどれだけ近づけられたか")}</p>
              <div className="flex items-center gap-4">
                <DialInGauge value={Number(form.dialInScore)} size={88} />
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={form.dialInScore}
                  onChange={(e) => setForm((f) => ({ ...f, dialInScore: e.target.value }))}
                  className="flex-1 accent-[var(--accent)]"
                />
              </div>
            </div>
              </>
            )}

            <div>
              <label className="text-[11px] tracking-wide text-[var(--accent-label)] uppercase mb-1 block">
                {t("テイスティングノート")}
              </label>
              <textarea
                value={form.note}
                onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))}
                rows={isShopForm ? 5 : 3}
                placeholder={
                  isShopForm
                    ? t("店で飲んだときの香り・酸味・甘み・後味など、感じたことを自由に")
                    : t("香り・酸味・甘み・後味など、感じたことを自由に")
                }
                className="w-full px-3 py-2 rounded-lg bg-[var(--c-surface-2)] border border-[var(--c-border)] text-[13px] text-[var(--c-text)] placeholder:text-[var(--c-text-3)] focus:outline-none focus:border-[var(--accent)] resize-none"
              />
            </div>

            <div>
              <label className="text-[11px] tracking-wide text-[var(--accent-label)] uppercase mb-1 block">
                {t("風味")}
              </label>
              <p className="text-[11px] text-[var(--c-text-3)] mb-2">{t("感じた風味を複数選べます(分類をタップすると詳細が開きます)")}</p>
              <FlavorPicker
                value={form.flavors}
                onChange={(flavors) => setForm((f) => ({ ...f, flavors }))}
              />
            </div>

            <button
              onClick={handleSubmit}
              disabled={!canSubmit}
              className="flex items-center justify-center gap-1.5 py-2.5 rounded-xl bg-[var(--accent)] text-[var(--on-accent)] text-[13px] font-medium hover:bg-[var(--accent-soft)] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <NotebookPen size={14} strokeWidth={2} />
              {t("この記録を保存")}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
