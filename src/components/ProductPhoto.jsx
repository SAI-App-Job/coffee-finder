import { useRef, useState } from "react";
import { Camera, ImagePlus, Trash2, X } from "lucide-react";
import { resizeImageToBlob } from "../utils/imageResize";
import { useT } from "../i18n";

// 写真を拡大して見るための全画面表示(タップで閉じる)
function PhotoLightbox({ url, alt, onClose }) {
  const t = useT();
  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/85 p-4"
      onClick={(e) => {
        e.stopPropagation();
        onClose();
      }}
    >
      <img src={url} alt={alt} className="max-w-full max-h-full object-contain rounded-lg" />
      <button
        onClick={onClose}
        className="absolute top-3 right-3 min-w-[40px] min-h-[40px] flex items-center justify-center rounded-full bg-black/50 text-white"
        aria-label={t("閉じる")}
      >
        <X size={20} />
      </button>
    </div>
  );
}

// 商品カードに載せる小さな写真。タップすると拡大する。
export function PhotoThumb({ url, alt }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  if (!url) return null;
  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="shrink-0 w-14 h-14 rounded-lg overflow-hidden border border-[var(--c-border)] bg-[var(--c-surface)]"
        aria-label={t("パッケージ写真を拡大")}
      >
        <img src={url} alt={alt} className="w-full h-full object-cover" />
      </button>
      {open && <PhotoLightbox url={url} alt={alt} onClose={() => setOpen(false)} />}
    </>
  );
}

// パッケージ写真の追加・変更・削除。スマホでは「撮影」と「ギャラリーから選択」を選べる。
// onChange(blob | null): 縮小済みの JPEG(削除は null)を受け取る。false を返すと保存失敗として扱う。
export function PhotoPicker({ url, onChange, alt }) {
  const t = useT();
  const altText = alt ?? t("パッケージ写真");
  const inputRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [zoom, setZoom] = useState(false);

  const handleFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = ""; // 同じ写真を続けて選んでも change が発火するようにリセット
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const blob = await resizeImageToBlob(file);
      if ((await onChange(blob)) === false) setError(t("写真を保存できませんでした(端末の空き容量や設定をご確認ください)"));
    } catch {
      setError(t("この画像は読み込めませんでした。別の写真をお試しください"));
    } finally {
      setBusy(false);
    }
  };

  const handleRemove = async () => {
    setError("");
    if ((await onChange(null)) === false) setError(t("写真を削除できませんでした"));
  };

  return (
    <div>
      {url ? (
        <div className="flex flex-col gap-2">
          <button
            onClick={() => setZoom(true)}
            className="w-full rounded-xl overflow-hidden border border-[var(--c-border)] bg-[var(--c-surface-2)]"
            aria-label={t("パッケージ写真を拡大")}
          >
            <img src={url} alt={altText} className="w-full max-h-56 object-contain" />
          </button>
          <div className="flex gap-2">
            <button
              onClick={() => inputRef.current?.click()}
              disabled={busy}
              className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl border border-[var(--c-border)] text-[var(--c-text-2)] text-[12px] disabled:opacity-50"
            >
              <Camera size={13} strokeWidth={2} />
              {busy ? t("処理中…") : t("写真を変更")}
            </button>
            <button
              onClick={handleRemove}
              disabled={busy}
              className="flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-xl border border-[var(--c-border)] text-[var(--c-danger)] text-[12px] disabled:opacity-50"
            >
              <Trash2 size={13} strokeWidth={2} />
              {t("削除")}
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={() => inputRef.current?.click()}
          disabled={busy}
          className="w-full flex items-center justify-center gap-1.5 py-3 rounded-xl border border-dashed border-[var(--accent-label)] text-[var(--accent-on-glow)] text-[13px] font-medium hover:bg-[var(--c-surface-2)] transition-colors disabled:opacity-50"
        >
          <ImagePlus size={14} strokeWidth={2} />
          {busy ? t("処理中…") : t("パッケージ写真を追加")}
        </button>
      )}
      <input ref={inputRef} type="file" accept="image/*" className="hidden" onChange={handleFile} />
      {error && <p className="text-[12px] text-[var(--c-danger)] mt-1.5">{error}</p>}
      {zoom && url && <PhotoLightbox url={url} alt={altText} onClose={() => setZoom(false)} />}
    </div>
  );
}
