# -*- coding: utf-8 -*-
"""
scrape_hanacoffee.py

hanacoffee(https://hanacoffee06.base.shop、長野県上田市(番地は非公開)。公式サイトは https://hanacoffee.jp)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(長野県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10-11時点): sitemap.xml の全15商品のうち、100g(豆のまま)の焙煎豆8銘柄(シングル6・ブレンド1・ディカフェ1)を対象とする。
内容量は購入バリエーション名(「豆のまま100g」等)から確認した。ドリップバッグ/パック・ギフト・水出しパック・手提げバッグは除外。
インドネシアは深煎りと中深煎りの2商品があるが、焙煎度違いの別商品として両方収録した。
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している
(商品名に重量や送料無料等の付帯表記・英語併記が入っているため)。
価格・在庫・説明(og:description)は商品ページから取得する。

【在庫について】
購入ページのバリエーション(豆/粉)のうち豆の在庫が「在庫なし」なら完売とする(粉のみ在庫ありでも完売)。
バリエーションが無い商品は item_purchasability が unpurchasable なら完売。

【住所について】
/law の事業者所在地はBASE株式会社(東京都港区六本木)のため店舗住所ではない。公式サイト hanacoffee.jp の
所在地が「長野県上田市」のみのため、市までを採用し、番地は捏造しない。

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
    "name": "hanacoffee",
    "url": "https://hanacoffee06.base.shop/",
    "platform": "BASE",
    "address": "長野県上田市",
    "prefecture": "長野県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://hanacoffee06.base.shop"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# 商品ごとの明示情報。
#   id: 商品ID / name: 表示名 / weight: 代表(最小重量)のグラム数 / category: Noneなら自動判定
#   roast: 焙煎度 / roast_hint: 焙煎度を一意に決められない場合の表記 / origin: 産地国の上書き
#   process: 精選方法の上書き / blend: ブレンドの構成国(判明分のみ)
ITEMS = [{'id': '82757754', 'name': '季節のコーヒー ウィンターブレンド', 'weight': 100, 'roast': '中深煎り', 'blend': [('インドネシア', None), ('グアテマラ', None)]},
 {'id': '89487226', 'name': 'タイ', 'weight': 100, 'roast': '中煎り', 'category': 'ストレート', 'origin': 'タイ'},
 {'id': '78460920', 'name': 'ブラジル', 'weight': 100, 'roast': '中煎り'},
 {'id': '76503454', 'name': 'タンザニア ンゴロンゴロ AA++', 'weight': 100, 'roast': '中煎り'},
 {'id': '69660086', 'name': 'グアテマラ ウエウエテナンゴ', 'weight': 100, 'roast': '中煎り', 'process': 'ウォッシュド'},
 {'id': '69324918', 'name': 'インドネシア スラウェシ・ママサ', 'weight': 100, 'roast': '深煎り'},
 {'id': '56214122', 'name': 'インドネシア', 'weight': 100, 'roast': '中深煎り'},
 {'id': '64449945', 'name': 'ディカフェのコーヒー豆', 'weight': 100, 'roast': '中深煎り', 'category': 'ストレート', 'origin': 'コスタリカ'}]

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
VARIATION_PATTERN = re.compile(
    r'<p class="cot-itemOrder-variationName"[^>]*>([^<]*)</p>\s*'
    r'(?:<p class="cot-itemOrder-variationStock"[^>]*>([^<]*)</p>)?'
)
GROUND_KEYWORDS = ("粉", "挽", "ドリップ")


def is_sold_out(html_text: str) -> bool:
    """豆(挽いていない)のバリエーションが全て在庫なしなら完売。バリエーションが無ければ購入可否で判定する。"""
    bean_variations = [
        (name, stock.strip())
        for name, stock in VARIATION_PATTERN.findall(html_text)
        if not any(k in name for k in GROUND_KEYWORDS)
    ]
    if bean_variations:
        return all(stock == "在庫なし" for _, stock in bean_variations)
    m = PURCHASABILITY_PATTERN.search(html_text)
    return bool(m) and m.group(1) == "unpurchasable"


def build_record(item: dict) -> dict | None:
    item_url = f"{BASE_URL}/items/{item['id']}"
    resp = requests.get(item_url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    desc = re.sub(r"\s+", " ", re.sub(r"-{3,}", " ", desc_m.group(1))).strip()[:400] if desc_m else None
    price_m = PRICE_PATTERN.search(html_text)
    sold_out = is_sold_out(html_text)

    name = item["name"]
    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if item.get("category"):
        parsed["category"] = item["category"]
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if item.get("origin"):
            parsed["origin_country"] = item["origin"]
            parsed["origin_source"] = "raw_name"
    if item.get("process"):
        parsed["processing_method"] = item["process"]

    blend_components = [{"origin_country": c, "percentage": p} for c, p in (item.get("blend") or [])]

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": item.get("roast") or parsed["roast_level"],
        "roast_hint": item.get("roast_hint"),
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": blend_components,
        "price": int(price_m.group(1)) if price_m else None,
        "weight_g": item["weight"],
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": item_url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in ITEMS:
        try:
            record = build_record(item)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item['id']} ({e})")
            continue
        if record is not None:
            records.append(record)
        time.sleep(0.5)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_hanacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_hanacoffee.json に出力しました")


if __name__ == "__main__":
    main()
