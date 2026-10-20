# -*- coding: utf-8 -*-
"""
scrape_taishocoffee.py

TAISHO COFFEE ROASTER(https://taishocoffee.theshop.jp/、福岡県糸島市二丈深江3丁目1-5)の商品情報を取得する。BASE。

【店舗発見の経緯】
福岡県のモール・独自EC出店店舗の試験調査(福岡県3)で発見。

【対象商品について】
実データ確認済み(2026-10時点): sitemap.xmlの全21商品のうち、焙煎豆200gの12商品(ブレンド4・デカフェ1・シングルオリジン7)を対象とする。リキッドコーヒー、ドリップバッグ、各種セット、定期便、さいき・やよいブレンド(3種セット)は除外。グアテマラ プエルタ ベルデは「中煎りor深煎り」選択式のため焙煎度は不明(None)とする。
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している
(商品ページのタイトルが産地・農園・品種・焙煎度・重量を並べた長文のため)。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "TAISHO COFFEE ROASTER",
    "url": "https://taishocoffee.theshop.jp/",
    "platform": "BASE",
    "address": "福岡県糸島市二丈深江3丁目1-5",
    "prefecture": "福岡県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
    "source_note": "特商法(/law)・Aboutページ(/about)と各商品ページを2026-10-20に確認。住所は特商法の福岡県糸島市二丈深江3丁目1-5(第三者記事の二丈深江569-1は旧表記の可能性)。About: 2016年10月に自家焙煎スペシャルティコーヒー豆店として開店",
    "last_verified_at": "2026-10-20",
}

BASE_URL = "https://taishocoffee.theshop.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [('78139700', '秋のブレンド2026 ふかまる', 200, 'ブレンド', None),
 ('5992117', 'ハウスブレンド ピッピ', 200, 'ブレンド', '中煎り'),
 ('8244694', 'シティブレンド フカエ', 200, 'ブレンド', '中深煎り'),
 ('8836008', 'デカフェ メキシコ エル・トリウンフォ', 200, 'デカフェ', None),
 ('8170874', 'エチオピア イルガチェフェ モカ G-1 デスタ・ゴロ ウォッシュド', 200, None, '中煎り'),
 ('8170066', 'コロンビア サントゥアリオ農園', 200, None, '中煎り'),
 ('8170250', 'ブラジル レクレイオ農園', 200, None, '中煎り'),
 ('8170506', 'グアテマラ プエルタ ベルデ農園', 200, None, None),
 ('8170942', 'エチオピア イルガチェフェ モカ ナチュラル アベベゴダナ農園', 200, None, '中煎り'),
 ('8245221', 'ケニア カリアイニ ファクトリー', 200, None, '中深煎り'),
 ('8245959', 'ブラジル トミオフクダ バレ・ド・クリスタル農園 ドライ・オン・ツリー', 200, None, None),
 ('8246039', 'イタリアンブレンド パッショーネ', 200, 'ブレンド', '深煎り')]

# coffee_parser.pyの国名辞書で検出できない表記(「タイ」「中国」「ケニヤ」等)の産地を明示する
ORIGIN_OVERRIDES = {}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id: str, name: str, weight_g: int, category_override: str | None, roast_level: str | None) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    desc = re.sub(r"\s+", " ", re.sub(r"^.*?-{5,}", "", desc_m.group(1), flags=re.S)).strip()[:400] if desc_m else None
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
    for n, (item_id, name, weight_g, category_override, roast_level) in enumerate(ITEMS):
        if n:
            time.sleep(5)  # BASEは5秒以上の間隔
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
    with open("data_taishocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_taishocoffee.json に出力しました")


if __name__ == "__main__":
    main()
