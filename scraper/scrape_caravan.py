# -*- coding: utf-8 -*-
"""
scrape_caravan.py

自家焙煎珈琲の店 きゃらばん(caravan1976.com、群馬県高崎市昭和町209、
1976年創業)の商品情報を取得する。レガシーなCGIベースの自社カート
(cgi/cart/shop.cgi)。

【店舗発見の経緯】
全国再調査(群馬県)でサブエージェント調査から発見。オンラインショップの
存在が確認できたため、実店舗のみの他候補と異なりスクレイパーで実装した。

【対象商品について】
実データ確認済み(2026-09時点): 自家焙煎カテゴリ(class=0)配下に
「レギュラー」(class=0/0、20件)・「フレンチ」(class=0/1、4件)の2
サブカテゴリがあり、両方合わせて計24件を対象とする(珈琲生豆・
アイス珈琲・器具・ネルドリップ等の非対象カテゴリは除外済み)。
レギュラー20件のうち1件(こだわりブレンド)はブレンド、残り19件は
ストレート。フレンチ4件は全てストレート(レギュラーと同一銘柄の
深煎りバリエーションを含むが、通常焙煎とは別の独立商品として
販売継続中のためどちらも収録する)。

【産地判定について】
「ジャバ・ロブスター」は商品名に国名が無いが、商品説明に「産地：
インドネシア（ジャワ島）」と明記されているため説明文からの検出で
補完する。「スプレモ　200ｇ」(フレンチ)は商品名・説明文のいずれにも
産地情報が無いため、coffee_parser.pyの標準辞書通りorigin_country=null
のまま(単独の「スプレモ」はグレード名であり国名を特定できないため
推測しない)とする。

【ページ構造について】
実データ確認済み: 商品一覧はHTMLテーブルの繰り返し構造で、
`<a name="noXX">`を各商品ブロックの開始点として分割することで
名称・記号(商品番号)・価格・詳細説明を正しく紐付けられる(単純な
正規表現の位置ベースzipでは、詳細説明が無い商品がスキップされる
影響で後続商品の説明文が全てずれて誤対応してしまう不具合を確認した
ため、`<a name=...>`単位のブロック分割方式を採用している)。
"""

import json
import re

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "きゃらばん",
    "url": "http://www.caravan1976.com/",
    "platform": "自社ECサイト(レガシーCGIカート)",
    "address": "群馬県高崎市昭和町209",
    "prefecture": "群馬県",
    "robots_txt_status": "未確認",
}

BASE_URL = "http://www.caravan1976.com/cgi/cart/shop.cgi"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}

CATEGORY_URLS = {
    "レギュラー": f"{BASE_URL}?class=0/0&keyword=&superkey=1&FF=0&order=",
    "フレンチ": f"{BASE_URL}?class=0/1&keyword=&superkey=1&FF=0&order=",
}

NAME_PATTERN = re.compile(
    r'名 称</TD>\s*<TD bgcolor="#ffffff" align="left" height="10" width="200">([^<]+)</TD>'
)
ID_PATTERN = re.compile(
    r'記 号</TD>\s*<TD bgcolor="#ffffff" width="100" height="10" align="left" valign="middle">(\d+)</TD>'
)
PRICE_PATTERN = re.compile(
    r'単 価</TD>\s*<TD bgcolor="#ffffff" width="100" height="10" align="left" valign="middle">([^<]+)</TD>'
)
DESC_PATTERN = re.compile(r"<FONT color=[^>]*>([^<]*)</font>")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def parse_listing(html_text: str, subcategory: str) -> list[dict]:
    blocks = re.split(r'(?=<a name="no\d+">)', html_text)
    records = []
    for block in blocks[1:]:
        name_m = NAME_PATTERN.search(block)
        id_m = ID_PATTERN.search(block)
        price_m = PRICE_PATTERN.search(block)
        if not name_m or not id_m:
            continue
        raw_name = name_m.group(1).strip()
        item_id = id_m.group(1)
        price = int(re.sub(r"[^\d]", "", price_m.group(1))) if price_m else None
        desc_m = DESC_PATTERN.search(block)
        desc = desc_m.group(1).strip() if desc_m else None

        weight_m = WEIGHT_PATTERN.search(raw_name)
        weight_g = int(weight_m.group(1)) if weight_m else None

        parsed = parse_product(raw_name)
        if parsed["category"] != "ブレンド":
            detected = detect_country_name(raw_name) or (detect_country_name(desc) if desc else None)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name" if detect_country_name(raw_name) else "product_description"
            parsed = apply_category_hint_fallback(parsed, desc or "")

        roast_level = parsed["roast_level"]
        if subcategory == "フレンチ" and not roast_level:
            roast_level = "フレンチロースト"

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": raw_name,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": roast_level,
            "roast_hint": "フレンチ" if subcategory == "フレンチ" else None,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": price,
            "weight_g": weight_g,
            "stock_status": "販売中",
            "out_of_stock": False,
            "product_url": f"{BASE_URL}?class=0&keyword=&superkey=1&FF=&order=&mode=p_wide&id={item_id}",
        })
    return records


def scrape_all_products() -> list[dict]:
    records = []
    for subcategory, url in CATEGORY_URLS.items():
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
        resp.encoding = "shift_jis"
        records.extend(parse_listing(resp.text, subcategory))
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_caravan.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_caravan.json に出力しました")


if __name__ == "__main__":
    main()
