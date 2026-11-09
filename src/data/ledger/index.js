// 出典の台帳(docs/research-rules.md)を読み、「表示してよい記述」かを判定する。
//
// 表示してよい条件(すべて満たす):
//  1. 台帳に、その記述のキーがある
//  2. 記述の status が "verified"
//  3. 現在の本文のハッシュが、検証した本文のハッシュ(textHash)と一致する(本文を直したら再検証が必要)
//  4. 全ての主張が "verified" で、各主張に「公式の一次資料(kind: primary)を原文で読んだ(readMethod: full-text)」
//     資料が1つ以上ある。二次資料だけの主張は、ユーザーの承認(approvedSecondary: true)があるときだけ。
//
// 出典のない記述は、画面に出さない。
import SOURCES from "./sources.json";
import ENTRIES from "./entries.json";

// FNV-1a(32bit)。本文の同一性の確認だけに使う。
export function hashText(text) {
  let h = 0x811c9dc5;
  const s = String(text).normalize("NFC");
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h.toString(16).padStart(8, "0");
}

const claimIsBacked = (claim, entry) =>
  claim.status === "verified" &&
  Array.isArray(claim.sourceIds) &&
  claim.sourceIds.some((id) => {
    const source = SOURCES[id];
    return source && source.readMethod === "full-text" && (source.kind === "primary" || entry.approvedSecondary === true);
  });

/** 表示してよいか。理由も返す(検査スクリプトが使う)。 */
export function publishState(key, text) {
  const entry = ENTRIES[key];
  if (!entry) return { ok: false, reason: "台帳に無い" };
  if (entry.status !== "verified") return { ok: false, reason: `status=${entry.status}` };
  if (!Array.isArray(entry.claims) || entry.claims.length === 0) return { ok: false, reason: "主張が無い" };
  if (entry.content !== undefined) {
    // 監査を経て直した内容(content)を表示する記述。content が検証時と同じであること
    if (entry.textHash !== hashText(JSON.stringify(entry.content))) return { ok: false, reason: "内容が検証時と違う" };
  } else if (text !== undefined && entry.textHash !== hashText(text)) {
    return { ok: false, reason: "本文が検証時と違う" };
  }
  const unbacked = entry.claims.find((claim) => !claimIsBacked(claim, entry));
  if (unbacked) return { ok: false, reason: `根拠の無い主張: ${unbacked.text}` };
  return { ok: true, reason: "" };
}

/** 監査を経て直した日本語の内容。無ければ null(データの本文のまま表示する記述) */
export const contentOf = (key) => ENTRIES[key]?.content ?? null;
/** 同じ内容の英訳。無ければ null */
export const contentEnOf = (key) => ENTRIES[key]?.contentEn ?? null; // 日本語の内容が変わると、merge で英訳が外れる(英語表示は日本語になる)

export const isPublishable = (key, text) => publishState(key, text).ok;

/** 表示中の記述(キーの配列)の出典を、重複なしで返す。 */
export function sourcesFor(keys) {
  const seen = new Map();
  for (const key of keys) {
    const entry = ENTRIES[key];
    if (!entry) continue;
    for (const claim of entry.claims ?? []) {
      for (const id of claim.sourceIds ?? []) {
        const source = SOURCES[id];
        if (source && source.readMethod === "full-text" && !seen.has(id)) seen.set(id, { id, ...source });
      }
    }
  }
  return [...seen.values()];
}

export const LEDGER_SOURCES = SOURCES;
export const LEDGER_ENTRIES = ENTRIES;
