# -*- coding: utf-8 -*-
"""
scrape_caffevita.py

CAFFE VITA(カフェヴィータ、caffe-vita.com、島根県松江市学園2-5-3、自家焙煎
エスプレッソコーヒーのオンライン販売)の商品情報を取得する。

【プラットフォームについて】
実データ確認済み: BASE/カラーミー/Shopify/STORES等の汎用ASPではなく、
静的HTML+PHPの独自カート(online_shop.php、cart.php)。robots.txtが存在しない
(404)ため制限なし。商品情報(商品名・重量選択肢・挽き方選択肢・価格)は
online_shop.php1ページに全14件が静的HTMLとして直接記載されている(JS
レンダリング不要)。個別の商品ページは存在しないため、product_urlはnullにする
(全商品で同一URLを共有すると、aggregate_shops.pyのid生成ロジック
(product_url優先、無ければshop_name:raw_nameにフォールバック)で複数商品が
同一IDに衝突してしまう)。

【非コーヒー豆商品の除外について】
実データ確認済み(全14件): 「ギフト箱包装」(コーヒー豆本体ではなく箱詰め
包装サービス自体の商品)1件のみ非対象。NON_BEAN_KEYWORDSで除外する。残り
13件(産地ストレート6種＋ブレンド7種)を対象とする。

【重量・価格について】
実データ確認済み: 各商品は200g/300g/400g/500gの4段階の重量選択肢を持つ
プルダウン式の購入フォームで、価格表示は「￥1728 / 200g ～」のように基準
重量(200g)の価格のみが明記されている(300g以上の価格は個別に表示されない)。
基準重量200gの価格を代表として採用する。

【商品名の産地について】
実データ確認済み: 「コスタリカ　ハニープロセス」「ブラジル　CAFFE VITA農園
ナチュラル」のように産地国名が商品名先頭に付くストレート商品と、
「エスプレッソブレンド」「ヴィータブレンド」等のブレンド商品が混在する。

【flavor_notes(2026-09-21追記)】
実データ確認済み: 各div.shop_cts内の「豆の特徴」見出しに続くp.materialに
テイスティング文が直接入っており(対象13件全て確認)、価格・スペック等の
混入は無いため全文をそのまま採用する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "CAFFE VITA",
    "url": "https://www.caffe-vita.com/",
    "platform": "独自カート(静的HTML+PHP)",
    "address": "島根県松江市学園2-5-3",
    "prefecture": "島根県",
    "robots_txt_status": "制限なし(2026-09確認。robots.txt自体が存在しない[404])",
}

PRODUCT_PAGE_URL = "https://www.caffe-vita.com/online_shop.php"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["ギフト箱包装"]
REPRESENTATIVE_WEIGHT_G = 200  # 理由はモジュールdocstring参照
PRICE_PATTERN = re.compile(r"￥([\d,]+)")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def scrape_item_list() -> list[dict]:
    soup = fetch_page(PRODUCT_PAGE_URL)
    results = []
    for block in soup.select("div.shop_cts"):
        name_el = block.select_one("h2")
        if not name_el:
            continue
        raw_name = name_el.get_text(strip=True)

        price_el = block.select_one("p.price")
        price = None
        if price_el:
            m = PRICE_PATTERN.search(price_el.get_text())
            if m:
                price = int(m.group(1).replace(",", ""))

        material_el = block.select_one("p.material")
        flavor_notes = material_el.get_text(strip=True) if material_el else None

        results.append({"raw_name": raw_name, "price": price, "flavor_notes": flavor_notes or None})
    return results


def build_record(item: dict) -> dict | None:
    title = item["raw_name"]
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": item["price"],
            "product_url": None,
        }

    stock_status = detect_stock_status(title)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "flavor_notes": item.get("flavor_notes"),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": REPRESENTATIVE_WEIGHT_G,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": None,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    items = scrape_item_list()

    records = []
    flavored_records = []
    for item in items:
        detail = build_record(item)
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


if __name__ == "__main__":
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_caffevita.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_caffevita.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
