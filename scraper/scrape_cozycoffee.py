# -*- coding: utf-8 -*-
"""
scrape_cozycoffee.py

COZY COFFEE(https://cozycoffee.thebase.in/、福岡県福岡市西区橋本1-11-16)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(福岡県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): 各銘柄が100g/200gの別ページ登録(ブレンド・一部は200gのみ)のため、最小重量の商品を代表とする。ドリップバッグ・水出しパック・ギフトBOX・ハーブティー・フィルター・スプーン・オリジナルパッケージ受注は除外。商品名の先頭の「【◯月限定】」等の販売期間表記は商品名から取り除く。焙煎度は説明文の「焙煎度:」欄から取得する。住所は特定商取引法ページの記載による。
商品一覧ページ(ページ送り)から商品URLを集め、各商品ページの og:title・og:description・
product:price:amount・item_purchasability(価格・説明・在庫)を取得する。
商品名の重量表記から重量(g)を取り、重量表記のない商品(器具・菓子・飲料等)と、除外キーワード
(ドリップバッグ・セット・ギフト・定期便・水出し等)を含む商品は対象外とする。
同一銘柄が重量違いの別商品で並ぶ場合は、最小重量の商品を代表とする。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import html
import json
import re
import time
import unicodedata

import requests

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method,
)

SHOP_INFO = {
    "name": "COZY COFFEE",
    "url": "https://cozycoffee.thebase.in/",
    "platform": "BASE",
    "address": "福岡県福岡市西区橋本1-11-16",
    "prefecture": "福岡県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://cozycoffee.thebase.in"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL_SEC = 0.5

# 商品名(正規化後)にこれらを含む商品は対象外
EXCLUDE_KEYWORDS = ("ドリップ", "drip", "バッグ", "bag", "水出し", "コールドブリュー", "cold brew", "セット", " set", "ギフト", "gift", "定期便", "飲み比べ", "グラノーラ", "タンブラー", "ドリッパー", "フィルター", "スプーン", "ティー", "羊羹", "cookie", "オリジナルパッケージ", "お試し", "詰め合わせ")
# 商品名(正規化後)がこのパターンに一致する商品だけを対象にする
INCLUDE_TITLE_PATTERN = re.compile(r"")
# 商品名から取り除く表記(重量表記は別途取り除く)
NAME_STRIP_PATTERNS = [r"^【[^】]*限定[^】]*】"]
# 商品名からは産地が判定できない銘柄の産地(商品名の部分一致)
ORIGIN_OVERRIDES = {}
# 商品名にこれを含む銘柄の精製方法(商品名の別の語に誤反応する場合の明示)
PROCESS_OVERRIDES = {"ハニーショコラ": "ナチュラル"}
# 商品名に「ブレンド」を含むが単一産地として扱う銘柄(商品名の部分一致)
SINGLE_ORIGIN_NAMES = ()
# 説明文から取り除く表記(正規表現)
DESC_STRIP_PATTERNS = []
# 説明文のこの正規表現に一致した位置から後ろ(配送案内等)は捨てる
DESC_CUT_PATTERN = None
# 説明文がこの文字列で始まる場合は店舗紹介の定型文なので使わない
DESC_BOILERPLATE_PREFIX = ""

WEIGHT_PATTERN = re.compile(r"(\d+)\s*g(?![a-z])", re.I)
WEIGHT_TOKEN_PATTERN = re.compile(r"[【\[]?\s*\d+\s*g(?![a-z])\s*[】\]]?", re.I)
COARSE_ROASTS = (
    ("中浅煎り", re.compile(r"中浅煎り?|ミディアムライト|medium\s*light", re.I)),
    ("中深煎り", re.compile(r"中深煎り?|ミディアムダーク|medium\s*dark", re.I)),
    ("浅煎り", re.compile(r"浅煎り?|ライト\s*ロースト|light\s*roast|\blight\b", re.I)),
    ("中煎り", re.compile(r"中煎り?|ミディアム\s*ロースト|medium\s*roast|\bmedium\b", re.I)),
    ("深煎り", re.compile(r"深煎り?|ダーク\s*ロースト|dark\s*roast|\bdark\b|フレンチ|イタリアン|french\s*roast", re.I)),
)
ROAST_LABEL_PATTERN = re.compile(r"(?:焙煎度|焙煎|Roast\s*Level|Roast\s*Profile|Roast)\s*[:：/／は]?\s*([^\n。、]{0,30})", re.I)
DESC_ORIGIN_PATTERN = re.compile(r"(?:豆原産国|原産国|生産国|生産地)\s*[:：/／]?\s*([^\s、,/]+)")
DESC_PROCESS_PATTERN = re.compile(r"(?:生産処理|精製方法|精製|プロセス|Process)\s*[:：/／]?\s*([^\s、,/]+)", re.I)

OG_TITLE = re.compile(r'<meta property="og:title" content="([^"]*)"')
OG_DESC = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s or "")).strip()


def coarse_roast(text: str) -> tuple[str | None, str | None]:
    for label, pat in COARSE_ROASTS:
        m = pat.search(text or "")
        if m:
            return label, m.group(0)
    return None, None


def fetch_item_ids() -> list[str]:
    ids: list[str] = []
    for page in range(1, 30):
        url = BASE_URL + ("/" if page == 1 else f"/?page={page}")
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
        resp.encoding = "utf-8"
        found = re.findall(r'href="(?:https?://[^"/]+)?/items/(\d+)', resp.text)
        new = [i for i in dict.fromkeys(found) if i not in ids]
        if not new:  # 範囲外のページは1ページ目が返るため、新規IDが無ければ終了
            break
        ids.extend(new)
        time.sleep(REQUEST_INTERVAL_SEC)
    return ids


def fetch_item(item_id: str) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    t = resp.text
    title_m = OG_TITLE.search(t)
    price_m = PRICE_PATTERN.search(t)
    if not title_m or not price_m:
        return None
    desc_m = OG_DESC.search(t)
    pur_m = PURCHASABILITY_PATTERN.search(t)
    return {
        "id": item_id,
        "title": html.unescape(title_m.group(1)).rsplit(" | ", 1)[0],
        "desc": html.unescape(desc_m.group(1)) if desc_m else "",
        "price": int(price_m.group(1)),
        "sold_out": bool(pur_m) and pur_m.group(1) == "unpurchasable",
    }


def clean_name(title: str) -> str:
    name = norm(title)
    name = WEIGHT_TOKEN_PATTERN.sub(" ", name)
    for pat in NAME_STRIP_PATTERNS:
        name = re.sub(pat, " ", name)
    name = re.sub(r"【\s*】|\[\s*\]|\(\s*\)", " ", name)
    return norm(name).strip(" -_・")


def clean_desc(raw: str) -> str | None:
    text = norm(raw)
    if DESC_BOILERPLATE_PREFIX and text.startswith(DESC_BOILERPLATE_PREFIX):
        return None
    for pat in DESC_STRIP_PATTERNS:
        text = re.sub(pat, "", text)
    if DESC_CUT_PATTERN:
        m = re.search(DESC_CUT_PATTERN, text)
        if m:
            text = text[:m.start()]
    return text.strip()[:400] or None


def build_record(item: dict) -> dict | None:
    title = norm(item["title"])
    if not INCLUDE_TITLE_PATTERN.search(title):
        return None
    if any(k.lower() in title.lower() for k in EXCLUDE_KEYWORDS):
        return None
    wm = WEIGHT_PATTERN.search(title)
    if not wm:
        return None
    weight = int(wm.group(1))
    name = clean_name(title)
    if not name or item["price"] <= 0:
        return None
    desc = clean_desc(item["desc"])
    raw_desc = norm(item["desc"])
    if DESC_BOILERPLATE_PREFIX and raw_desc.startswith(DESC_BOILERPLATE_PREFIX):
        raw_desc = ""

    parsed = parse_product(name.replace("ウォシュド", "ウォッシュド"))
    parsed["raw_name"] = name
    is_blend = parsed["category"] == "ブレンド" and not any(k in name for k in SINGLE_ORIGIN_NAMES)
    if is_blend:
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
        parsed["grade"] = None
        processing = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"]:
            detected = detect_country_name(name)
            if detected:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
        for key, country in ORIGIN_OVERRIDES.items():
            if key in name:
                parsed["origin_country"] = country
                parsed["origin_source"] = "raw_name"
                break
        if not parsed["origin_country"]:
            m = DESC_ORIGIN_PATTERN.search(raw_desc)
            c = detect_country_name(m.group(1)) if m else None
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "description"
        parsed = apply_category_hint_fallback(parsed, name)
        processing = parsed["processing_method"]
        if not processing:
            m = DESC_PROCESS_PATTERN.search(raw_desc)
            processing = detect_processing_method(m.group(1)) if m else None
        for key, method in PROCESS_OVERRIDES.items():
            if key in name:
                processing = method

    roast_level, roast_hint = coarse_roast(title)
    if not roast_level:
        for m in ROAST_LABEL_PATTERN.finditer(raw_desc):
            roast_level, _ = coarse_roast(m.group(1))
            if roast_level:
                roast_hint = m.group(1).split("豆原産国")[0].strip()
                break

    status = "完売" if item["sold_out"] else "販売中"
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_hint": roast_hint,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": weight,
        "stock_status": status,
        "out_of_stock": status != "販売中",
        "product_url": f"{BASE_URL}/items/{item['id']}",
    }


def scrape_all_products() -> list[dict]:
    # 銘柄ごとに最小重量(同重量なら安い方)の商品を代表にする
    best: dict[str, dict] = {}
    order: list[str] = []
    for item_id in fetch_item_ids():
        try:
            item = fetch_item(item_id)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        time.sleep(REQUEST_INTERVAL_SEC)
        if item is None:
            continue
        record = build_record(item)
        if record is None:
            continue
        key = record["raw_name"]
        if key not in best:
            best[key] = record
            order.append(key)
        elif (record["weight_g"], record["price"]) < (best[key]["weight_g"], best[key]["price"]):
            best[key] = record
    return [best[k] for k in order]


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_cozycoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_cozycoffee.json に出力しました")


if __name__ == "__main__":
    main()
