import { useEffect, useState } from "react";
import { X, ArrowLeft, Plus, Trash2, NotebookPen, Gauge } from "lucide-react";
import { DialInGauge } from "./common";
import { formatDateTime } from "../utils/format";

const EMPTY_FORM = {
  brewMethod: "",
  doseG: "",
  waterG: "",
  grindSize: "",
  waterTempC: "",
  brewTime: "",
  dialInScore: 50,
  note: "",
};

function computeRatio(doseG, waterG) {
  const dose = Number(doseG);
  const water = Number(waterG);
  if (!dose || !water) return null;
  return `1 : ${(water / dose).toFixed(1)}`;
}

function LogEntryCard({ entry, onDelete }) {
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
    <div className="rounded-xl bg-[#3B2211] border border-[#4A3A2A] p-3.5 flex flex-col gap-2.5">
      <div className="flex items-start justify-between gap-3">
        <p className="text-[11px] text-[#8B7361]">{formatDateTime(entry.recordedAt)}</p>
        <button
          onClick={() => onDelete(entry.id)}
          className="text-[#8B7361] hover:text-[#F2E9DD] transition-colors -m-1 p-1"
          aria-label="このログを削除"
        >
          <Trash2 size={13} />
        </button>
      </div>
      {recipeParts.length > 0 && (
        <p className="text-[12px] text-[#F2E9DD] leading-relaxed">{recipeParts.join(" ・ ")}</p>
      )}
      <div className="flex items-center gap-3">
        <DialInGauge value={entry.dialInScore ?? 0} size={72} />
        <div className="flex-1">
          <p className="text-[10px] text-[var(--accent-label)] uppercase tracking-wide">Dial-in Score</p>
          <p className="text-[11px] text-[#8B7361] mt-0.5">目指した味にどれだけ近づけたか</p>
        </div>
      </div>
      {entry.note && <p className="text-[12px] text-[#B8A891] leading-relaxed">{entry.note}</p>}
    </div>
  );
}

// 商品詳細モーダルの「テイスティングログを記録」から開く、記録一覧+新規記録フォーム。
// 同じ豆に対する複数の抽出記録を並べて見返せるようにし(条件を変えた比較)、
// Dial-in Score(=目指した味にどれだけ近づけたか)をゲージで直感的に示す。
export function TastingLogModal({ product, logs, onAddLog, onDeleteLog, onClose }) {
  const [mode, setMode] = useState("list");
  const [form, setForm] = useState(EMPTY_FORM);

  useEffect(() => {
    setMode("list");
    setForm(EMPTY_FORM);
  }, [product?.id]);

  if (!product) return null;

  const ratio = computeRatio(form.doseG, form.waterG);

  const handleSubmit = () => {
    onAddLog({
      brewMethod: form.brewMethod.trim() || null,
      doseG: form.doseG ? Number(form.doseG) : null,
      waterG: form.waterG ? Number(form.waterG) : null,
      grindSize: form.grindSize.trim() || null,
      waterTempC: form.waterTempC ? Number(form.waterTempC) : null,
      brewTime: form.brewTime.trim() || null,
      dialInScore: Number(form.dialInScore),
      note: form.note.trim() || null,
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
        className="w-full sm:w-[440px] max-h-[85vh] overflow-y-auto bg-[#2F241A] border border-[#4A3A2A] rounded-t-2xl sm:rounded-2xl p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 mb-4">
          <div className="flex items-center gap-2 min-w-0">
            {mode === "form" && (
              <button
                onClick={() => setMode("list")}
                className="shrink-0 text-[#8B7361] hover:text-[#F2E9DD] transition-colors -m-1 p-1"
                aria-label="一覧に戻る"
              >
                <ArrowLeft size={18} />
              </button>
            )}
            <div className="min-w-0">
              <p className="text-[11px] tracking-wider text-[var(--accent-label)] uppercase">
                {mode === "list" ? "Tasting Log" : "New Log"}
              </p>
              <h3 className="font-serif text-[17px] text-[#F2E9DD] mt-0.5 leading-snug truncate">
                {product.rawName}
              </h3>
            </div>
          </div>
          <button
            onClick={onClose}
            className="shrink-0 text-[#8B7361] hover:text-[#F2E9DD] transition-colors min-w-[36px] min-h-[36px] flex items-center justify-center -m-2"
            aria-label="閉じる"
          >
            <X size={18} />
          </button>
        </div>

        {mode === "list" ? (
          <div className="flex flex-col gap-3">
            <button
              onClick={() => setMode("form")}
              className="flex items-center justify-center gap-1.5 py-2.5 rounded-xl bg-[var(--accent)] text-[#231810] text-[13px] font-medium hover:bg-[var(--accent-soft)] transition-colors"
            >
              <Plus size={14} strokeWidth={2} />
              新しく記録する
            </button>
            {logs.length === 0 ? (
              <p className="text-[12px] text-[#8B7361] text-center py-8">
                まだ記録がありません。抽出条件とDial-in Scoreを記録して、次の一杯に活かしましょう。
              </p>
            ) : (
              <>
                <p className="text-[11px] text-[#8B7361]">
                  同じ豆で条件を変えた記録を比較できます({logs.length}件)
                </p>
                {logs.map((entry) => (
                  <LogEntryCard key={entry.id} entry={entry} onDelete={onDeleteLog} />
                ))}
              </>
            )}
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            <div>
              <label className="text-[11px] tracking-wide text-[var(--accent-label)] uppercase mb-1 block">
                抽出方法
              </label>
              <input
                type="text"
                value={form.brewMethod}
                onChange={(e) => setForm((f) => ({ ...f, brewMethod: e.target.value }))}
                placeholder="例: V60、エアロプレス、エスプレッソ"
                className="w-full px-3 py-2 rounded-lg bg-[#3B2211] border border-[#4A3A2A] text-[13px] text-[#F2E9DD] placeholder:text-[#8B7361] focus:outline-none focus:border-[var(--accent)]"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[11px] tracking-wide text-[var(--accent-label)] uppercase mb-1 block">
                  粉量(g)
                </label>
                <input
                  type="number"
                  inputMode="decimal"
                  value={form.doseG}
                  onChange={(e) => setForm((f) => ({ ...f, doseG: e.target.value }))}
                  className="w-full px-3 py-2 rounded-lg bg-[#3B2211] border border-[#4A3A2A] text-[13px] text-[#F2E9DD] focus:outline-none focus:border-[var(--accent)]"
                />
              </div>
              <div>
                <label className="text-[11px] tracking-wide text-[var(--accent-label)] uppercase mb-1 block">
                  湯量(g)
                </label>
                <input
                  type="number"
                  inputMode="decimal"
                  value={form.waterG}
                  onChange={(e) => setForm((f) => ({ ...f, waterG: e.target.value }))}
                  className="w-full px-3 py-2 rounded-lg bg-[#3B2211] border border-[#4A3A2A] text-[13px] text-[#F2E9DD] focus:outline-none focus:border-[var(--accent)]"
                />
              </div>
            </div>
            {ratio && <p className="text-[12px] text-[#8B7361] -mt-2">比率(自動計算): {ratio}</p>}

            <div>
              <label className="text-[11px] tracking-wide text-[var(--accent-label)] uppercase mb-1 block">
                挽き目
              </label>
              <input
                type="text"
                value={form.grindSize}
                onChange={(e) => setForm((f) => ({ ...f, grindSize: e.target.value }))}
                placeholder="例: 中細挽き、コマンダンテ20クリック"
                className="w-full px-3 py-2 rounded-lg bg-[#3B2211] border border-[#4A3A2A] text-[13px] text-[#F2E9DD] placeholder:text-[#8B7361] focus:outline-none focus:border-[var(--accent)]"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[11px] tracking-wide text-[var(--accent-label)] uppercase mb-1 block">
                  湯温(℃)
                </label>
                <input
                  type="number"
                  inputMode="decimal"
                  value={form.waterTempC}
                  onChange={(e) => setForm((f) => ({ ...f, waterTempC: e.target.value }))}
                  className="w-full px-3 py-2 rounded-lg bg-[#3B2211] border border-[#4A3A2A] text-[13px] text-[#F2E9DD] focus:outline-none focus:border-[var(--accent)]"
                />
              </div>
              <div>
                <label className="text-[11px] tracking-wide text-[var(--accent-label)] uppercase mb-1 block">
                  抽出時間
                </label>
                <input
                  type="text"
                  value={form.brewTime}
                  onChange={(e) => setForm((f) => ({ ...f, brewTime: e.target.value }))}
                  placeholder="例: 2:30"
                  className="w-full px-3 py-2 rounded-lg bg-[#3B2211] border border-[#4A3A2A] text-[13px] text-[#F2E9DD] placeholder:text-[#8B7361] focus:outline-none focus:border-[var(--accent)]"
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
              <p className="text-[11px] text-[#8B7361] mb-3">目指した味にどれだけ近づけられたか</p>
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

            <div>
              <label className="text-[11px] tracking-wide text-[var(--accent-label)] uppercase mb-1 block">
                テイスティングノート
              </label>
              <textarea
                value={form.note}
                onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))}
                rows={3}
                placeholder="香り・酸味・甘み・後味など、感じたことを自由に"
                className="w-full px-3 py-2 rounded-lg bg-[#3B2211] border border-[#4A3A2A] text-[13px] text-[#F2E9DD] placeholder:text-[#8B7361] focus:outline-none focus:border-[var(--accent)] resize-none"
              />
            </div>

            <button
              onClick={handleSubmit}
              className="flex items-center justify-center gap-1.5 py-2.5 rounded-xl bg-[var(--accent)] text-[#231810] text-[13px] font-medium hover:bg-[var(--accent-soft)] transition-colors"
            >
              <NotebookPen size={14} strokeWidth={2} />
              この記録を保存
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
