// 端末内(localStorage)に保存した、利用者のデータの、読み込み・保護の共通部品。
// 規則は docs/user-data-storage.md。
//
// 目的: 「読めなかったら、空で始めて、直後に空で上書きする」ことで、元のデータを失わないようにする。
//   - 読めない(壊れた値・形が違う)・読めたが一部を捨てた(知らない種類など)ときは、元の文字列を、別のキー(<キー>:unreadable)に、残してから続ける。
//   - 保存形式を変えるとき(migrations)は、変える前の文字列を、<キー>:before-v<番号> に、残す。

export const SCHEMA_VERSION = 1; // 保存形式の版。形式を変えるときに、上げる(docs/user-data-storage.md)
const VERSION_KEY = "coffee-finder:schema-version";

// 利用者が作ったデータのキー(バックアップ・退避の対象)。設定・閲覧履歴・アラートは含めない
export const USER_DATA_KEYS = [
  "coffee-finder:favorites",
  "coffee-finder:favorite-dates",
  "coffee-finder:ratings",
  "coffee-finder:tasting-logs",
  "coffee-finder:shop-tasting-notes",
  "coffee-finder:user-collection",
  "coffee-finder:my-tools",
  "coffee-finder:achievements",
  "coffee-finder:product-snapshots",
];

const MAX_UNREADABLE_COPIES = 3;

/** 読めなかった元の文字列を、別のキーに残す(最大3件。古いものは、そのまま) */
export function keepUnreadable(key, raw) {
  try {
    for (let i = 1; i <= MAX_UNREADABLE_COPIES; i++) {
      const slot = i === 1 ? `${key}:unreadable` : `${key}:unreadable-${i}`;
      const existing = localStorage.getItem(slot);
      if (existing === raw) return; // 同じ内容は、重ねて残さない
      if (existing === null) {
        localStorage.setItem(slot, raw);
        return;
      }
    }
  } catch {
    // 保存できない環境では、残せない
  }
}

/**
 * 保存された JSON を読む。
 * parse(parsed) は、{ value, lossy? } を返す。形が違えば、null を返す(または、例外を出す)。
 *   lossy: 読み込むときに、保存されていた一部を捨てた(その場合も、元の文字列を残す)
 * 何も保存されていないときは、fallback を返す(残す必要は、無い)。
 */
export function loadStoredJson(key, parse, fallback) {
  let raw;
  try {
    raw = localStorage.getItem(key);
  } catch {
    return fallback;
  }
  if (raw === null) return fallback;
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch {
    keepUnreadable(key, raw);
    return fallback;
  }
  let result = null;
  try {
    result = parse(parsed);
  } catch {
    result = null;
  }
  if (!result) {
    keepUnreadable(key, raw);
    return fallback;
  }
  if (result.lossy) keepUnreadable(key, raw);
  return result.value;
}

// ---- 保存形式の移行 -----------------------------------------------------
// 形式を変える版を出すときは、ここに { to: 版の番号, run() { ... } } を足し、SCHEMA_VERSION を上げる。
// run() の前に、利用者のデータを、<キー>:before-v<番号> に、自動で残す。
const MIGRATIONS = [];

export function runMigrations() {
  try {
    const stored = Number(localStorage.getItem(VERSION_KEY)) || 1; // この記録を始める前から使っている人は、版1
    if (stored > SCHEMA_VERSION) return; // 新しい版のアプリで作られたデータ。ここでは、何もしない
    const pending = MIGRATIONS.filter((m) => m.to > stored).sort((a, b) => a.to - b.to);
    for (const m of pending) {
      for (const key of USER_DATA_KEYS) {
        const raw = localStorage.getItem(key);
        if (raw !== null) localStorage.setItem(`${key}:before-v${m.to}`, raw);
      }
      m.run();
    }
    if (String(stored) !== String(SCHEMA_VERSION) || localStorage.getItem(VERSION_KEY) === null) {
      localStorage.setItem(VERSION_KEY, String(SCHEMA_VERSION));
    }
  } catch {
    // 保存できない環境では、何もしない
  }
}

// ---- 永続化の要求 -------------------------------------------------------
// ブラウザは、空き容量が足りないときなどに、サイトのデータを自動で消すことがある。
// 「消さないで」と求める(ブラウザが、断ることもある)。利用者のデータができてから、1回だけ呼ぶ。
let persistRequested = false;
export async function requestPersistentStorage() {
  if (persistRequested) return false;
  persistRequested = true;
  try {
    if (!navigator.storage?.persist) return false;
    if (await navigator.storage.persisted?.()) return true;
    return await navigator.storage.persist();
  } catch {
    return false;
  }
}
