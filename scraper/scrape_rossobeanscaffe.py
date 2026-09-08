# -*- coding: utf-8 -*-
"""
scrape_rossobeanscaffe.py

ロッソビーンズカフェ(rossobeanscaffe.com、大阪府池田市栄町3-14、自家焙煎豆/
生豆のオンライン販売)の商品情報を取得する。MakeShop(schema.org Product形式の
JSON-LD構造化データを使用。カフェコーデと同じMakeShopだが、こちらは
ProductGroup/hasVariantではなく単一Productオブジェクトの配列で商品名・
価格・在庫状況が入っている)。

住所は自社サイトのご利用ガイドページ(https://www.rossobeanscaffe.com/hpgen/
HPB/shop/shoppinguide.html 、「Rosso Beans Caffe ADDRESS: 大阪府池田市栄町
３－１４」)で確認済み。

robots.txt確認済み(2026-09時点): robots.txt自体が存在しない(404)ため、
Disallow指定は無く実質許可。

【商品一覧の取得方法について】
実データ確認済み: トップページのナビゲーションには「限定豆」「サブスク
コーヒー」「おすすめ商品」「香りで選ぶ(4区分)」「価格で選ぶ」「(国別、
17か国)」「ドリップバッグ」「焙煎豆・生豆ギフト」「砂糖・ミルク」「コーヒー
器具」がある。国別17カテゴリ(親カテゴリ207138)と「限定豆」(207130)を
巡回すれば全25件のストレート豆(+限定豆1件)を過不足なく収集できることを
実データで確認済み(「香りで選ぶ」「価格で選ぶ」「おすすめ商品」は同一商品
への重複導線、「サブスクコーヒー」は下記の通り非対象、「ドリップバッグ」
「焙煎豆・生豆ギフト」「砂糖・ミルク」「コーヒー器具」は非対象カテゴリ)。

【非コーヒー豆商品の除外について】
実データ確認済み: 国別カテゴリページには「ギフトボックス（２種）／自由に
選んで詰めるギフト／」等のギフトボックス商品(SKU: r002gftbox〜)が同一
カテゴリ内に混在して掲載されている。NON_BEAN_KEYWORDSの「ギフト」で除外
する。また「サブスクコーヒー」カテゴリ(235531)の全5件は実データ確認済み
(例:「【まかせて安心】コーヒー選びにお悩みの方へおすすめ！店長セレクト豆
100g3種セット(送料込）」)で、いずれも複数銘柄を100gずつ詰め合わせる
定期便向けバラエティセットであり単一銘柄の豆単品ではないため、そもそも
巡回対象に含めない。

【価格・重量表記について】
実データ確認済み: 全25件が生豆100gあたりの税込単価表示(商品説明に
「生豆は100gから、焙煎豆は300gからご注文いただけます。表示価格は100g
当たりの税込金額です。」と明記)であり、固定包装重量の商品ではなく購入時に
数量(100g単位、焙煎豆は最低300g)を選択する方式。そのため本スクレイパーは
価格を100gあたりの単価として扱い、weight_gは基準の100gを採用する
(カラーミー系の少量計り売り品と異なり、こちらは全銘柄が同一の単価表示
方式であるため除外はしない)。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "ロッソビーンズカフェ",
    "url": "https://www.rossobeanscaffe.com/",
    "platform": "MakeShop",
    "address": "大阪府池田市栄町3-14",
    "prefecture": "大阪府",
    "robots_txt_status": "実質許可(2026-09確認。robots.txt自体が存在しない(404)ため"
                          "Disallow指定は無い)",
}

BASE_URL = "https://www.rossobeanscaffe.com"
CATEGORY_PATHS = [
    "SHOP/207130/list.html",  # 限定豆
    "SHOP/207138/207139/list.html",  # インドネシア
    "SHOP/207138/207140/list.html",  # イエメン
    "SHOP/207138/207141/list.html",  # エチオピア
    "SHOP/207138/207142/list.html",  # ケニア
    "SHOP/207138/207143/list.html",  # タンザニア
    "SHOP/207138/207144/list.html",  # 中国
    "SHOP/207138/207145/list.html",  # インド
    "SHOP/207138/207146/list.html",  # メキシコ
    "SHOP/207138/207147/list.html",  # ガテマラ
    "SHOP/207138/207148/list.html",  # ドミニカ
    "SHOP/207138/207149/list.html",  # コスタリカ
    "SHOP/207138/207150/list.html",  # キューバ
    "SHOP/207138/207151/list.html",  # ホンジュラス
    "SHOP/207138/207152/list.html",  # ニューギニア
    "SHOP/207138/207153/list.html",  # ハワイ
    "SHOP/207138/207154/list.html",  # ブラジル
    "SHOP/207138/207155/list.html",  # コロンビア
    "SHOP/207138/207156/list.html",  # エクアドル
    "SHOP/207138/207157/list.html",  # ジャマイカ
    "SHOP/207138/207158/list.html",  # ペルー
]
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["ギフト"]
PRODUCT_URL_PATTERN = re.compile(r"^/SHOP/([A-Za-z0-9]+)\.html$")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_product_urls() -> list[str]:
    codes: set[str] = set()
    for path in CATEGORY_PATHS:
        soup = fetch_page(f"{BASE_URL}/{path}")
        for a in soup.select('a[href^="/SHOP/"]'):
            m = PRODUCT_URL_PATTERN.match(a.get("href", ""))
            if m:
                codes.add(m.group(1))
    return [f"{BASE_URL}/SHOP/{code}.html" for code in codes]


def extract_product(html: str) -> dict | None:
    for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        candidates = data if isinstance(data, list) else [data]
        for candidate in candidates:
            if candidate.get("@type") == "Product":
                return candidate
    return None


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_product_urls()

    records = []
    flavored_records = []
    for product_url in product_urls:
        try:
            resp = requests.get(product_url, headers=REQUEST_HEADERS, timeout=15)
            resp.raise_for_status()
            html = resp.text
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue

        product = extract_product(html)
        if not product:
            continue
        title = re.sub(r"\s+", " ", (product.get("name") or "")).strip()
        if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
            continue

        offers = product.get("offers") or {}
        price_raw = offers.get("price")
        price = int(float(price_raw)) if price_raw is not None else None
        structural_out_of_stock = offers.get("availability") == "http://schema.org/OutOfStock"

        parsed = parse_product(title)

        if parsed["is_flavored"]:
            flavored_records.append({
                "shop_name": SHOP_INFO["name"],
                "raw_name": title,
                "category": "フレーバー",
                "is_flavored": True,
                "flavor_name": parsed["flavor_name"],
                "price": price,
                "product_url": product_url,
            })
            continue

        stock_status = detect_stock_status(title, structural_out_of_stock)

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
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
            # 全銘柄が生豆100gあたりの税込単価表示(docstring参照)のため100gを採用
            "weight_g": 100,
            "stock_status": stock_status,
            "out_of_stock": stock_status != "販売中",
            "product_url": product_url,
        })

    return records, flavored_records


if __name__ == "__main__":
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_rossobeanscaffe.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_rossobeanscaffe.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
