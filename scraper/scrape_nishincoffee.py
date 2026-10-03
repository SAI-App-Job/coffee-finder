# -*- coding: utf-8 -*-
"""
scrape_nishincoffee.py

日伸珈琲beans(https://nishincoffee.theshop.jp/、東京都府中市住吉町4-48-19)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(東京都)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): BASEの特定商取引法表記(/law)で府中市住吉町4-48-19の所在地、aboutで「府中市にある自家焙煎珈琲豆専門店」を確認。全35商品のうちドリップバッグ・リキッドアイスコーヒー・お試しセット・送料込みの2袋(400g)/3袋(300g)まとめ商品を除く17銘柄(ブレンド2、デカフェ1含む)を対象とする。内容量は商品名の(200g)から取り、エチオピア2銘柄(ブナブナ・ザ・セレモニー)は商品ページに内容量の記載がなくNone。焙煎度は商品名の【深煎り】等による。
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
    "name": "日伸珈琲beans",
    "url": "https://nishincoffee.theshop.jp/",
    "platform": "BASE",
    "address": "東京都府中市住吉町4-48-19",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://nishincoffee.theshop.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g。ページに記載がなければNone), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('142754632', 'ニカラグア ラス・デリシアス農園 Javanica anaerobic at low', 200, None, '中煎り'),
    ('142752944', 'インドネシア ホリデーマンデリン G1', 200, None, '深煎り'),
    ('121484396', 'エチオピア イルガチェフィG1 ブナブナ ナチュラル', None, None, '浅煎り'),
    ('111809627', 'ブラジル ダテーラ農園 ヴィラ RA認証', 200, None, '深煎り'),
    ('109257874', 'エチオピア イルガチェフィG1 ザ・セレモニー ナチュラル Idido村', None, None, '浅煎り'),
    ('98562740', 'パプアニューギニア トロピカル マウンテン', 200, None, None),
    ('83745444', 'コロンビア クンディナマナカ エクセルソEP', 200, None, '深煎り'),
    ('75209356', 'エチオピア ゲイシャ ジャスミン ケビルゲイシャ農園 ナチュラル', 200, None, None),
    ('73245051', 'コロンビア スウィートベリー スプレモ', 200, None, '深煎り'),
    ('67519913', 'コスタリカ アキアレス農園(RA認証) ウォッシュド', 200, None, None),
    ('44499253', 'なかがわらマイルドブレンド', 200, None, '中深煎り'),
    ('12673347', 'にっしんブレンド', 200, None, '深煎り'),
    ('9016762', 'コロンビア エメラルドマウンテン', 200, None, '深煎り'),
    ('9012082', 'ホンジュラス カフェインレスコーヒー', 200, None, 'シティロースト'),
    ('8943035', 'ケニアマサイ AA', 200, None, '深煎り'),
    ('8927879', 'グアテマラ アンティグアSHB アゾテア', 200, None, '中深煎り'),
    ('8911391', 'ブラジル プレミアムショコラ', 200, None, '深煎り'),
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
    with open("data_nishincoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_nishincoffee.json に出力しました")


if __name__ == "__main__":
    main()
