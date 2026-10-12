# -*- coding: utf-8 -*-
"""
scrape_kohakucoffeefukui.py

Kohaku珈琲(旧 焙煎所 松)(https://sunnycoffee.theshop.jp/、公式 https://roastery-matsu.com/、
福井県今立郡池田町菅生25 直売所)の商品情報を取得する。BASE。
(既存の scrape_kohakucoffee.py は滋賀県の別店舗「kohaku coffee」のため別名にしている)

【住所について】
BASEの特商法ページはBASE社の住所のみ記載。公式サイト https://roastery-matsu.com/about/ の
直売所の記載(〒910-2535 福井県今立郡池田町菅生25、不定期営業)を採用(2026-10-12確認)。

【対象商品について】
実データ確認済み(2026-10-12): sitemap.xmlの商品18件のうち、ドリップバッグ・ギフトBOX・
「焙煎士のオリジナルブレンド100g×4種類」(4種セット)を除く12銘柄を対象とする。
全商品が「100g×2set」(100g袋2つのセット)の1ページ構成で、単品1袋の価格は取得できないため、
表示どおり「価格=2袋セットの表示価格、重量=200g」を採用する。
商品名・産地は商品ページのタイトル/説明を確認したうえで下のITEMSに明示している。
価格・在庫(item_purchasability)・説明は商品ページから取得する。
公式サイトのブログ最新は2025.03/04と古い(更新の古さに注意)。

【robots.txtについて】
他のBASE系店舗と同一の記述。識別可能な独自User-Agentを使用する。
"""

import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "Kohaku珈琲",
    "url": "https://sunnycoffee.theshop.jp/",
    "platform": "BASE",
    "address": "福井県今立郡池田町菅生25",
    "prefecture": "福井県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://sunnycoffee.theshop.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g)=100g×2set, 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ("87484158", "森ノ彩 〜morinoiro〜", 200, "ブレンド", None),
    ("3854985", "Sunny blend", 200, "ブレンド", None),
    ("40238509", "アオノ日", 200, "ブレンド", "ライトロースト"),
    ("64067107", "山影 〜yamakage〜", 200, "ブレンド", None),
    ("64067207", "白風 〜shirakaze〜", 200, "ブレンド", None),
    ("84761214", "タンザニア イサイソ ウォッシュド", 200, None, None),
    ("81462767", "ブルンジ ブシンデウォッシングステーション ナチュラル", 200, None, None),
    ("82787021", "エチオピア チレ ウォッシュド", 200, None, None),
    ("5711382", "インドネシア マンデリン ミトラG1", 200, None, None),
    ("88983703", "ルワンダ ギト ハニープロセス", 200, None, None),
    ("3966679", "ブラジル ブルボンアマレロ ボンジャルディン農園 ナチュラル", 200, None, None),
    ("64067255", "グアテマラ リオ コロラド ゴールデンパレンシア", 200, None, None),
]

ORIGIN_OVERRIDES = {
    "84761214": "タンザニア",
    "81462767": "ブルンジ",
    "82787021": "エチオピア",
    "5711382": "インドネシア",
    "88983703": "ルワンダ",
    "3966679": "ブラジル",
    "64067255": "グアテマラ",
}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id, name, weight_g, category_override, roast_level):
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    html_text = resp.text

    import html as _html
    desc_m = DESC_PATTERN.search(html_text)
    desc = re.sub(r"\s+", " ", _html.unescape(desc_m.group(1))).strip()[:400] if desc_m else None
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


def scrape_all_products():
    records = []
    for item_id, name, weight_g, category_override, roast_level in ITEMS:
        try:
            record = build_record(item_id, name, weight_g, category_override, roast_level)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        if record is not None:
            records.append(record)
        time.sleep(0.5)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_kohakucoffeefukui.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kohakucoffeefukui.json に出力しました")


if __name__ == "__main__":
    main()
