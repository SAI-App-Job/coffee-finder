import { useEffect, useMemo, useState } from "react";
import { Wrench, Plus, Pencil, Trash2, X, ExternalLink } from "lucide-react";
import { TOOL_KINDS } from "../hooks/useMyTools";
import { cleanGtin, isValidGtin, normalizeUrl } from "../utils/gtin";
import { findToolByGtin, searchToolCatalog, toolDisplayName } from "../utils/toolCatalog";
import { loadToolCatalog } from "../data/remote";
import { INPUT_CLASS, LABEL_CLASS, PRIMARY_BUTTON_CLASS } from "./formStyles";
import { useT } from "../i18n";

const EMPTY = { name: "", maker: "", gtin: "", url: "", note: "" };

// 道具1件の追加・編集フォーム(モーダル)。target = { kind, tool? }。tool があれば編集
function ToolFormModal({ target, onSave, onClose }) {
  const t = useT();
  const editing = target.tool ?? null;
  const kind = TOOL_KINDS.find((k) => k.id === target.kind);
  const [form, setForm] = useState(() => (editing ? { ...EMPTY, ...editing } : EMPTY));
  const [error, setError] = useState("");
  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  // 器具カタログ(メーカー公式のデータ)。開いたときに1回だけ取得する。取得できなければ、候補が出ないだけ
  const [catalog, setCatalog] = useState([]);
  useEffect(() => {
    let alive = true;
    loadToolCatalog().then((rows) => alive && setCatalog(rows));
    return () => {
      alive = false;
    };
  }, []);
  // 名前を入力し始めたときだけ候補を出す(編集の開始時や、候補を選んだ直後は出さない)
  const [nameTouched, setNameTouched] = useState(false);
  const suggestions = useMemo(
    () => (nameTouched ? searchToolCatalog(catalog, target.kind, form.name) : []),
    [catalog, target.kind, form.name, nameTouched]
  );
  const gtinMatch = useMemo(() => findToolByGtin(catalog, form.gtin), [catalog, form.gtin]);
  const gtinMatchKind = gtinMatch ? TOOL_KINDS.find((k) => k.id === gtinMatch.kind) : null;
  const applyCatalogRow = (row) => {
    setNameTouched(false);
    setForm((f) => ({ ...f, name: toolDisplayName(row), maker: row.maker || f.maker, gtin: row.gtin || f.gtin, url: row.url || f.url }));
  };

  const submit = () => {
    const name = form.name.trim();
    if (!name) {
      setError(t("名前を入力してください"));
      return;
    }
    const gtin = cleanGtin(form.gtin);
    if (gtin && !isValidGtin(gtin)) {
      setError(t("バーコードの番号(JAN・GTIN)が正しくありません。8・12・13・14桁の数字で、末尾の確認用の数字も合っている必要があります"));
      return;
    }
    const rawUrl = form.url.trim();
    const url = rawUrl ? normalizeUrl(rawUrl) : "";
    if (rawUrl && !url) {
      setError(t("URLの書式が正しくありません(http:// または https:// で始まるアドレス)"));
      return;
    }
    onSave({ name, maker: form.maker.trim(), gtin, url: url ?? "", note: form.note.trim() }, editing);
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
            <p className="text-[11px] tracking-wider text-[var(--accent-label)] uppercase">My Tools</p>
            <h3 className="font-serif text-[17px] text-[var(--c-text)] mt-0.5">
              {editing ? t("{kind}を編集", { kind: t(kind.label) }) : t("{kind}を登録", { kind: t(kind.label) })}
            </h3>
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
            <label className={LABEL_CLASS} htmlFor="my-tool-name">
              {t("名前")}
            </label>
            <input
              id="my-tool-name"
              type="text"
              value={form.name}
              onChange={(e) => {
                setNameTouched(true);
                set("name")(e);
              }}
              maxLength={80}
              placeholder={t(kind.example)}
              autoComplete="off"
              className={INPUT_CLASS}
            />
            {suggestions.length > 0 && (
              <div className="mt-1.5 rounded-lg border border-[var(--c-border)] bg-[var(--c-surface-2)] overflow-hidden">
                <p className="px-3 pt-2 text-[10px] text-[var(--c-text-3)]">{t("メーカー公式の情報から選べます")}</p>
                <ul>
                  {suggestions.map((row) => (
                    <li key={row.key}>
                      <button
                        type="button"
                        onClick={() => applyCatalogRow(row)}
                        className="w-full text-left px-3 py-2 text-[12px] text-[var(--c-text)] hover:bg-[var(--c-surface)] transition-colors"
                      >
                        <span className="block break-words">{toolDisplayName(row)}</span>
                        <span className="block text-[10px] text-[var(--c-text-3)]">
                          {row.maker}
                          {row.gtin ? ` ・ JAN/GTIN ${row.gtin}` : ""}
                        </span>
                        {row.notListedSince && (
                          <span className="block text-[10px] text-[var(--c-text-3)]">{t("公式サイトに、現在載っていません({date}に確認)", { date: row.notListedSince })}</span>
                        )}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
          <div>
            <label className={LABEL_CLASS} htmlFor="my-tool-maker">
              {t("メーカー(任意)")}
            </label>
            <input
              id="my-tool-maker"
              type="text"
              value={form.maker}
              onChange={set("maker")}
              maxLength={60}
              autoComplete="off"
              className={INPUT_CLASS}
            />
          </div>
          <div>
            <label className={LABEL_CLASS} htmlFor="my-tool-gtin">
              {t("バーコードの番号(JAN・GTIN、任意)")}
            </label>
            <input
              id="my-tool-gtin"
              type="text"
              inputMode="numeric"
              value={form.gtin}
              onChange={set("gtin")}
              maxLength={20}
              placeholder="4901234567894"
              autoComplete="off"
              className={INPUT_CLASS}
            />
            <p className="text-[11px] text-[var(--c-text-3)] mt-1.5 leading-relaxed">
              {t("番号は、控えとして保存します。メーカー公式の情報にある番号なら、名前などを自動で入力できます。")}
            </p>
            {gtinMatch && (
              <button
                type="button"
                onClick={() => (gtinMatch.kind === target.kind ? applyCatalogRow(gtinMatch) : undefined)}
                disabled={gtinMatch.kind !== target.kind}
                className="mt-1.5 w-full text-left px-3 py-2 rounded-lg border border-[var(--accent)] text-[12px] text-[var(--c-text)] disabled:opacity-70"
              >
                <span className="block text-[10px] text-[var(--accent)]">
                  {gtinMatch.kind === target.kind
                    ? t("この番号は、メーカー公式の情報にあります。タップで入力します")
                    : t("この番号は、{kind}のものです", { kind: t(gtinMatchKind.label) })}
                </span>
                <span className="block break-words">{toolDisplayName(gtinMatch)}</span>
                {gtinMatch.notListedSince && (
                  <span className="block text-[10px] text-[var(--c-text-3)]">{t("公式サイトに、現在載っていません({date}に確認)", { date: gtinMatch.notListedSince })}</span>
                )}
              </button>
            )}
          </div>
          <div>
            <label className={LABEL_CLASS} htmlFor="my-tool-url">
              {t("商品ページのURL(任意)")}
            </label>
            <input
              id="my-tool-url"
              type="url"
              value={form.url}
              onChange={set("url")}
              maxLength={500}
              placeholder="https://"
              autoComplete="off"
              className={INPUT_CLASS}
            />
            <p className="text-[11px] text-[var(--c-text-3)] mt-1.5 leading-relaxed">
              {t("アドレスは、リンクとして保存します。ページの内容は、読み込みません。")}
            </p>
          </div>
          <div>
            <label className={LABEL_CLASS} htmlFor="my-tool-note">
              {t("メモ(任意)")}
            </label>
            <textarea
              id="my-tool-note"
              value={form.note}
              onChange={set("note")}
              maxLength={300}
              rows={2}
              className={`${INPUT_CLASS} resize-none`}
            />
          </div>

          {error && (
            <p role="alert" className="text-[12px] text-[var(--c-danger,#d66)] leading-relaxed">
              {error}
            </p>
          )}
          <button type="button" onClick={submit} className={`${PRIMARY_BUTTON_CLASS} w-full`}>
            {editing ? t("保存する") : t("登録する")}
          </button>
        </div>
      </div>
    </div>
  );
}

function ToolRow({ tool, onEdit, onDelete }) {
  const t = useT();
  const [confirming, setConfirming] = useState(false);
  const host = (() => {
    try {
      return new URL(tool.url).hostname.replace(/^www\./, "");
    } catch {
      return "";
    }
  })();

  return (
    <li className="rounded-xl bg-[var(--c-surface-2)] border border-[var(--c-border)] px-3.5 py-3 flex items-start justify-between gap-3">
      <div className="min-w-0 flex flex-col gap-0.5">
        <p className="text-[13px] text-[var(--c-text)] break-words">{tool.name}</p>
        {tool.maker && <p className="text-[11px] text-[var(--c-text-3)] break-words">{tool.maker}</p>}
        {tool.gtin && <p className="text-[11px] text-[var(--c-text-3)]">JAN/GTIN {tool.gtin}</p>}
        {tool.url && host && (
          <a
            href={tool.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[11px] text-[var(--c-text-3)] underline underline-offset-2 inline-flex items-center gap-1 break-all"
          >
            {host}
            <ExternalLink size={10} className="shrink-0" />
          </a>
        )}
        {tool.note && <p className="text-[11px] text-[var(--c-text-2)] leading-relaxed mt-0.5 break-words">{tool.note}</p>}
      </div>
      <div className="shrink-0 flex items-center gap-1">
        {confirming ? (
          <>
            <button
              type="button"
              onClick={() => onDelete(tool.id)}
              className="text-[11px] px-2.5 py-1.5 rounded-full bg-[var(--accent)] text-[var(--on-accent)]"
            >
              {t("削除する")}
            </button>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className="text-[11px] px-2.5 py-1.5 rounded-full border border-[var(--c-border)] text-[var(--c-text-2)]"
            >
              {t("やめる")}
            </button>
          </>
        ) : (
          <>
            <button
              type="button"
              onClick={() => onEdit(tool)}
              className="text-[var(--c-text-3)] hover:text-[var(--c-text)] transition-colors p-2 -m-0.5"
              aria-label={t("編集")}
            >
              <Pencil size={14} />
            </button>
            <button
              type="button"
              onClick={() => setConfirming(true)}
              className="text-[var(--c-text-3)] hover:text-[var(--c-text)] transition-colors p-2 -m-0.5"
              aria-label={t("削除")}
            >
              <Trash2 size={14} />
            </button>
          </>
        )}
      </div>
    </li>
  );
}

// 設定画面の「マイツール」: 自分のドリッパー・ペーパー・コーヒーミル（グラインダー）を登録する。
// 登録した道具は、テイスティングログの「抽出方法」「挽き目」で選べる。
export function MyToolsSection({ tools, addTool, updateTool, deleteTool }) {
  const t = useT();
  const [formTarget, setFormTarget] = useState(null);

  const handleSave = (input, editing) => {
    if (editing) updateTool(editing.id, input);
    else addTool({ ...input, kind: formTarget.kind });
    setFormTarget(null);
  };

  return (
    <section className="rounded-2xl bg-[var(--c-surface)] border border-[var(--c-border)] p-4 flex flex-col gap-3">
      <div className="flex items-center gap-1.5">
        <Wrench size={14} className="text-[var(--accent)]" strokeWidth={1.75} />
        <h3 className="text-[14px] font-medium text-[var(--c-text)]">{t("マイツール")}</h3>
      </div>
      <p className="text-[12px] text-[var(--c-text-3)] leading-relaxed">
        {t("お持ちのコーヒーミル（グラインダー）・ドリッパー・サイフォン・フレンチプレス・エアロプレス・コーヒーメーカー・ペーパーを登録します。テイスティングログの「抽出方法」「挽き目」を書くときに、ここから選べます。登録した内容は、この端末の中だけに保存されます。")}
      </p>
      {TOOL_KINDS.map((kind) => {
        const items = tools.filter((tool) => tool.kind === kind.id);
        return (
          <div key={kind.id} className="flex flex-col gap-2">
            <div className="flex items-center justify-between gap-2">
              <p className="text-[12px] text-[var(--c-text-2)]">
                {t(kind.label)}
                <span className="text-[var(--c-text-3)]"> ({items.length})</span>
              </p>
              <button
                type="button"
                onClick={() => setFormTarget({ kind: kind.id })}
                className="flex items-center gap-1 text-[12px] px-3 py-1.5 rounded-full border border-[var(--c-border)] text-[var(--c-text-2)] hover:border-[var(--accent-label)] transition-colors"
              >
                <Plus size={12} />
                {t("追加")}
              </button>
            </div>
            {items.length > 0 && (
              <ul className="flex flex-col gap-2">
                {items.map((tool) => (
                  <ToolRow
                    key={tool.id}
                    tool={tool}
                    onEdit={(tl) => setFormTarget({ kind: kind.id, tool: tl })}
                    onDelete={deleteTool}
                  />
                ))}
              </ul>
            )}
          </div>
        );
      })}
      {formTarget && (
        <ToolFormModal
          key={formTarget.tool?.id ?? `new-${formTarget.kind}`}
          target={formTarget}
          onSave={handleSave}
          onClose={() => setFormTarget(null)}
        />
      )}
    </section>
  );
}
