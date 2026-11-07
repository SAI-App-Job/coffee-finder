import { useEffect, useMemo, useState } from "react";
import { X, Coffee } from "lucide-react";
import { FlavorPicker } from "./FlavorPicker";
import { PhotoPicker } from "./ProductPhoto";
import { INPUT_CLASS, LABEL_CLASS, PRIMARY_BUTTON_CLASS } from "./formStyles";
import { ORIGIN_GUIDE } from "../data/originGuide";
import { ROAST_LEVELS } from "../data/roastLevels";
import { PROCESSING_EXPLANATIONS } from "../data/explanations";
import { useT } from "../i18n";

const ORIGIN_COUNTRIES = ORIGIN_GUIDE.map((o) => o.country);
const PROCESSING_METHODS = Object.keys(PROCESSING_EXPLANATIONS);

const EMPTY_FORM = {
  name: "",
  price: "",
  weightG: "",
  originCountry: "",
  roast: "",
  processingMethod: "",
  flavors: [],
  note: "",
};

const toForm = (product) => ({
  name: product.name,
  price: product.price ?? "",
  weightG: product.weightG ?? "",
  originCountry: product.originCountry,
  roast: product.roast,
  processingMethod: product.processingMethod,
  flavors: product.flavors,
  note: product.note,
});

// 空欄・不正な値(負数など)は null にする(価格・重量を推測や0で埋めない)
const toNumberOrNull = (v) => {
  if (v === "" || v === null) return null;
  const n = Number(v);
  return Number.isFinite(n) && n >= 0 ? n : null;
};

// 「商品を登録」フォーム。店舗を先に登録したあと、その店舗の商品として登録する。
// target: null(閉じる) | { shop, product? }(productがあれば編集)
// photoUrl: 編集中の商品に、すでに保存されている写真のURL。
// 写真は「保存」を押すまで確定しない。pendingPhoto: undefined=変更なし / Blob=新しい写真 / null=削除。
export function UserProductFormModal({ target, photoUrl, onSave, onClose }) {
  const t = useT();
  const editing = target?.product ?? null;
  const [form, setForm] = useState(EMPTY_FORM);
  const [pendingPhoto, setPendingPhoto] = useState(undefined);

  useEffect(() => {
    setForm(editing ? toForm(editing) : EMPTY_FORM);
    setPendingPhoto(undefined);
  }, [target, editing]);

  // 選んだ写真のプレビュー用URL(新しい写真を選んだときだけ作る)
  const pendingUrl = useMemo(
    () => (pendingPhoto instanceof Blob ? URL.createObjectURL(pendingPhoto) : null),
    [pendingPhoto]
  );
  useEffect(() => () => pendingUrl && URL.revokeObjectURL(pendingUrl), [pendingUrl]);

  if (!target) return null;

  const shownPhotoUrl = pendingPhoto === undefined ? photoUrl : pendingUrl;

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));
  const name = form.name.trim();

  const handleSubmit = () => {
    if (!name) return;
    onSave(
      {
        name,
        price: toNumberOrNull(form.price),
        weightG: toNumberOrNull(form.weightG),
        originCountry: form.originCountry.trim(),
        roast: form.roast,
        processingMethod: form.processingMethod.trim(),
        flavors: form.flavors,
        note: form.note.trim(),
      },
      target.shop,
      editing,
      pendingPhoto
    );
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
          <div className="min-w-0">
            <p className="text-[11px] tracking-wider text-[var(--accent-label)] uppercase">
              {editing ? "Edit Product" : "New Product"}
            </p>
            <h3 className="font-serif text-[17px] text-[var(--c-text)] mt-0.5">
              {editing ? t("商品を編集") : t("商品を登録")}
            </h3>
            <p className="text-[12px] text-[var(--c-text-3)] mt-0.5 truncate">{t("店舗: {name}", { name: target.shop.name })}</p>
          </div>
          <button
            onClick={onClose}
            className="shrink-0 text-[var(--c-text-3)] hover:text-[var(--c-text)] transition-colors min-w-[36px] min-h-[36px] flex items-center justify-center -m-2"
            aria-label={t("閉じる")}
          >
            <X size={18} />
          </button>
        </div>

        <div className="flex flex-col gap-4">
          <div>
            <label className={LABEL_CLASS} htmlFor="user-product-name">
              {t("商品名")}
            </label>
            <input
              id="user-product-name"
              type="text"
              value={form.name}
              onChange={set("name")}
              placeholder={t("例: エチオピア イルガチェフェ")}
              className={INPUT_CLASS}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={LABEL_CLASS} htmlFor="user-product-price">
                {t("価格(円・任意)")}
              </label>
              <input
                id="user-product-price"
                type="number"
                inputMode="numeric"
                min="0"
                value={form.price}
                onChange={set("price")}
                placeholder={t("例: 1500")}
                className={INPUT_CLASS}
              />
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="user-product-weight">
                {t("内容量(g・任意)")}
              </label>
              <input
                id="user-product-weight"
                type="number"
                inputMode="numeric"
                min="0"
                value={form.weightG}
                onChange={set("weightG")}
                placeholder={t("例: 200")}
                className={INPUT_CLASS}
              />
            </div>
          </div>

          <div>
            <label className={LABEL_CLASS} htmlFor="user-product-origin">
              {t("産地(任意)")}
            </label>
            <input
              id="user-product-origin"
              type="text"
              list="user-product-origins"
              value={form.originCountry}
              onChange={set("originCountry")}
              placeholder={t("例: エチオピア(ブレンドは自由に入力)")}
              autoComplete="off"
              className={INPUT_CLASS}
            />
            <datalist id="user-product-origins">
              {ORIGIN_COUNTRIES.map((c) => (
                <option key={c} value={c} />
              ))}
            </datalist>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={LABEL_CLASS} htmlFor="user-product-roast">
                {t("焙煎度(任意)")}
              </label>
              <select id="user-product-roast" value={form.roast} onChange={set("roast")} className={INPUT_CLASS}>
                <option value="">{t("指定なし")}</option>
                {ROAST_LEVELS.map((r) => (
                  <option key={r.key} value={r.key}>
                    {t(r.label)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="user-product-processing">
                {t("精製方法(任意)")}
              </label>
              <input
                id="user-product-processing"
                type="text"
                list="user-product-processings"
                value={form.processingMethod}
                onChange={set("processingMethod")}
                placeholder={t("例: ウォッシュド")}
                autoComplete="off"
                className={INPUT_CLASS}
              />
              <datalist id="user-product-processings">
                {PROCESSING_METHODS.map((m) => (
                  <option key={m} value={m} />
                ))}
              </datalist>
            </div>
          </div>

          <div>
            <label className={LABEL_CLASS}>{t("風味(任意)")}</label>
            <p className="text-[11px] text-[var(--c-text-3)] mb-2">
              {t("感じた風味を複数選べます(分類をタップすると詳細が開きます)")}
            </p>
            <FlavorPicker value={form.flavors} onChange={(flavors) => setForm((f) => ({ ...f, flavors }))} />
          </div>

          <div>
            <label className={LABEL_CLASS}>{t("パッケージ写真(任意)")}</label>
            <PhotoPicker url={shownPhotoUrl} onChange={(blob) => setPendingPhoto(blob)} />
          </div>

          <div>
            <label className={LABEL_CLASS} htmlFor="user-product-note">
              {t("メモ(任意)")}
            </label>
            <textarea
              id="user-product-note"
              value={form.note}
              onChange={set("note")}
              rows={3}
              placeholder={t("購入した日や、気づいたことなど")}
              className={`${INPUT_CLASS} resize-none`}
            />
          </div>

          <button onClick={handleSubmit} disabled={!name} className={PRIMARY_BUTTON_CLASS}>
            <Coffee size={14} strokeWidth={2} />
            {editing ? t("変更を保存") : t("この商品を登録")}
          </button>
        </div>
      </div>
    </div>
  );
}
