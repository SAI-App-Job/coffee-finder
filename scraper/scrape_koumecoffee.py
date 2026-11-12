# -*- coding: utf-8 -*-
"""
scrape_koumecoffee.py

小梅の珈琲焙煎所(https://coffeekoume.base.shop/、東京都立川市高松町2-1-24)の自家焙煎コーヒー豆の商品情報を取得する。BASE。

【店舗の実在確認(2026-10-25)】
公式ショップ about(https://coffeekoume.base.shop/about)「東京都立川市高松町にある、自家焙煎コーヒー豆の専門店です。半熱風焙煎機と小さな直火の焙煎機で丁寧にお作りします」
「実店舗 立川市高松町2-1-24 営業時間11:00〜19:00 月水は12:00〜17:00 不定休」。
第三者: たちかわタイムス(https://tachikawatimes.com/koumecoffee501.html/)「立川市高松町２丁目１−２４」「小さな直火の焙煎機で丁寧に焙煎したコーヒー豆の専門店」。

【対象商品について】
実データ確認済み(2026-10-25): 商品ページ8件(sitemap.xml)のうち豆単品5件(いずれも100g、商品名末尾に「100グラム」表記)。
除外: お試し300g/400gセット2件、お試しドリップバッグ5個セット。
商品名・重量・焙煎度は商品ページの表記を確認したうえで下のITEMSに明示している。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。

【robots.txtについて】
BASE共通の記述(python-requests/curl等は個別にDisallow: /、User-agent: *では
/cart/・/web_cart/・/shops/・/api/shops/等のみ禁止)。本スクレイパーは識別可能な
独自User-Agentを使用し、取得するのは /items/ の商品ページのみ。取得間隔は5秒。
"""

import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "小梅の珈琲焙煎所",
    "url": "https://coffeekoume.base.shop/",
    "platform": "BASE",
    "address": "東京都立川市高松町2-1-24",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-10-25確認。BASE共通の記述でpython-requests/curl等は個別にDisallow、User-agent: * では商品ページ(/items/)は許可。識別可能なUser-Agentを使用)",
    "source_note": "公式ショップ about と商品ページ(sitemap.xmlの/items/全8件)を2026-10-25に確認。商品説明に「2024年冬入荷の新作です」の記述が残る(更新日は不明)。たちかわタイムスで実店舗・自家焙煎を確認(過去の記事)。",
    "last_verified_at": "2026-10-25",
}

BASE_URL = "https://coffeekoume.base.shop"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL = 5

# (商品ID, 商品名, 重量(g)またはNone, 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら説明文→商品名の順で判定))
ITEMS = [
    ('46767084', 'インドネシア スマトラタイガー 深煎り', 100, None, '深煎り'),
    ('46767157', 'ブラジル プラナウト農園エスプレッソレディ 中深煎り', 100, None, '中深煎り'),
    ('47156679', 'グァテマラ アンティグア 中深煎り', 100, None, '中深煎り'),
    ('58430238', 'チョコレートブレンド 深煎り', 100, 'ブレンド', '深煎り'),
    ('58599576', 'デカフェ(カフェインレス)グァテマラ 中深煎り', 100, None, '中深煎り'),
]

# 産地の上書き(商品ID -> 日本語の国名。None は「商品名と説明で食い違う等で不明」とする)
ORIGIN_OVERRIDES = {}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)")
ROAST_PATTERN = re.compile(r"【焙煎度】\s*([^【\s]+)")


def clean_desc(raw: str) -> str | None:
    import html as _html
    text = _html.unescape(raw)
    text = re.sub(r"\s+", " ", text).strip()
    pass
    return text[:400] or None


def build_record(item_id, name, weight_g, category_override, roast_level):
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    raw_desc = desc_m.group(1) if desc_m else ""
    desc = clean_desc(raw_desc)
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
            parsed["origin_source"] = "raw_name" if ORIGIN_OVERRIDES[item_id] else None

    if not roast_level:
        import html as _html
        roast_m = ROAST_PATTERN.search(re.sub(r"\s+", "", _html.unescape(raw_desc)))
        roast_level = roast_m.group(1) if roast_m else None
    if not roast_level:
        roast_level = parsed["roast_level"]

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level,
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
    for index, (item_id, name, weight_g, category_override, roast_level) in enumerate(ITEMS):
        if index:
            time.sleep(REQUEST_INTERVAL)
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
    with open("data_koumecoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_koumecoffee.json に出力しました")


if __name__ == "__main__":
    main()
