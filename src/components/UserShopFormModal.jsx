import { useEffect, useState } from "react";
import { X, Store } from "lucide-react";
import { INPUT_CLASS, LABEL_CLASS, PRIMARY_BUTTON_CLASS } from "./formStyles";

const normalizeName = (s) => s.normalize("NFKC").trim().toLowerCase();

// 「店舗を登録」フォーム。コレクションに手動で商品を登録する前の、最初のステップ。
// 店舗名を入力すると、アプリに収録済みの店舗が候補に出て、選ぶと住所が自動で入る。
// target: null(閉じる) | { shop: 既存の店舗 }(編集) | {}(新規)
export function UserShopFormModal({ target, appShops, userShops, onSave, onClose }) {
  const editing = target?.shop ?? null;
  const [name, setName] = useState("");
  const [address, setAddress] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    setName(editing?.name ?? "");
    setAddress(editing?.address ?? "");
    setError("");
  }, [target, editing]);

  if (!target) return null;

  const handleNameChange = (value) => {
    setName(value);
    setError("");
    // アプリ収録の店舗と同じ名前なら、住所が空のときだけ自動で入れる
    const matched = appShops.find((s) => s.name === value);
    if (matched && !address.trim()) setAddress(matched.address ?? "");
  };

  const handleSubmit = () => {
    const trimmedName = name.trim();
    if (!trimmedName) return;
    const duplicated = userShops.some(
      (s) => s.id !== editing?.id && normalizeName(s.name) === normalizeName(trimmedName)
    );
    if (duplicated) {
      setError("同じ名前の店舗がすでに登録されています");
      return;
    }
    onSave({ name: trimmedName, address: address.trim() }, editing);
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
              {editing ? "Edit Shop" : "New Shop"}
            </p>
            <h3 className="font-serif text-[17px] text-[var(--c-text)] mt-0.5">
              {editing ? "店舗を編集" : "店舗を登録"}
            </h3>
          </div>
          <button
            onClick={onClose}
            className="shrink-0 text-[var(--c-text-3)] hover:text-[var(--c-text)] transition-colors min-w-[36px] min-h-[36px] flex items-center justify-center -m-2"
            aria-label="閉じる"
          >
            <X size={18} />
          </button>
        </div>

        <div className="flex flex-col gap-4">
          <div>
            <label className={LABEL_CLASS} htmlFor="user-shop-name">
              店舗名
            </label>
            <input
              id="user-shop-name"
              type="text"
              list="user-shop-suggestions"
              value={name}
              onChange={(e) => handleNameChange(e.target.value)}
              placeholder="例: FUGLEN COFFEE ROASTERS"
              autoComplete="off"
              className={INPUT_CLASS}
            />
            {/* アプリ収録の店舗名の候補(選ぶと住所が自動で入る)。自由入力もできる */}
            <datalist id="user-shop-suggestions">
              {appShops.map((s) => (
                <option key={s.name} value={s.name} />
              ))}
            </datalist>
            <p className="text-[11px] text-[var(--c-text-3)] mt-1.5">
              アプリに載っていないお店も、自由に入力して登録できます。
            </p>
            {error && <p className="text-[12px] text-[var(--c-danger)] mt-1.5">{error}</p>}
          </div>

          <div>
            <label className={LABEL_CLASS} htmlFor="user-shop-address">
              住所(任意)
            </label>
            <input
              id="user-shop-address"
              type="text"
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              placeholder="例: 東京都渋谷区富ヶ谷1-16-11"
              className={INPUT_CLASS}
            />
            <p className="text-[11px] text-[var(--c-text-3)] mt-1.5">入力すると、地図で店舗を開けるようになります。</p>
          </div>

          <button onClick={handleSubmit} disabled={!name.trim()} className={PRIMARY_BUTTON_CLASS}>
            <Store size={14} strokeWidth={2} />
            {editing ? "変更を保存" : "この店舗を登録"}
          </button>
        </div>
      </div>
    </div>
  );
}
