#!/usr/bin/env python3
"""出典の原文を、保存して管理するための道具。

目的: 画面の表示や分類のしかたを変えるときに、「原文を保存していないので、探し直す」ことにならないようにする。
台帳(src/data/ledger/sources.json)の資料は、すべて、原文の保存(アーカイブ)がある状態にする。

保存先: source-archive/<資料ID>/  (**git管理の対象外**。公開リポジトリに、第三者の著作物を置かないため。バックアップは、利用者が行う)
  original.<ext>   取得した原文そのもの(PDF・HTML・画像)
  text.txt         原文から取り出した本文(PDFはpypdf、HTMLはタグを除去)。ページ区切りは [[pN]]
  images/          PDFに文字情報がない(スキャン画像)ときの、ページ画像(読み取りの根拠)
  meta.json        URL・取得日・ハッシュ(sha256)・取得方法・メモ
git管理する台帳: docs/source-archive-manifest.json  (資料ID・URL・取得日・sha256・サイズ・ファイル一覧。著作物の中身は含めない)

使い方:
  python scripts/archive_source.py add <資料ID> <URL> [--note 備考]       URLを取得して保存する
  python scripts/archive_source.py import <資料ID> <ファイル> <URL> [--note 備考] [--extra ファイル ...]
                                                                        すでに取得したファイルを、保存する(画像などの補助ファイルは --extra)
  python scripts/archive_source.py check                                台帳の資料に、保存が無いもの・ハッシュが合わないものを一覧にする
  python scripts/archive_source.py verify                               保存したファイルのハッシュを、再計算して確かめる
  python scripts/archive_source.py backfill [--only 接頭辞] [--delay 秒]  台帳の資料のうち、保存が無いものを、まとめて取得する
"""
import argparse
import hashlib
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = ROOT / "source-archive"
MANIFEST = ROOT / "docs" / "source-archive-manifest.json"
SOURCES_JSON = ROOT / "src" / "data" / "ledger" / "sources.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_manifest() -> dict:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {}


def save_manifest(m: dict) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(dict(sorted(m.items())), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def detect_ext(data: bytes, content_type: str, url: str) -> str:
    if data[:4] == b"%PDF":
        return "pdf"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    ct = (content_type or "").lower()
    if "html" in ct or data[:200].lstrip().lower().startswith((b"<!doctype", b"<html")):
        return "html"
    if "json" in ct:
        return "json"
    m = re.search(r"\.(\w{2,4})(?:$|\?)", url)
    return m.group(1).lower() if m else "bin"


def html_to_text(raw: bytes) -> str:
    for enc in ("utf-8", "cp932", "latin-1"):
        try:
            s = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", s, flags=re.S | re.I)
    s = re.sub(r"<br\s*/?>|</p>|</h\d>|</li>|</tr>|</div>|</td>", "\n", s, flags=re.I)
    s = html.unescape(re.sub(r"<[^>]+>", "", s))
    s = re.sub(r"[ \t 　]+", " ", s)
    return re.sub(r"\n\s*\n+", "\n", s).strip() + "\n"


def pdf_to_text(path: Path, out_dir: Path):
    """(本文, スキャン画像か, 画像ファイル名の一覧)"""
    import pypdf

    reader = pypdf.PdfReader(str(path))
    pages = [(p.extract_text() or "") for p in reader.pages]
    text = "".join(f"\n[[p{i + 1}]]\n{t}" for i, t in enumerate(pages))
    images = []
    scanned = sum(len(t.strip()) for t in pages) < 50 * max(len(pages), 1) * 0.2
    if scanned:
        img_dir = out_dir / "images"
        img_dir.mkdir(exist_ok=True)
        for i, p in enumerate(reader.pages):
            try:
                for j, im in enumerate(p.images):
                    name = f"p{i + 1}_{j}.{(im.name.rsplit('.', 1)[-1] if '.' in im.name else 'jpg').lower()}"
                    (img_dir / name).write_bytes(im.data)
                    images.append(name)
                    break  # 1ページ1枚(スキャン)を想定
            except Exception as e:  # 画像を取り出せないページは、記録して続ける
                images.append(f"p{i + 1}:error:{e}")
    return text, scanned, images


def store(source_id: str, data: bytes, url: str, final_url: str, status: int, content_type: str, tool: str, note: str, extra: list[Path] | None = None) -> dict:
    out = ARCHIVE / source_id
    out.mkdir(parents=True, exist_ok=True)
    ext = detect_ext(data, content_type, url)
    original = out / f"original.{ext}"
    original.write_bytes(data)
    files = [original.name]
    text_file, scanned, images = None, False, []
    try:
        if ext == "pdf":
            text, scanned, images = pdf_to_text(original, out)
        elif ext == "html":
            text = html_to_text(data)
        else:
            text = None
        if text is not None:
            (out / "text.txt").write_text(text, encoding="utf-8")
            text_file = "text.txt"
            files.append("text.txt")
    except Exception as e:
        note = (note + " " if note else "") + f"[本文の抽出に失敗: {e}]"
    for ex in extra or []:
        (out / ex.name).write_bytes(ex.read_bytes())
        files.append(ex.name)
    if images:
        files.append("images/")
    meta = {
        "id": source_id,
        "url": url,
        "finalUrl": final_url,
        "httpStatus": status,
        "contentType": content_type,
        "size": len(data),
        "sha256": sha256(data),
        "accessed": date.today().isoformat(),
        "tool": tool,
        "textFile": text_file,
        "textChars": len((out / "text.txt").read_text(encoding="utf-8")) if text_file else 0,
        "scannedImagesOnly": scanned,
        "images": images,
        "files": files,
        "note": note,
    }
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    m = load_manifest()
    m[source_id] = {k: meta[k] for k in ("url", "finalUrl", "httpStatus", "contentType", "size", "sha256", "accessed", "tool", "textChars", "scannedImagesOnly", "files", "note")}
    save_manifest(m)
    return meta


def fetch(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read(), r.geturl(), r.status, r.headers.get("Content-Type", "")


def cmd_add(a):
    data, final, status, ctype = fetch(a.url)
    meta = store(a.id, data, a.url, final, status, ctype, "urllib(fetch)", a.note or "")
    print(f"保存: {a.id} {meta['size']}バイト sha256={meta['sha256'][:12]} 本文{meta['textChars']}字 スキャン画像={meta['scannedImagesOnly']}")


def cmd_import(a):
    p = Path(a.file)
    data = p.read_bytes()
    meta = store(a.id, data, a.url, a.url, 200, "", "ローカルのファイルを取り込み", a.note or "", [Path(x) for x in (a.extra or [])])
    print(f"取り込み: {a.id} {meta['size']}バイト sha256={meta['sha256'][:12]} 本文{meta['textChars']}字 スキャン画像={meta['scannedImagesOnly']}")


def ledger_sources() -> dict:
    return json.loads(SOURCES_JSON.read_text(encoding="utf-8"))


def archived(source_id: str) -> bool:
    return (ARCHIVE / source_id / "meta.json").exists()


def cmd_check(_a):
    m = load_manifest()
    missing, readonly = [], []
    for sid, s in ledger_sources().items():
        if s.get("readMethod") != "full-text":
            continue
        if sid not in m:
            missing.append(sid)
        elif not archived(sid):
            readonly.append(sid)
    total = sum(1 for s in ledger_sources().values() if s.get("readMethod") == "full-text")
    print(f"台帳の資料(全文を読んだもの) {total} 件: 保存あり {total - len(missing)} 件 / 保存なし {len(missing)} 件")
    if readonly:
        print(f"台帳(manifest)にはあるが、この端末にファイルが無い: {len(readonly)} 件 → バックアップから戻すか、backfillで取り直す")
        for sid in readonly[:30]:
            print("  -", sid)
    for sid in missing:
        print("  未保存:", sid, ledger_sources()[sid].get("url", ""))
    sys.exit(1 if missing else 0)


def cmd_verify(_a):
    m = load_manifest()
    bad = 0
    for sid, rec in m.items():
        meta_path = ARCHIVE / sid / "meta.json"
        if not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        orig = next((f for f in meta["files"] if f.startswith("original.")), None)
        if not orig:
            continue
        h = sha256((ARCHIVE / sid / orig).read_bytes())
        if h != rec["sha256"]:
            print("ハッシュが合わない:", sid)
            bad += 1
    print("確認完了。不一致:", bad)
    sys.exit(1 if bad else 0)


def cmd_backfill(a):
    m = load_manifest()
    todo = [(sid, s) for sid, s in ledger_sources().items() if s.get("readMethod") == "full-text" and sid not in m and s.get("url", "").startswith("http")]
    if a.only:
        todo = [(sid, s) for sid, s in todo if sid.startswith(a.only)]
    print(f"取得する資料: {len(todo)} 件")
    fails = {}
    for i, (sid, s) in enumerate(todo, 1):
        url = s["url"]
        ok = False
        for attempt in range(3):
            try:
                data, final, status, ctype = fetch(url)
                if len(data) < 200 and b"429" in data[:50]:
                    raise urllib.error.HTTPError(url, 429, "rate limited", {}, None)
                meta = store(sid, data, url, final, status, ctype, "urllib(backfill)", "")
                print(f"[{i}/{len(todo)}] 保存 {sid} {meta['size']}バイト 本文{meta['textChars']}字 スキャン={meta['scannedImagesOnly']}")
                ok = True
                break
            except urllib.error.HTTPError as e:
                err = f"HTTP {e.code}"
                if e.code == 429:
                    time.sleep(30 * (attempt + 1))
                    continue
                break
            except Exception as e:  # 接続できない、など
                err = type(e).__name__ + ": " + str(e)[:120]
                time.sleep(3)
        if not ok:
            fails[sid] = {"url": url, "error": err, "date": date.today().isoformat()}
            print(f"[{i}/{len(todo)}] 失敗 {sid}: {err}")
        time.sleep(a.delay)
    if fails:
        path = ROOT / "docs" / "source-archive-failures.json"
        old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        old.update(fails)
        path.write_text(json.dumps(dict(sorted(old.items())), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"失敗 {len(fails)} 件 → docs/source-archive-failures.json")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("add")
    p.add_argument("id")
    p.add_argument("url")
    p.add_argument("--note")
    p.set_defaults(fn=cmd_add)
    p = sub.add_parser("import")
    p.add_argument("id")
    p.add_argument("file")
    p.add_argument("url")
    p.add_argument("--note")
    p.add_argument("--extra", nargs="*")
    p.set_defaults(fn=cmd_import)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    sub.add_parser("verify").set_defaults(fn=cmd_verify)
    p = sub.add_parser("backfill")
    p.add_argument("--only")
    p.add_argument("--delay", type=float, default=2.0)
    p.set_defaults(fn=cmd_backfill)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
