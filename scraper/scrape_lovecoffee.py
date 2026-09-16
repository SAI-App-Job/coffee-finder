# -*- coding: utf-8 -*-
"""
scrape_lovecoffee.py

らぶこーひー自家焙煎豆店(lovecoffeejikabaisen.com、札幌市北区東茨戸三条
1-16-11、WordPress+WooCommerce)の商品情報を取得する。

住所は特定商取引法(利用規約)ページ(https://lovecoffeejikabaisen.com/terms/)
で実データ確認済み(2026-09時点、〒002-8044 北海道札幌市北区東茨戸三条
1-16-11)。

【対象商品の絞り込みについて】
実データ確認済み(Store API /wp-json/wc/store/v1/products、全46件):
単一銘柄のコーヒー豆商品は商品名に「【¥1200／100g】」のように単価が
埋め込まれているという固有の命名規則があり、これを正規表現で検出して
対象商品を絞り込む(該当17件)。他の29件(お試しセット・定期便「たのしくる」・
ドリップバッグ単品/詰め合わせ・ギフトセット・グッズ・ナッツ・バナナ
チップ・水出しパック等)はこのパターンに一致しないため自然に除外される。

【価格・重量の取得方法について】
実データ確認済み: 対象17件は全てWooCommerceの`type: "variable"`(可変
商品)で、Store APIのprices.priceは最安バリアント(スペシャルティ贅沢
ドリップバッグ、ドリップバッグ形態で量り売りの豆ではない)の価格になって
しまうため使えない。個別の商品ページ(/product/<id>/)のHTML内
`data-product_variations`属性(JSON)から、挽き方選択肢「豆のまま」
(attribute_pa_type1=category01、全商品で共通のterm slugであることを
実データ複数商品で確認済み)に対応するバリアントのdisplay_priceを採用する。
重量は商品名の「／100g」表記から100gに固定。

robots.txt確認済み(2026-09時点): /wp-admin/と一部WooCommerce内部パスの
みDisallow(admin-ajax.phpは個別にAllow)。本スクレイパーが使うStore API・
商品ページは制限対象外。
"""

import json
import re

import requests

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "らぶこーひー自家焙煎豆店",
    "url": "https://lovecoffeejikabaisen.com/",
    "platform": "WooCommerce",
    "address": "北海道札幌市北区東茨戸三条1-16-11",
    "prefecture": "北海道",
    "robots_txt_status": "実質許可(2026-09確認。/wp-admin/等のみDisallow、"
                          "本スクレイパーが使うStore API・商品ページは制限対象外)",
}

API_URL = "https://lovecoffeejikabaisen.com/wp-json/wc/store/v1/products"
BASE_URL = "https://lovecoffeejikabaisen.com"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 理由はモジュールdocstring参照(単一銘柄の100gコーヒー豆であることを示す固有表記)
PRICE_TAG_PATTERN = re.compile(r"【¥[\d,]+／100g\s*】")
WHOLE_BEAN_ATTRIBUTE_VALUE = "category01"  # 実データ複数商品で確認済み(「豆のまま」)
VARIATIONS_ATTR_PATTERN = re.compile(r'data-product_variations="([^"]+)"')


def fetch_all_products() -> list[dict]:
    products = []
    page = 1
    while True:
        resp = requests.get(
            API_URL, headers=REQUEST_HEADERS, params={"per_page": 100, "page": page}, timeout=20
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        products.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return products


def fetch_whole_bean_variant(permalink: str) -> dict | None:
    resp = requests.get(permalink, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    m = VARIATIONS_ATTR_PATTERN.search(resp.text)
    if not m:
        return None
    try:
        import html as html_module
        variations = json.loads(html_module.unescape(m.group(1)))
    except (json.JSONDecodeError, ValueError):
        return None
    for v in variations:
        if v.get("attributes", {}).get("attribute_pa_type1") == WHOLE_BEAN_ATTRIBUTE_VALUE:
            return v
    return variations[0] if variations else None


def build_record(product: dict) -> dict | None:
    name = (product.get("name") or "").strip()
    if not name or not PRICE_TAG_PATTERN.search(name):
        return None

    permalink = product.get("permalink")
    try:
        variant = fetch_whole_bean_variant(permalink) if permalink else None
    except requests.RequestException as e:
        print(f"[warn] 詳細ページ取得失敗: {permalink} ({e})")
        variant = None

    price = variant.get("display_price") if variant else None
    if price is not None:
        price = int(price)
    structural_out_of_stock = variant is not None and not variant.get("is_in_stock", True)

    parsed = parse_product(name)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": permalink,
        }

    stock_status = detect_stock_status(name, structural_out_of_stock)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": 100,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": permalink,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    products = fetch_all_products()

    records = []
    flavored_records = []
    for product in products:
        detail = build_record(product)
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


if __name__ == "__main__":
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_lovecoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_lovecoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
