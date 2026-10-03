# -*- coding: utf-8 -*-
"""
scrape_coffeenova.py

コフィノワ COFFEE NOVA(https://www.coffee-nova.com/、東京都台東区蔵前3-20-5 ハッピーメゾン蔵前 1F)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(東京都)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): BASEの特定商取引法表記(/law)と公式サイトのaboutで台東区蔵前3-20-5の所在地を確認。aboutは「蔵前にカフェを構えるコーヒーロースター」「焙煎に携わること15年以上」とあり、報道・紹介記事でもオーナーが焙煎から抽出まで行う店と確認(自家焙煎の記述は公式サイトでは控えめ)。全27商品のうちドリップパック・言葉珈琲(定期便)・おまとめ買い・セレクションセット・タオルを除く15銘柄(ブレンド4、デカフェ1含む)を対象とする。100g表記が基本。エスプレッソブレンドのみ商品名・説明に重量記載がなくNone。焙煎度は商品説明の「焙煎度合」表記による。
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している
(商品名に重量・焙煎度・キャッチコピーが混在しているため)。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。
在庫がpartially_purchasable(豆のみ品切れ等)の商品は販売中として扱う。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import json
import re

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "コフィノワ COFFEE NOVA",
    "url": "https://www.coffee-nova.com/",
    "platform": "BASE",
    "address": "東京都台東区蔵前3-20-5 ハッピーメゾン蔵前 1F",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://www.coffee-nova.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g。ページに記載がなければNone), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('152656904', 'Rwanda Simbi Anaerobic Natural', 100, None, 'ミディアムロースト'),
    ('129163660', 'Guatemala La Maravilla Washed', 100, None, 'シティロースト'),
    ('129074625', 'Brazil Carmo Farm Pulped Natural', 100, None, 'シティロースト'),
    ('117203095', 'Colombia Huila, Carambolo fermented washed', 100, None, 'ミディアムロースト'),
    ('113760965', 'エチオピア Sidamo ボナ・ズリア セダカ Natural', 100, None, 'ミディアムロースト'),
    ('106542067', 'ケニアAA Gititu Factory フリーウォッシュト', 100, None, 'ミディアムロースト'),
    ('94338597', 'Colombia GEISHA Fermented Washed Peñas Blancas', 100, None, None),
    ('87253287', 'エチオピア イルガチェフェ ウォルカ・チェルチェレ ウォッシュト', 100, None, 'ミディアムロースト'),
    ('66524867', 'インドネシア・リントン・マンデリン・ビートル', 100, None, 'フルシティロースト'),
    ('66524859', 'EL Salvador Santa Rita Natural', 100, None, 'ハイロースト'),
    ('66524857', '桂ブレンド KatsuraBlend', 100, None, 'シティロースト'),
    ('66524856', '蔵前ブレンド KuramaeBlend', 100, None, 'シティロースト'),
    ('66524855', '厩ブレンド UmayaBlend', 100, None, 'フルシティロースト'),
    ('66524854', 'デカフェ エチオピア マウンテンウォータープロセス', 100, None, 'フレンチロースト'),
    ('66524853', 'エスプレッソブレンド', None, None, 'フルシティロースト'),
]

# coffee_parser.pyの国名辞書で検出できない表記の産地を明示する(商品ID: 産地)
ORIGIN_OVERRIDES = {}

# 商品名の語から誤判定される/名称に記載がない精選方法を、商品ページの記載に合わせて上書きする(商品ID: 精選方法)
PROCESSING_OVERRIDES = {}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id: str, name: str, weight_g: int | None, category_override: str | None, roast_level: str | None) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    desc = re.sub(r"\s+", " ", desc_m.group(1)).strip()[:400] if desc_m else None
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

    if item_id in PROCESSING_OVERRIDES:
        parsed["processing_method"] = PROCESSING_OVERRIDES[item_id]

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
    with open("data_coffeenova.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeenova.json に出力しました")


if __name__ == "__main__":
    main()
