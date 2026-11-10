#!/usr/bin/env python3
"""器具カタログ(data/tools.json)を、メーカー公式のデータから作る。

目的: 設定「マイツール」の追加で、ドリッパー・ペーパー・コーヒーミルを、名前やJAN(GTIN)から選んで登録できるようにする。
方針:
  - 値は、メーカー公式のサイトから取る(販売店・まとめサイトは使わない)。取れなかった項目は、空にする(推測しない)。
  - 取得した原文(JSON)は、scripts/archive_source.py の import で、source-archive/ に保存する(資料ID: tools-<メーカー>-<日付>)。
  - JAN(GTIN)は、桁数とチェックデジットを検査し、合わないものは載せない(警告を出す)。
  - 価格は載せない(変わりやすいため)。画像も載せない(著作権)。
使い方:
  python scripts/build_tools_catalog.py hario            HARIOを取得して、data/tools.json に反映する
  python scripts/build_tools_catalog.py hario --dry-run  取得せず、対象の商品の一覧だけを出す(商品一覧の1回だけ取得)
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "tools.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
TODAY = date.today().isoformat()
DELAY = 6.0  # 秒。公式サイトへの負荷と、取得制限(429)を避ける


def get(url: str, retries: int = 12) -> bytes:
    for i in range(retries):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and i < retries - 1:
                time.sleep(min(30 * (i + 1), 180))  # 取得制限(429)は、間隔を空けて、やり直す
                continue
            raise
        except urllib.error.URLError:
            if i < retries - 1:
                time.sleep(DELAY * (i + 1))
                continue
            raise
    raise RuntimeError(url)


def valid_gtin(value: str) -> bool:
    d = re.sub(r"[\s-]", "", value or "")
    if not d.isdigit() or len(d) not in (8, 12, 13, 14):
        return False
    body = d[:-1]
    s = sum(int(c) * (3 if i % 2 == 0 else 1) for i, c in enumerate(reversed(body)))
    return (10 - s % 10) % 10 == int(d[-1])


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("　", " ")).strip()


# ---------------------------------------------------------------- HARIO(公式サイト hario.com の製品情報)
# 注意: HARIOのJAN(GTIN)は、公式オンラインショップ(shop.hariocorp.co.jp)にあるが、この環境からは取得できなかった(429)。
#       hario.com の製品ページには、JANが無い。そのため、JANは空にする(推測しない)。
HARIO_BASE = "https://www.hario.com"
HARIO_DIRS = [("dripper", "dripper"), ("paperfilter", "paper"), ("grinder", "grinder")]
HARIO_EXCLUDE = re.compile(r"ウォータードリッパー|ケース|スタンド|サーバー|ポット|ケトル|スケール|ブラシ|ボトル|アクセサリー")


def hario_blocks(text: str, series: str):
    """製品ページの本文から、「名前 品番 コード カラー 色」の並びを取り出す"""
    start = text.find("製品情報")
    body = text[start:] if start >= 0 else text
    end = min([i for i in (body.find("取り扱い説明書"), body.find("NEW PRODUCTS"), body.find("よくあるご質問 ご購入")) if i >= 0] or [len(body)])
    body = body[:end]
    out = []
    pos = 0
    for m in re.finditer(r"品番\s+(\S+)(?:\s+カラー\s+(.+?))?(?=\s+(?:製品サイズ|サイズ|口径|容量|材質|重量|メーカ))", body):
        before = body[pos:m.start()].strip()
        # 直前のブロックの末尾(食洗機・IH・直火など)より後ろが、この製品の名前
        before = re.split(r"(?:直火|ＩＨ|IH|食洗機|オーブン|電子レンジ|熱湯)\s+", before)[-1].strip()
        if series and series in before:
            before = before[before.rindex(series):]
        out.append((clean(before), m.group(1), clean(m.group(2) or "")))
        pos = m.end()
    return out


# 付属品・補助具(本体ではないもの)は、載せない
HARIO_ACCESSORY = re.compile(r"リブ|リング|Drip-Assist|セット")


def hario_items(page: dict):
    """取得した1ページ(url・kind・title・text)から、カタログの項目を作る"""
    series, text, kind = page["title"], page["text"], page["kind"]
    if HARIO_EXCLUDE.search(series):
        return []
    groups = {}
    for name, code, color in hario_blocks(text, series):
        # 名前の前に、商品説明の文が付いて長くなったものは、最後の文(。の後ろ)だけを名前にする
        if "。" in name:
            name = clean(name.rsplit("。", 1)[-1])
        if not name or HARIO_EXCLUDE.search(name) or HARIO_ACCESSORY.search(name) or len(name) > 60:
            continue
        groups.setdefault(name, []).append({"label": color, "sku": code, "gtin": ""})
    return [{
        "id": f"hario-{variants[0]['sku'].lower()}", "kind": kind, "maker": "HARIO", "name": name,
        "variants": variants, "url": page["url"], "checkedAt": TODAY,
    } for name, variants in groups.items()]


def hario(dry: bool, reuse: bool = False):
    if reuse:
        raw = json.loads(sorted((ROOT / "source-archive").glob("tools-hario-*"))[-1].joinpath("original.bin").read_text(encoding="utf-8"))["pages"]
        return {"maker": "HARIO", "sourceUrl": f"{HARIO_BASE}/product/coffee/", "raw": None, "items": [i for pg in raw for i in hario_items(pg)]}
    listing = get(f"{HARIO_BASE}/product/coffee/").decode("utf-8", errors="replace")
    pages = []
    for d, kind in HARIO_DIRS:
        urls = sorted(set(re.findall(rf'href="(/product/coffee/{d}/[^"]+\.html)"', listing)))
        pages += [(HARIO_BASE + u, kind) for u in urls]
    print(f"HARIO: 製品ページ {len(pages)} 件 (" + ", ".join(f"{d}={sum(1 for _, k in pages if k == kind)}" for d, kind in HARIO_DIRS) + ")")
    if dry:
        return None
    raw, items = [], []
    for n, (url, kind) in enumerate(pages, 1):
        time.sleep(DELAY)
        try:
            body = get(url).decode("utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001
            print(f"  取得失敗 {url}: {e}")
            continue
        text = html_text(body.encode("utf-8"))
        m = re.search(r"<title>\s*(.*?)\s*(?:\||｜)", body, flags=re.S)
        page = {"url": url, "kind": kind, "title": clean(m.group(1)) if m else "", "text": text[:12000]}
        raw.append(page)
        got = hario_items(page)
        items += got
        print(f"  [{n}/{len(pages)}] {kind:8s} {page['title']}: {len(got)}製品")
    return {"maker": "HARIO", "sourceUrl": f"{HARIO_BASE}/product/coffee/", "raw": {"pages": raw}, "items": items}


# ---------------------------------------------------------------- Kalita(カリタ。公式サイトの商品ページ)
KALITA_BASE = "https://www.kalita.co.jp"
# 一覧のページ(種類の見当)。製品ページは /products/<一覧>/<番号>
KALITA_LISTS = [("dripper", "dripper"), ("coffeefilter", "paper"), ("mill", "grinder"), ("waveseries", None)]
KALITA_EXCLUDE = re.compile(r"セット|サーバー|ポット|スタンド|ケース|ブラシ|スケール|ケトル|スプーン|メジャー|ヤグラ|ホルダー|ネル|ろ布|濾布|業務用|ケーキ")


def html_text(raw: bytes) -> str:
    import html as _html
    t = raw.decode("utf-8", errors="replace")
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", t, flags=re.S)
    t = _html.unescape(re.sub(r"<[^>]+>", " ", t))
    return re.sub(r"\s+", " ", t)


KIND_NOUN = {"dripper": "ドリッパー", "paper": "ペーパーフィルター", "grinder": "コーヒーミル"}


def kalita_kind(title: str, text: str, hint):
    """種類を決める。決められないものは None(載せない)"""
    if KALITA_EXCLUDE.search(title) or "ウェーブスタイル" in title or re.search(r"GO-?BREW", title, flags=re.I):
        return None
    if re.search(r"濾紙|ろ紙|フィルター|ペーパー", title) and "ドリッパー" not in title:
        return "paper"
    if re.search(r"ドリッパー", title):
        return "dripper"
    if re.search(r"ミル|グラインダー", title):
        return "grinder"
    # ウェーブシリーズの本体(WDG・WDC・WDS)は、ページに「ウェーブフィルター…専用」とある
    if re.match(r"WD[A-Z]-\d+", title) and "ウェーブフィルター" in text and "専用" in text:
        return "dripper"
    return hint if hint and not re.search(r"スタンド|ポット", title) else None


def kalita_parse(page: dict, hint):
    """取得した1ページ(url・title・productCode・jan・text)から、カタログの1件を作る。載せないものは None"""
    title, text = page["title"], page["text"]
    kind = kalita_kind(title, text, hint) if title else None
    if not kind:
        return None
    m = re.search(r"ホーム >\s*(.*?)\s*-->", text)
    category = clean(m.group(1)) if m else ""
    # 型番だけの題名(例: 102-D)には、種類の名前を前に付ける(公式の分類の語: ブレッドクラムの「コーヒードリッパー」など)
    name = title if re.search(r"ドリッパー|濾紙|ろ紙|フィルター|ペーパー|ミル|グラインダー", title) else f"{KIND_NOUN[kind]} {title}"
    return {
        "id": f"kalita-{page['url'].rsplit('/', 1)[-1]}", "kind": kind, "maker": "Kalita", "name": name, "category": category,
        "variants": [{"label": "", "sku": page.get("productCode", ""), "gtin": page.get("jan", "")}], "url": page["url"], "checkedAt": TODAY,
    }


def kalita(dry: bool, reuse: bool = False):
    hints = dict(KALITA_LISTS)
    if reuse:
        # 取得済みの原文(source-archive)から作り直す。サイトには、アクセスしない
        raw = json.loads(sorted((ROOT / "source-archive").glob("tools-kalita-*"))[-1].joinpath("original.bin").read_text(encoding="utf-8"))["pages"]
        items = []
        for page in raw:
            lst = re.search(r"/products/([a-z]+)/", page["url"]).group(1)
            item = kalita_parse(page, hints.get(lst))
            if item:
                items.append(item)
        return {"maker": "Kalita", "sourceUrl": f"{KALITA_BASE}/products/", "raw": None, "items": items}
    pages = []  # (url, 一覧の名前)
    seen = set()
    for lst, hint in KALITA_LISTS:
        time.sleep(DELAY)
        body = get(f"{KALITA_BASE}/products/{lst}/").decode("utf-8", errors="replace")
        for m in re.finditer(rf"/products/{lst}/(\d+)", body):
            if m.group(1) not in seen:
                seen.add(m.group(1))
                pages.append((f"{KALITA_BASE}/products/{lst}/{m.group(1)}", hint))
        print(f"Kalita: 一覧 {lst} 累計 {len(pages)} ページ")
    if dry:
        return None
    raw, items = [], []
    for n, (url, hint) in enumerate(pages, 1):
        time.sleep(DELAY)
        try:
            body = get(url)
        except Exception as e:  # noqa: BLE001
            print(f"  取得失敗 {url}: {e}")
            continue
        text = html_text(body)
        m = re.search(r"<title>\s*(.*?)\s*(?:\||｜)", body.decode("utf-8", errors="replace"), flags=re.S)
        code = re.search(r"商品コード[:：]\s*([0-9A-Za-z-]+)", text)
        jan = re.search(r"JANコード[:：]\s*([0-9 ]{8,20})", text)
        gtin = re.sub(r"\s", "", jan.group(1)) if jan else ""
        if gtin and not valid_gtin(gtin):
            print(f"  警告: {url} のJANが不正のため載せません: {gtin}")
            gtin = ""
        page = {"url": url, "title": clean(m.group(1)) if m else "", "productCode": code.group(1) if code else "", "jan": gtin, "text": text[:3000]}
        raw.append(page)
        item = kalita_parse(page, hint)
        print(f"  [{n}/{len(pages)}] {item['kind'] if item else '対象外':8s} {page['title']} JAN={gtin or '-'}")
        if item:
            items.append(item)
    return {"maker": "Kalita", "sourceUrl": f"{KALITA_BASE}/products/", "raw": {"pages": raw}, "items": items}


# 検索用: メーカー名の日本語の読み
MAKER_ALIAS = {"HARIO": "ハリオ", "Kalita": "カリタ"}

MAKERS = {"hario": hario, "kalita": kalita}


def save_raw(maker_key: str, result: dict) -> str:
    """取得した原文(JSON)を、source-archive/ に保存する。資料IDを返す"""
    source_id = f"tools-{maker_key}-{TODAY}"
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(result["raw"], f, ensure_ascii=False)
        path = f.name
    subprocess.run(
        [sys.executable, "-X", "utf8", str(ROOT / "scripts" / "archive_source.py"), "import", source_id, path, result["sourceUrl"],
         "--note", "メーカー公式サイトの商品データ(JSON)。器具カタログ(data/tools.json)の根拠"],
        check=True,
    )
    return source_id


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("maker", choices=sorted(MAKERS))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--reuse", action="store_true", help="取得済みの原文(source-archive)から作り直す。サイトにはアクセスしない(Kalitaのみ)")
    a = ap.parse_args()
    result = MAKERS[a.maker](a.dry_run, a.reuse) if a.reuse else MAKERS[a.maker](a.dry_run)
    if result is None:
        return
    source_id = save_raw(a.maker, result) if result["raw"] is not None else sorted(p.name for p in (ROOT / "source-archive").glob(f"tools-{a.maker}-*"))[-1]
    catalog = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"version": 1, "items": []}
    # 同じメーカーの項目は、入れ替える(他のメーカーは、そのまま)
    catalog["items"] = [i for i in catalog["items"] if i["maker"] != result["maker"]]
    for item in result["items"]:
        item["sourceId"] = source_id
        if result["maker"] in MAKER_ALIAS:
            item["makerAlias"] = MAKER_ALIAS[result["maker"]]  # 検索用の読み(カタカナ)
    catalog["items"] += result["items"]
    catalog["items"].sort(key=lambda i: (i["maker"], i["kind"], i["name"]))
    catalog["updatedAt"] = TODAY
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(catalog, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"保存: {OUT}  (合計 {len(catalog['items'])} 件)")


if __name__ == "__main__":
    main()
