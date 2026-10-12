# -*- coding: utf-8 -*-
"""
scrape_sowacafe.py

自家焙煎 真岡珈琲ソワカフェ(https://sowacafe.thebase.in/、栃木県真岡市八木岡472-5)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(栃木県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): 全18商品のうち豆15銘柄(各100g)を対象とする。おまかせ三点セット2種・セミナーは除外。
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している
(商品ページのタイトルがキャッチコピー付き・重量違いの重複登録のため)。
価格・在庫(item_purchasability)・説明(og:description。汎用文のときは商品ページ本文)は商品ページから取得する。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import html
import json
import re

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "自家焙煎 真岡珈琲ソワカフェ",
    "url": "https://sowacafe.thebase.in/",
    "platform": "BASE",
    "address": "栃木県真岡市八木岡472-5",
    "prefecture": "栃木県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://sowacafe.thebase.in"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('27973191', 'イエメンモカ【中煎】', 100, None, '中煎り'),
    ('27700941', 'キリマンジャロ【中煎】', 100, None, '中煎り'),
    ('102959325', 'モカ【中煎】', 100, None, '中煎り'),
    ('27968675', 'コロンビア【中深煎】', 100, None, '中深煎り'),
    ('27969709', 'サントス【中深煎】', 100, None, '中深煎り'),
    ('27973772', 'モカ【中深煎】', 100, None, '中深煎り'),
    ('27973053', 'ブルボン【中深煎】', 100, None, '中深煎り'),
    ('27970335', 'トラジャ【中深煎】', 100, None, '中深煎り'),
    ('27700797', 'グアテマラ【中深煎】', 100, None, '中深煎り'),
    ('27973391', 'マンデリン【深煎】', 100, None, '深煎り'),
    ('27700853', 'モカ【深煎】', 100, None, '深煎り'),
    ('27970130', 'ダテーラ【深煎】', 100, None, '深煎り'),
    ('27970814', 'カフェインレス【液体二酸化炭素法】', 100, None, None),
    ('28844933', '白布(はくふ)ブレンド【中煎】', 100, None, '中煎り'),
    ('28844641', '真岡(もおか)ブレンド【中深煎】', 100, None, '中深煎り'),
]

# coffee_parser.pyの国名辞書で検出できない表記(「タイ」「中国」「ケニヤ」等)の産地を明示する
ORIGIN_OVERRIDES = {'27973191': 'イエメン', '27700941': 'タンザニア', '102959325': 'エチオピア', '27969709': 'ブラジル', '27973772': 'エチオピア', '27973053': 'ブラジル', '27970335': 'インドネシア', '27973391': 'インドネシア', '27700853': 'エチオピア', '27970130': 'ブラジル'}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id: str, name: str, weight_g: int, category_override: str | None, roast_level: str | None) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    desc = re.sub(r"\s+", " ", desc_m.group(1)).strip()[:400] if desc_m else None
    if not desc or "通販ネットショップ" in desc:
        # og:descriptionが汎用文のため、商品ページ本文(タイトル直後〜価格の間)から説明を取る
        body = re.sub(r"<script.*?</script>|<style.*?</style>", "", html_text, flags=re.S)
        body = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", body)))
        title_m = re.search(r'<meta property="og:title" content="([^"|]*)', html_text)
        title = re.sub(r"\s+", " ", html.unescape(title_m.group(1))).strip() if title_m else ""
        start = body.find("CONTACT " + title) if title else -1
        if start >= 0:
            start += len("CONTACT " + title)
            end = body.find("¥", start)
            body = body[start:end if end > 0 else start + 400]
            body = re.sub(r"[★※]\s*送料[^ ]*", "", body).strip()
            desc = body[:400] or None
        else:
            desc = None
    price_m = PRICE_PATTERN.search(html_text)
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    sold_out = bool(purchasability_m) and purchasability_m.group(1) == "unpurchasable"

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if category_override:
        parsed["category"] = category_override
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if item_id in ORIGIN_OVERRIDES:
            parsed["origin_country"] = ORIGIN_OVERRIDES[item_id]
            parsed["origin_source"] = "raw_name"

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price_m.group(1)) if price_m else None,
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/items/{item_id}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item_id, name, weight_g, category_override, roast_level in ITEMS:
        try:
            record = build_record(item_id, name, weight_g, category_override, roast_level)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_sowacafe.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_sowacafe.json に出力しました")


if __name__ == "__main__":
    main()
