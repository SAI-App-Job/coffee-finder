# -*- coding: utf-8 -*-
"""
scrape_lennoncoffee.py

玲音香琲(レノンコーヒー、東京都国立市富士見台4-23-10、公式 https://www.lennon-coffee.com/)の
自家焙煎コーヒー豆の商品情報を取得する。静的HTML(Shift_JIS)+独自CGIカート(shop.cgi)。

【実店舗・自家焙煎の根拠】(2026-10-25確認)
店舗案内(shop_info.html)の特商法表記で所在地「東京都国立市富士見台4-23-10」、2005年4月に開店、
「珈琲豆はこれまで通り店内で毎日焙煎しています」(同ページ)。当店のこだわり(kodawari.html)で直火式焙煎機を説明。

【robots.txt】https://www.lennon-coffee.com/robots.txt は404(制限記述なし)。商品ページ(bl-*.html / st-*.html)のみ取得する。

【対象商品】
ブレンド一覧(bl-toppage.html)と ストレート一覧(st-toppage.html)から辿れる商品ページ全て。
各ページの「販売価格(税込) ￥780(100g)」を価格・重量とし、豆のまま(カートの既定)の価格を採用する。
セットメニュー・珈琲アイテム(器具)・ギフトは対象外。
"""

import json
import re
import time
import unicodedata

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "玲音香琲",
    "url": "https://www.lennon-coffee.com/",
    "platform": "独自サイト(静的HTML+CGIカート)",
    "address": "東京都国立市富士見台4-23-10",
    "prefecture": "東京都",
    "robots_txt_status": "制限記述なし(robots.txtは404。2026-10-25確認)",
    "source_note": "公式サイト https://www.lennon-coffee.com/ のブレンド一覧(bl-toppage.html)・ストレート一覧(st-toppage.html)と各商品ページ(bl-*.html, st-*.html)を2026-10-25に確認。店舗案内(shop_info.html)で所在地・店内焙煎を確認。トップの更新情報は10/23付(2026-10-25時点で最新)",
    "last_verified_at": "2026-10-25",
}

BASE_URL = "https://www.lennon-coffee.com/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL = 2

ROAST_IN_NAME = re.compile(r"[（(]([^（()）]*煎り)[）)]")
PRICE_PATTERN = re.compile(r"販売価格（税込）\s*[￥¥]\s*([\d,]+)\s*[（(]\s*(\d+)\s*[ｇg]")
FORM_PATTERN = re.compile(r'<input type="hidden" name="goods" value="([^"]*)"')
CODE_PATTERN = re.compile(r"商品コード：(\S+)")
SOLD_OUT_PATTERN = re.compile(r"品切れ|売り切れ|売切れ|SOLD ?OUT|入荷待ち|在庫なし|販売終了", re.IGNORECASE)


def fetch(path: str) -> str:
    resp = None
    for attempt in range(3):
        resp = requests.get(BASE_URL + path, headers=REQUEST_HEADERS, timeout=30)
        if resp.status_code not in (429, 500, 502, 503, 504):
            break
        time.sleep(10 * (attempt + 1))
    resp.raise_for_status()
    return resp.content.decode("cp932", errors="replace")


def list_pages() -> list[str]:
    pages = []
    for top in ("bl-toppage.html", "st-toppage.html"):
        html_text = fetch(top)
        time.sleep(REQUEST_INTERVAL)
        for p in re.findall(r'href="((?:bl|st)-\d[^"]*\.html)"', html_text):
            if p not in pages:
                pages.append(p)
    return pages


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s or "")).strip()


def build_record(path: str) -> dict | None:
    html_text = fetch(path)
    pm = PRICE_PATTERN.search(html_text)
    gm = FORM_PATTERN.search(html_text)
    if not pm or not gm:
        print(f"[warn] 価格またはカート情報なし: {path}")
        return None
    price = int(pm.group(1).replace(",", ""))
    weight = int(pm.group(2))
    name = clean(gm.group(1))
    is_blend = path.startswith("bl-")

    # 本文: 「商品コード」以降〜「販売価格」まで
    body = re.sub(r"<script.*?</script>|<style.*?</style>", "", html_text, flags=re.S)
    body = re.sub(r"<[^>]+>", "\n", body)
    body = body.replace("&nbsp;", " ")
    i = body.find("商品コード")
    j = body.find("販売価格", i)
    seg = body[i:j] if i >= 0 and j > i else ""
    lines = [clean(l) for l in seg.split("\n")]
    lines = [l for l in lines if l and not l.startswith("商品コード")]
    desc = " ".join(lines)[:500] or None
    sold_out = bool(SOLD_OUT_PATTERN.search(body[i:] if i >= 0 else body))

    rm = ROAST_IN_NAME.search(name)
    roast = rm.group(1) if rm else None
    if not roast:
        m = re.search(r"(極深煎り|中深煎り|中浅煎り|深煎り|中煎り|浅煎り)", desc or "")
        roast = m.group(1) if m else None

    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"]:
            c = detect_country_name(name)
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "decaf_process": "薬品を使わず天然水でカフェインを除去(ウォータープロセス)" if "デカフェ" in name else None,
        "price": price,
        "weight_g": weight,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": BASE_URL + path,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for path in list_pages():
        time.sleep(REQUEST_INTERVAL)
        try:
            rec = build_record(path)
        except requests.RequestException as e:
            print(f"[warn] 商品ページ取得失敗: {path} ({e})")
            continue
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_lennoncoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_lennoncoffee.json に出力しました")


if __name__ == "__main__":
    main()
