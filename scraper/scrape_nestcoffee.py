# -*- coding: utf-8 -*-
"""
scrape_nestcoffee.py

nest coffee(ネストコーヒー、nest.ocnk.net、鹿児島県鹿児島市中山町2039-1、
自家焙煎豆のオンライン販売)の商品情報を取得する。おちゃのこネット(Ocnk)。

robots.txt確認済み(2026-09時点): 他のOcnk店舗と同一の記述。User-agent: *には
制限なし(GPTBot/Bytespider/TikTokSpider/meta-externalagentのみDisallow: /で
本スクレイパーは該当しない)。

【住所について】
特定商取引法ページ(https://nest.ocnk.net/info)で実データ確認済み(2026-09
時点): 「販売主」欄に「株式会社 KINENBI」「販売店舗 nest coffee」、所在地
「鹿児島県鹿児島市中山町2039-1」との記載を確認。候補リストの住所と一致。

【対象カテゴリについて】
実データ確認済み(2026-09時点): トップページのカテゴリ一覧中「コーヒー豆」
(https://nest.ocnk.net/product-list/3)が対象カテゴリで、全8件(ページネー
ション無し)。他のカテゴリ(コーヒーギフトセット・リキッドベース・
アイスコーヒー・ドリップバッグ・コーヒーバッグ)は非対象のため対象外。
商品名先頭の「【nest coffee】」は店舗名プレフィックスのため除去する。

【価格・重量の取得方法について】
実データ確認済み: 商品ページのog:title/product:price:amountメタタグには
価格が入らない(重量バリエーション制のため)。商品ページ本文の
`pConf.priceArray[1][重量オプションID][挽き方オプションID] = 価格;`という
JS変数割り当てに実際の価格が埋め込まれている。挽き方オプション(豆のまま/
中挽き/細挽き/挽き方はお任せ)によって価格は変わらず、重量オプション
(100g/200g)のみで価格が決まる(8件全てで確認済み)。本スクレイパーは
`<option value="ID">重量g</option>`から重量IDを取得し、
`priceArray[1][重量ID][...]`から対応する価格を取得、最小重量(100g)を
代表として採用する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "nest coffee",
    "url": "https://nest.ocnk.net/",
    "platform": "おちゃのこネット",
    "address": "鹿児島県鹿児島市中山町2039-1",
    "prefecture": "鹿児島県",
    "robots_txt_status": "実質許可(2026-09確認。他のOcnk店舗と同一の記述。"
                          "User-agent: *には制限なし)",
}

BASE_URL = "https://nest.ocnk.net"
CATEGORY_URL = f"{BASE_URL}/product-list/3"  # コーヒー豆カテゴリ
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

SHOP_PREFIX_PATTERN = re.compile(r"^【nest coffee】\s*")
WEIGHT_OPTION_PATTERN = re.compile(r'<option value="(\d+)">\s*(\d+)\s*[gｇ]\s*</option>')
PRICE_ARRAY_PATTERN = re.compile(r"priceArray\[1\]\[(\d+)\]\[(\d+)\]\s*=\s*([\d.]+);")


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def fetch_product_urls() -> list[str]:
    html = fetch_html(CATEGORY_URL)
    urls = sorted(set(re.findall(r'href="(https://nest\.ocnk\.net/product/\d+)"', html)),
                  key=lambda u: int(u.rsplit("/", 1)[-1]))
    return urls


def pick_min_weight_price(html: str) -> tuple[int, int] | None:
    """(重量ID, 重量g)のペアを重量昇順で並べ、最小重量とその価格を返す。"""
    weight_options = [(int(vid), int(g)) for vid, g in WEIGHT_OPTION_PATTERN.findall(html)]
    if not weight_options:
        return None
    weight_options.sort(key=lambda x: x[1])
    min_weight_id, min_weight_g = weight_options[0]

    for wid, _sub_id, price in PRICE_ARRAY_PATTERN.findall(html):
        if int(wid) == min_weight_id:
            return min_weight_g, int(float(price))
    return None


def build_record(title: str, html: str, product_url: str) -> dict | None:
    title = SHOP_PREFIX_PATTERN.sub("", title).strip()
    if not title:
        return None
    parsed = parse_product(title)

    weight_price = pick_min_weight_price(html)
    price = weight_price[1] if weight_price else None
    weight_g = weight_price[0] if weight_price else None

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": product_url,
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
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_product_urls()

    records = []
    flavored_records = []
    for product_url in product_urls:
        try:
            html = fetch_html(product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue

        title_m = re.search(r'<meta property="og:title" content="([^"]*)"', html)
        if not title_m:
            continue
        title = title_m.group(1).split(" | ")[0].strip()

        detail = build_record(title, html, product_url)
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
    with open("data_nestcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_nestcoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
