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
  python scripts/build_tools_catalog.py hario --dry-run  取得せず、対象の商品の一覧だけを出す
  python scripts/build_tools_catalog.py hario-shop|timemore|fellow|origami  Shopify製の公式ショップから、JANを取る(docs/tool-catalog.md)
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
                wait = min(30 * (i + 1), 180)
                print(f"  取得制限({e.code})のため、{wait}秒待ってから、やり直します(止めずに、お待ちください)", flush=True)
                time.sleep(wait)  # 取得制限は、間隔を空けて、やり直す
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
        raw = json.loads(sorted((ROOT / "source-archive").glob("tools-hario-2*"))[-1].joinpath("original.bin").read_text(encoding="utf-8"))["pages"]
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


# ---------------------------------------------------------------- Melitta(メリタジャパン。公式サイトの製品ページ。家庭用)
MELITTA_BASE = "https://www.melitta.co.jp"
MELITTA_DIRS = [("pourover", "dripper"), ("paper", "paper"), ("coffeegrinder", "grinder")]
MELITTA_EXCLUDE = re.compile(r"ケトル|サーバー|ポット|セット|スケール|ブラシ|ミルク")
SPEC_LABELS = ["製品名", "型番", "品目コード", "JAN", "容量", "寸法", "本体質量", "カラー", "付属品", "そのほか", "関連製品", "材質", "原産国", "サイズ", "質量"]


def melitta_spec(html_body: str):
    """製品ページの「スペック」の表を、{項目名: 値の文字列} にする。無ければ None"""
    import html as _html
    i = html_body.find("スペック")
    if i < 0:
        return None
    seg = re.sub(r"<script.*?</script>|<style.*?</style>", "", html_body[i:i + 9000], flags=re.S)
    toks = [clean(t) for t in re.split(r"\s*\|\s*", _html.unescape(re.sub(r"<[^>]+>", " | ", seg))) if clean(t)]
    spec, cur = {}, None
    for tok in toks:
        if tok == "スペック" or tok == "-->":
            continue
        if tok in SPEC_LABELS:
            cur = tok
            spec.setdefault(cur, [])
        elif cur:
            spec[cur].append(tok)
        if tok == "関連製品":
            break
    return {k: v for k, v in spec.items()}


def melitta_items(page: dict):
    spec, kind = page.get("spec"), page["kind"]
    if not spec or not spec.get("製品名"):
        return []
    name = clean(" ".join(spec["製品名"]))  # 製品名が2つの語に分かれている製品がある(例: フラットカッターディスク コーヒーグラインダー)
    if MELITTA_EXCLUDE.search(name):
        return []

    def keyed(label):
        out = {}
        toks = spec.get(label, [])
        if label == "JAN":  # JANの欄の後ろに、電源・消費電力などが続くことがある。数字(または「型: 数字」)だけを取る
            toks = [t for t in toks if re.match(r"^(?:[^:：]{1,12}[:：]\s*)?[0-9 ]{8,16}$", t)]
        if label == "カラー":  # カラーの欄の後ろに、電源・消費電力が続くことがある
            toks = toks[: toks.index("電源")] if "電源" in toks else toks
        for tok in toks:
            m = re.match(r"^([^:：]{1,12})[:：]\s*(.+)$", tok)
            out[m.group(1) if m else ""] = (m.group(2) if m else tok)
        return out

    models, jans, colors = keyed("型番"), keyed("JAN"), keyed("カラー")
    keys = list(dict.fromkeys(list(models) + list(jans)))
    variants = []
    for k in keys or [""]:
        gtin = re.sub(r"\D", "", jans.get(k, jans.get("", "")) if k in jans or "" in jans else "")
        if gtin and not valid_gtin(gtin):
            print(f"  警告: {page['url']} のJANが不正のため載せません: {gtin}")
            gtin = ""
        label = k or colors.get("", "")
        variants.append({"label": label, "sku": models.get(k, models.get("", "")), "gtin": gtin})
    return [{
        "id": "melitta-" + page["url"].rstrip("/").rsplit("/", 1)[-1], "kind": kind, "maker": "Melitta", "name": name,
        "variants": variants, "url": page["url"], "checkedAt": TODAY,
    }]


def melitta(dry: bool, reuse: bool = False):
    if reuse:
        raw = json.loads(sorted((ROOT / "source-archive").glob("tools-melitta-*"))[-1].joinpath("original.bin").read_text(encoding="utf-8"))["pages"]
        return {"maker": "Melitta", "sourceUrl": f"{MELITTA_BASE}/melitta_hh/", "raw": None, "items": [i for pg in raw for i in melitta_items(pg)]}
    pages = []
    for d, kind in MELITTA_DIRS:
        time.sleep(DELAY)
        body = get(f"{MELITTA_BASE}/melitta_hh/{d}/").decode("utf-8", errors="replace")
        slugs = sorted(set(re.findall(rf'href="{re.escape(MELITTA_BASE)}/melitta_hh/{d}/([a-z0-9_]+)/"', body)) - {"feed"})
        pages += [(f"{MELITTA_BASE}/melitta_hh/{d}/{sl}/", kind) for sl in slugs]
        print(f"Melitta: {d} 累計 {len(pages)} ページ")
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
        page = {"url": url, "kind": kind, "spec": melitta_spec(body)}
        raw.append(page)
        got = melitta_items(page)
        items += got
        print(f"  [{n}/{len(pages)}] {kind:8s} {url.rsplit('/', 2)[-2]}: {', '.join(g['name'] + '×' + str(len(g['variants'])) for g in got) or '対象外/表なし'}")
    return {"maker": "Melitta", "sourceUrl": f"{MELITTA_BASE}/melitta_hh/", "raw": {"pages": raw}, "items": items}


# ---------------------------------------------------------------- 1Zpresso(公式サイト 1zpresso.coffee。手挽きミル)
# 公式サイトには、型番・JANの表が無く、機種名は、各シリーズのページの見出しにある。
# そのため、「機種名と、それが書かれているページ・文言」の対応を、ここに書き、取得したページに、その文言が実際にあることを確かめてから載せる
# (記憶や他のサイトの情報で、機種を足さない)。JANは、公式サイトに無いため、空にする。
Z1_BASE = "https://1zpresso.coffee"
# (機種名, ページ, ページに書かれている文言)
Z1_MODELS = [
    ("Diamond A", "diamond-a", "Diamond A"),
    ("JX", "j", "JX Series ( JX / JX S / J )"),
    ("JX S", "j", "JX Series ( JX / JX S / J )"),
    ("J", "j", "JX Series ( JX / JX S / J )"),
    ("J-Ultra", "j-ultra", "J-Ultra Grinder"),
    ("K-Pro", "k", "K-Pro Grinder"),
    ("K-Max", "k", "K-Max Grinder"),
    ("K-Plus", "k", "K-Plus Grinder"),
    ("K-Ultra", "k-ultra", "K-Ultra Grinder"),
    ("X-Ultra", "x", "X-Ultra Grinder"),
    ("ZP6 Special", "manual-coffee-grinder", "ZP6 Special"),
]


def z1presso_items(pages: dict):
    items = []
    for model, slug, phrase in Z1_MODELS:
        page = pages.get(slug)
        if not page or phrase not in page["text"]:
            print(f"  警告: {model}: ページ {slug} に「{phrase}」が見つからないため、載せません")
            continue
        items.append({
            "id": "1zpresso-" + re.sub(r"[^a-z0-9]+", "-", model.lower()).strip("-"), "kind": "grinder", "maker": "1Zpresso",
            "name": f"1Zpresso {model}", "variants": [{"label": "", "sku": "", "gtin": ""}],
            "url": f"{Z1_BASE}/{slug}/", "checkedAt": TODAY,
        })
    return items


def z1presso(dry: bool, reuse: bool = False):
    if reuse:
        raw = json.loads(sorted((ROOT / "source-archive").glob("tools-1zpresso-*"))[-1].joinpath("original.bin").read_text(encoding="utf-8"))["pages"]
        return {"maker": "1Zpresso", "sourceUrl": f"{Z1_BASE}/", "raw": None, "items": z1presso_items({p["slug"]: p for p in raw})}
    slugs = list(dict.fromkeys(sl for _, sl, _ in Z1_MODELS))
    print(f"1Zpresso: ページ {len(slugs)} 件")
    if dry:
        return None
    raw = []
    for sl in slugs:
        time.sleep(DELAY)
        raw.append({"slug": sl, "url": f"{Z1_BASE}/{sl}/", "text": html_text(get(f"{Z1_BASE}/{sl}/"))[:20000]})
    return {"maker": "1Zpresso", "sourceUrl": f"{Z1_BASE}/", "raw": {"pages": raw}, "items": z1presso_items({p["slug"]: p for p in raw})}


# ---------------------------------------------------------------- Shopify製の公式ショップ(HARIO・TIMEMORE・Fellow・ORIGAMI)
# Shopifyの公式ショップは、商品の一覧(/products.json)と、商品ごとのデータ(/products/<ハンドル>.js)を公開している。
# JAN(GTIN)は、後者の variants[].barcode にある(店が入力した、型番ごとの値)。
# 注意: 取得の間隔が短いと、取得制限(429)がかかる。この環境(作業用の端末)では、取得できないことがあった。利用者のPCで実行する。
SHOPIFY_DELAY = 2.0
# hario.com(公式サイト)と公式ショップで、同じ製品の型番の書き方が違うもの(hario.comの型番 → ショップの型番)
HARIO_SKU_ALIAS = {"VDSU-02-B＆W": "VDSU-02-BAW"}


def shopify_kind_en(p: dict):
    """英語の商品名から、種類を決める。決められないものは None(載せない)"""
    title = f"{p.get('title', '')} {p.get('product_type', '')}"
    # 本体ではないもの(付属品・交換部品・セット・中古品など)は、載せない
    if re.search(r"kettle|server|\bscale\b|brush|\bmug\b|\bcup\b|carafe|tumbler|bottle|\bbag\b|\bcover\b|\bcase\b|\bstand\b|holder|plate|\btool\b|cleaning|replacement|spare|burr set|gift|bundle|\bset\b|subscription|\bused\b|refurb|open[- ]box|\bdemo\b|\blamp\b|\blight\b|pendant|\btea\b", title, flags=re.I):
        return None
    if re.search(r"filter paper|paper filter|filter papers|filters?\b.*(paper|pack|pcs|sheets)|(paper|disposable).*filter", title, flags=re.I) and not re.search(r"metal|steel|cloth", title, flags=re.I):
        return "paper"
    if re.search(r"dripper|pour[- ]?over cone", title, flags=re.I):
        return "dripper"
    if re.search(r"grinder|coffee mill|\bmill\b", title, flags=re.I):
        return "grinder"
    return None


# HARIOの公式ショップの商品名(日本語)から、種類を決める。本体ではないもの・別の用途のものは、除く
HARIO_SHOP_EXCLUDE = re.compile(r"セット|サーバー|ケース|スタンド|ポット|ウォータードリッパー|スケール|ケトル|ボトル|ブラシ|リブ|リング|Drip-Assist")


def hario_kind(title: str):
    if HARIO_SHOP_EXCLUDE.search(title):
        return None
    if re.search(r"ペーパーフィルター|フィルターペーパー", title):
        return "paper"
    if re.search(r"ドリッパー", title) and not re.search(r"グラインダー|ミル", title):
        return "dripper"
    if re.search(r"ミル|グラインダー", title):
        return "grinder"
    return None


def shopify_kind_hario(p: dict):
    return hario_kind(clean(p.get("title", "")))


def shopify_kind_aeropress(p: dict):
    """小川珈琲オンラインショップの商品のうち、エアロプレス(AeroPress)の本体と専用フィルターだけを載せる"""
    title = clean(p.get("title", ""))
    if not re.search(r"エアロプレス|aeropress", title, flags=re.I):
        return None
    if re.search(r"ケース|スタンド|ブラシ|ポーチ|バッグ|ケトル|ミル|グラインダー|スケール|クリーナー|ストレーナー|ステンレス|メタル|キャップ|セット|used|中古|シール|カラフェ|フローコントロール|おすすめ|選べる|コーヒー豆|ギフト", title, flags=re.I):
        return None
    if re.search(r"フィルター|ペーパー|filter", title, flags=re.I):
        return "paper"
    return "aeropress"


SHOPIFY = {
    # 小川珈琲オンラインショップ(販売店)。エアロプレスだけを載せる。JANは、店が入力した値(メーカーの公式の値ではない)
    "ogawa": dict(maker="AeroPress", base="https://oc-shop.co.jp", kind=shopify_kind_aeropress, merge=None, collection="coffee-goods"),
    "hario-shop": dict(maker="HARIO", base="https://shop.hariocorp.co.jp", kind=shopify_kind_hario, merge="sku", collection="coffee"),
    "timemore": dict(maker="TIMEMORE", base="https://www.timemore.com", kind=shopify_kind_en, merge=None),
    "fellow": dict(maker="Fellow", base="https://fellowproducts.com", kind=shopify_kind_en, merge=None),
    "origami": dict(maker="ORIGAMI", base="https://origami-kai.com", kind=shopify_kind_en, merge=None),
}


def shopify_items(cfg: dict, records: list):
    """records: [{"handle", "kind", "js": 商品の.jsのデータ}] からカタログの項目を作る"""
    items = []
    for rec in records:
        js = rec["js"]
        variants = []
        for v in js.get("variants", []):
            gtin = re.sub(r"[\s-]", "", v.get("barcode") or "")
            if gtin and not valid_gtin(gtin):
                print(f"  警告: {rec['handle']} {v.get('sku')} のJANが不正のため載せません: {gtin}")
                gtin = ""
            label = clean(v.get("title", ""))
            sku = clean(v.get("sku") or "")
            variant = {"label": "" if label == "Default Title" else label, "sku": sku, "gtin": gtin}
            # barcode(JAN)が空でも、型番(sku)が、桁数とチェックデジットの合うバーコードの数字のとき(店が、型番にJANを入れている)は、その数字を、JANとして使う。印を付ける
            if not gtin and re.fullmatch(r"\d{12,13}", sku) and valid_gtin(sku):
                variant["gtin"] = sku
                variant["gtinFrom"] = "sku"
            variants.append(variant)
        if not variants:
            continue
        items.append({
            "id": f"{cfg['maker'].lower()}-shop-{rec['handle']}", "kind": rec["kind"], "maker": cfg["maker"], "name": clean(js.get("title", "")),
            "variants": variants, "url": f"{cfg['base']}/products/{rec['handle']}", "checkedAt": TODAY,
        })
    return items


def shopify_list(cfg: dict):
    """商品の一覧を、全ページ取得する"""
    out, page = [], 1
    # コレクションを指定できるメーカー(HARIO)は、その一覧だけを取る(全商品のページ送りは、取得制限がかかりやすい)
    path = f"/collections/{cfg['collection']}/products.json" if cfg.get("collection") else "/products.json"
    while page <= 30:
        data = json.loads(get(f"{cfg['base']}{path}?limit=250&page={page}"))["products"]
        if not data:
            break
        out += data
        print(f"  一覧 {page}ページ目: 累計 {len(out)} 件")
        if len(data) < 250:
            break
        page += 1
        time.sleep(6)  # ページの間は、長めに空ける
    return out


def shopify(key: str):
    cfg = SHOPIFY[key]

    def run(dry: bool, reuse: bool = False, from_file=None):
        if from_file:
            # ブラウザ(scripts/shopify-export.js)で書き出したファイルから作る。種類の判定と除外は、ここ(Python)で行う
            exported = json.loads(Path(from_file).read_text(encoding="utf-8"))
            records = []
            for rec in exported["records"]:
                js = rec["js"]
                kind = cfg["kind"]({"title": js.get("title", ""), "product_type": js.get("type", "")})
                if kind:
                    records.append({"handle": rec["handle"], "kind": kind, "js": js})
            print(f"{cfg['maker']}: ファイルの {len(exported['records'])} 件のうち、対象 {len(records)} 件")
            for r in records:
                print(f"  {r['kind']:8s} {r['handle']}  {clean(r['js'].get('title', ''))}  JAN {sum(1 for v in r['js'].get('variants', []) if v.get('barcode'))}/{len(r['js'].get('variants', []))}")
            if dry:
                return None
            return {"maker": cfg["maker"], "sourceUrl": cfg["base"] + "/", "raw": {"records": records}, "items": shopify_items(cfg, records), "merge": cfg["merge"]}
        if reuse:
            raw = json.loads(sorted((ROOT / "source-archive").glob(f"tools-{key}-2*"))[-1].joinpath("original.bin").read_text(encoding="utf-8"))["records"]
            return {"maker": cfg["maker"], "sourceUrl": cfg["base"] + "/", "raw": None, "items": shopify_items(cfg, raw), "merge": cfg["merge"]}
        listing = shopify_list(cfg)
        picked = [(p["handle"], cfg["kind"](p)) for p in listing]
        picked = [(h, k) for h, k in picked if k]
        print(f"{cfg['maker']}: 商品 {len(listing)} 件のうち、対象 {len(picked)} 件")
        titles = {p["handle"]: p.get("title", "") for p in listing}
        for h, k in picked:
            print(f"  {k:8s} {h}  {clean(titles[h])}")
        if dry:
            return None
        records = []
        for n, (handle, kind) in enumerate(picked, 1):
            time.sleep(SHOPIFY_DELAY)
            try:
                js = json.loads(get(f"{cfg['base']}/products/{handle}.js"))
            except Exception as e:  # noqa: BLE001
                print(f"  取得失敗 {handle}: {e}")
                continue
            records.append({"handle": handle, "kind": kind, "js": js})
            print(f"  [{n}/{len(picked)}] {handle}: JAN {sum(1 for v in js.get('variants', []) if v.get('barcode'))}/{len(js.get('variants', []))}")
        return {"maker": cfg["maker"], "sourceUrl": cfg["base"] + "/", "raw": {"records": records}, "items": shopify_items(cfg, records), "merge": cfg["merge"]}

    return run


# ---------------------------------------------------------------- 珈琲サイフオン(コーノ式。公式サイト coffee-syphon.co.jp)
# 公式サイトの商品ページは、CSV(/csv/<ページ名>.csv)を読み込んで表示している。そのCSVを取る。
# CSVの「jan」の列は、6桁の数字(例: 421319)で、13桁のJANではない。完全なJANが分からないため、gtinは空にする(推測しない)。
SYPHON_BASE = "https://coffee-syphon.co.jp"
SYPHON_PAGES = ["coffee_syphon", "meimon_filter"]
# (カテゴリー, サブカテゴリー) → 種類。それ以外(ロート・フラスコ・グラスポット・計量カップなどの部品)は、載せない
SYPHON_KINDS = {
    ("コーヒーサイフォン", "サイフォンセット"): "syphon",
    ("名門フィルター", "名門ドリッパーセット"): "dripper",
    ("名門フィルター", "ペーパーフィルター"): "paper",
}


def syphon_items(csvs: dict):
    import csv as _csv
    import io
    items = []
    for page, text in csvs.items():
        for row in _csv.DictReader(io.StringIO(text)):
            kind = SYPHON_KINDS.get((row.get("category", ""), row.get("subCategory", "")))
            if not kind or not row.get("id") or not row.get("name"):
                continue
            items.append({
                "id": "kono-" + re.sub(r"[^a-z0-9]+", "-", row["id"].lower()).strip("-"), "kind": kind, "maker": "珈琲サイフオン",
                "name": clean(row["name"]), "category": clean(f"{row['category']} {row['subCategory']} {row.get('categoryClass', '')}"),
                "variants": [{"label": "", "sku": row["id"].strip(), "gtin": "", "siteCode": (row.get("jan") or "").strip()}],
                "url": f"{SYPHON_BASE}/{page}/", "checkedAt": TODAY,
            })
    return items


def coffee_syphon(dry: bool, reuse: bool = False):
    if reuse:
        raw = json.loads(sorted((ROOT / "source-archive").glob("tools-coffee-syphon-2*"))[-1].joinpath("original.bin").read_text(encoding="utf-8"))["csv"]
        return {"maker": "珈琲サイフオン", "sourceUrl": f"{SYPHON_BASE}/", "raw": None, "items": syphon_items(raw)}
    csvs = {}
    for page in SYPHON_PAGES:
        time.sleep(DELAY)
        csvs[page] = get(f"{SYPHON_BASE}/csv/{page}.csv").decode("utf-8-sig")
        print(f"珈琲サイフオン: {page}.csv {len(csvs[page].splitlines())}行")
    items = syphon_items(csvs)
    print(f"珈琲サイフオン: 対象 {len(items)} 件 (" + ", ".join(f"{k}={sum(1 for i in items if i['kind'] == k)}" for k in ('syphon', 'dripper', 'paper')) + ")")
    if dry:
        return None
    return {"maker": "珈琲サイフオン", "sourceUrl": f"{SYPHON_BASE}/", "raw": {"csv": csvs}, "items": items}


# ---------------------------------------------------------------- ボダム(Bodum。公式オンラインショップ www.bodum.com/jp/ja)
# 商品ページに、「商品番号」と「EAN」が表示される。ただし、ページはスクリプトで描画され、データは、サイトの内部のAPIから取る作りのため、
# このスクリプトは、サイトにはアクセスしない。ブラウザで商品ページを開いて、表示されている値を読み取った記録(tools-bodum.json)から作る。
# 使い方: py -X utf8 scripts/build_tools_catalog.py bodum --from-file tools-bodum.json
def bodum(dry: bool, reuse: bool = False, from_file=None):
    if from_file:
        exported = json.loads(Path(from_file).read_text(encoding="utf-8"))
        records = exported["records"]
    elif reuse:
        records = json.loads(sorted((ROOT / "source-archive").glob("tools-bodum-2*"))[-1].joinpath("original.bin").read_text(encoding="utf-8"))["records"]
        exported = None
    else:
        raise SystemExit("bodum は、ブラウザで読み取った記録のファイルから作ります: --from-file tools-bodum.json")
    items = []
    for r in records:
        ean = re.sub(r"[\s-]", "", r.get("ean") or "")
        if ean and not valid_gtin(ean):
            print(f"  警告: {r['sku']} のEANが不正のため載せません: {ean}")
            ean = ""
        line = clean((r.get("line") or "").replace("®", ""))
        items.append({
            "id": "bodum-" + re.sub(r"[^a-z0-9]+", "-", r["sku"].lower()).strip("-"), "kind": "frenchpress", "maker": "Bodum",
            "name": clean(f"{line} {r.get('subtitle', '')}"),
            "variants": [{"label": r.get("color") or "", "sku": r["sku"], "gtin": ean}],
            "url": r["url"], "checkedAt": TODAY,
        })
    print(f"Bodum: {len(items)} 商品 / EANあり {sum(1 for i in items if i['variants'][0]['gtin'])}")
    if dry:
        return None
    return {"maker": "Bodum", "sourceUrl": "https://www.bodum.com/jp/ja/", "raw": ({"records": records, "note": exported.get("note", "")} if exported else None), "items": items}


# ---------------------------------------------------------------- Comandante(コマンダンテ。販売店 Crema(cremashop.eu。エストニア)の商品ページ)
# Comandante公式サイトは、この環境から取得できなかった(403)。利用者が指定した販売店 Crema の商品ページを使う。
# 販売店のため、JANは、店が入力した値(schema.org の gtin13)。Crema の「商品番号」は、メーカーの型番ではない(店の番号)。
CREMA_BASE = "https://www.cremashop.eu"


def crema_parse(page: dict):
    """商品ページ(url・html の要約)から、カタログの項目を作る。page: {"url", "product"(JSON-LD), "names"(商品番号→表示名)}"""
    prod = page["product"]
    offers = prod.get("offers") or []
    groups = {}
    for o in offers:
        sku = str(o.get("sku", ""))
        full = clean(page["names"].get(sku) or prod.get("name", ""))
        base, _, label = full.rpartition(", ")
        if not base:
            base, label = full, ""
        gtin = re.sub(r"[\s-]", "", str(o.get("gtin13") or o.get("gtin") or ""))
        if gtin and not valid_gtin(gtin):
            print(f"  警告: Crema {sku} のJANが不正のため載せません: {gtin}")
            gtin = ""
        g = groups.setdefault(base, {"url": o.get("url") or page["url"], "first": sku, "variants": []})
        g["variants"].append({"label": label, "sku": f"Crema {sku}", "gtin": gtin})
    return [{
        "id": f"comandante-{g['first']}", "kind": "grinder", "maker": "Comandante", "name": base,
        "variants": g["variants"], "url": g["url"], "checkedAt": TODAY,
    } for base, g in groups.items()]


def crema_comandante(dry: bool, reuse: bool = False):
    if reuse:
        raw = json.loads(sorted((ROOT / "source-archive").glob("tools-crema-comandante-2*"))[-1].joinpath("original.bin").read_text(encoding="utf-8"))["pages"]
        return {"maker": "Comandante", "sourceUrl": f"{CREMA_BASE}/en/shop-by-brand/comandante", "raw": None, "items": [i for pg in raw for i in crema_parse(pg)]}
    brand = get(f"{CREMA_BASE}/en/shop-by-brand/comandante").decode("utf-8", errors="replace")
    links = sorted(set(re.findall(r'href="(/en/products/comandante/((?:c40|c60)-[a-z0-9-]+)/(\d+))"', brand)))
    slugs = {}
    for path, slug, pid in links:
        slugs.setdefault(slug, path)  # 同じ商品名の変種は、1ページに全部載っている。最初の1つだけ取る
    print(f"Comandante(Crema): グラインダーの商品ページ {len(slugs)} 件: {', '.join(slugs)}")
    if dry:
        return None
    pages = []
    for slug, path in slugs.items():
        time.sleep(DELAY)
        body = get(CREMA_BASE + path).decode("utf-8", errors="replace")
        product = None
        for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', body, flags=re.S):
            try:
                d = json.loads(m.group(1))
            except ValueError:
                continue
            if d.get("@type") == "Product":
                product = d
        if not product:
            print(f"  警告: {path}: 商品データ(JSON-LD)が見つかりません")
            continue
        # 変種の名前は、商品番号が入った、画像の説明文(data-caption)・画像の代替文(alt)・リンクから取る(順番では対応づけない)。
        # 例: data-caption="Comandante C60 Baracuda Coffee Grinder, Nautilus Blue"(画像のファイル名に商品番号 13381 が入る)
        names = {}
        for o in product.get("offers") or []:
            sku = str(o.get("sku"))
            cands = []
            for m in re.finditer(r'(?:data-caption|alt)="([^"]+)"', body):
                # その属性を持つタグの中(前後の400字)に、「/<商品番号>-」を含む画像のファイル名か、/<商品番号>" のリンクがあるもの
                ctx = body[max(0, m.start() - 400): m.end() + 400]
                if re.search(r"/" + re.escape(sku) + r"[-\"]", ctx):
                    cands.append(clean(__import__("html").unescape(m.group(1))))
            cands = [c for c in cands if ", " in c and "€" not in c and c.startswith("Comandante")]
            if cands:
                names[sku] = max(set(cands), key=cands.count)
        pages.append({"url": CREMA_BASE + path, "product": product, "names": names})
        print(f"  {slug}: 変種 {len(product.get('offers') or [])}")
    items = [i for pg in pages for i in crema_parse(pg)]
    return {"maker": "Comandante", "sourceUrl": f"{CREMA_BASE}/en/shop-by-brand/comandante", "raw": {"pages": pages}, "items": items}


# ---------------------------------------------------------------- Comandante X25 Trailmaster Dune(複数の販売店のページで、同じEANを確認したもの)
# Crema(cremashop.eu)の一覧には、X25が載っていない。2つの販売店のページに、同じEANがあることを、取得して確かめてから載せる。
X25_SOURCES = [
    ("wb.coffee", "https://www.wb.coffee/shop/comandante-x25-trailmaster-dune-50234", "4260113437605"),
    ("MaxiCoffee", "https://maxicoffee.com/en-eu/coffee-grinder-x25-trailmaster-dune-comandante-p-146419.html", "4260113437605"),
]


def comandante_x25(dry: bool, reuse: bool = False):
    pages = []
    for shop, url, ean in X25_SOURCES:
        time.sleep(DELAY)
        body = get(url).decode("utf-8", errors="replace")
        i = body.find(ean)
        if i < 0:
            print(f"  警告: {shop}: ページに {ean} が見つかりません")
            continue
        pages.append({"shop": shop, "url": url, "ean": ean, "excerpt": clean(re.sub(r"<[^>]+>", " ", body[max(0, i - 200): i + 120]))})
        print(f"  {shop}: EAN {ean} を確認")
    if dry:
        return None
    eans = {pg["ean"] for pg in pages}
    if len(pages) < 2 or len(eans) != 1:
        raise SystemExit("2か所以上の販売店で、同じEANを確認できなかったため、載せません")
    ean = eans.pop()
    if not valid_gtin(ean):
        raise SystemExit(f"EANのチェックデジットが合いません: {ean}")
    item = {"id": "comandante-x25-trailmaster-dune", "kind": "grinder", "maker": "Comandante", "name": "Comandante X25 Trailmaster Hand Coffee Grinder",
            "variants": [{"label": "Dune", "sku": "", "gtin": ean}], "url": pages[0]["url"], "checkedAt": TODAY}
    return {"maker": "Comandante", "sourceUrl": pages[0]["url"], "raw": {"pages": pages}, "items": [item], "merge": "add"}


# 検索用: メーカー名の日本語の読み
MAKER_ALIAS = {"HARIO": "ハリオ", "Kalita": "カリタ", "Melitta": "メリタ", "1Zpresso": "ワンゼットプレッソ", "TIMEMORE": "タイムモア", "Fellow": "フェロー", "ORIGAMI": "オリガミ", "珈琲サイフオン": "コーノ式 KONO サイフオン", "AeroPress": "エアロプレス", "Bodum": "ボダム", "Comandante": "コマンダンテ"}

MAKERS = {"hario": hario, "kalita": kalita, "melitta": melitta, "1zpresso": z1presso, "coffee-syphon": coffee_syphon, "bodum": bodum, "crema-comandante": crema_comandante, "comandante-x25": comandante_x25, **{k: shopify(k) for k in SHOPIFY}}


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
    ap.add_argument("--from-file", help="ブラウザで書き出したファイル(scripts/shopify-export.js)から作る(Shopify製の公式ショップのみ)")
    ap.add_argument("--reuse", action="store_true", help="取得済みの原文(source-archive)から作り直す。サイトにはアクセスしない(Kalitaのみ)")
    a = ap.parse_args()
    if a.from_file and a.maker not in SHOPIFY and a.maker != "bodum":
        ap.error("--from-file は、Shopify製の公式ショップ(hario-shop・timemore・fellow・origami・ogawa)と、bodum だけで使えます")
    if a.from_file:
        result = MAKERS[a.maker](a.dry_run, False, a.from_file)
    else:
        result = MAKERS[a.maker](a.dry_run, a.reuse) if a.reuse else MAKERS[a.maker](a.dry_run)
    if result is None:
        return
    source_id = save_raw(a.maker, result) if result["raw"] is not None else sorted(p.name for p in (ROOT / "source-archive").glob(f"tools-{a.maker}-2*"))[-1]
    catalog = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"version": 1, "items": []}
    if result.get("merge") == "add":
        ids = {i["id"] for i in result["items"]}
        catalog["items"] = [i for i in catalog["items"] if i["id"] not in ids]
        for item in result["items"]:
            item["sourceId"] = source_id
            if result["maker"] in MAKER_ALIAS:
                item["makerAlias"] = MAKER_ALIAS[result["maker"]]
        catalog["items"] += result["items"]
    elif result.get("merge") == "sku":
        # 既存の項目(別の公式サイトの名前・型番)に、店のJANを、型番(sku)で補う。既存に無い型番の商品は、追加する
        shop_by_sku = {v["sku"]: (item, v) for item in result["items"] for v in item["variants"] if v["sku"]}
        known = set()
        filled = 0
        for item in catalog["items"]:
            if item["maker"] != result["maker"]:
                continue
            for v in item["variants"]:
                key = HARIO_SKU_ALIAS.get(v["sku"], v["sku"])
                known.add(key)
                known.add(v["sku"])
                hit = shop_by_sku.get(key)
                if hit and hit[1]["gtin"] and not v["gtin"]:
                    v["gtin"] = hit[1]["gtin"]
                    item["gtinSourceId"] = source_id
                    filled += 1
        added = 0
        for item in result["items"]:
            if all(v["sku"] in known for v in item["variants"] if v["sku"]) and any(v["sku"] for v in item["variants"]):
                continue
            item["sourceId"] = source_id
            if result["maker"] in MAKER_ALIAS:
                item["makerAlias"] = MAKER_ALIAS[result["maker"]]
            catalog["items"].append(item)
            added += 1
        print(f"JANを補った型番: {filled} 件 / 追加した製品: {added} 件 / 店に無い型番(補えなかった): "
              f"{sum(1 for i in catalog['items'] if i['maker'] == result['maker'] for v in i['variants'] if v['sku'] and v['sku'] not in shop_by_sku)} 件")
    else:
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
