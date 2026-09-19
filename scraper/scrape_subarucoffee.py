# -*- coding: utf-8 -*-
"""
scrape_subarucoffee.py

昴珈琲店(www.subarucoffee.shop、〒737-0046 広島県呉市中通2丁目5-3、
自家焙煎豆のオンライン販売)の商品情報を取得する。プラットフォーム:
独自ECシステム(会社公式サイトはsubarucoffee.co.jpだが、オンラインショップ
は別ドメインのsubarucoffee.shopで運営。BASE/Shopify/カラーミー/Ocnk/
theShop/EC Force等のいずれにも該当しない独自カート、クラスに"sys"
プレフィックスが付く特徴的な命名から判断)。

【住所について】
候補リストの「呉本店」の住所は公式サイト(https://www.subarucoffee.co.jp/
company/)で実データ確認し、候補リストと一致することを確認した(2026-09
時点)。

robots.txt確認済み(2026-09時点): www.subarucoffee.shopにrobots.txtが
存在しない(404)。User-Agent別の制限記述が無いため実質的にクロール制限
なしと判断した。

【商品一覧・価格の取得方法について】
実データ確認済み: カテゴリ一覧ページ(/ic/home等)は商品カードがJSで
動的に描画されており、静的HTMLには商品情報が含まれない
(price要素`class="sysRetailPrice"`が空、`/ic/home`静的HTMLに商品リンクが
0件)。一方、個別商品ページ(/i/<ID>)にはschema.org Product/ProductGroupの
JSON-LD構造化データが静的に埋め込まれており、価格・在庫状況を含む正確な
情報がJSレンダリング無しで取得できる(実データ確認済み)。sitemap.xmlに
全166件の/i/<ID>ページが列挙されているため、これを起点に全件クロールする。

【対象商品について】
実データ確認済み(sitemap.xmlの166件を広く抽出調査): 商品ラインは
「レギュラーコーヒー <銘柄>」(重量指定のコーヒー豆量り売り、
ProductGroupのhasVariantに「100gパック」「200gパック」の2バリアント)
のみが対象。「フレッシュバッグ <銘柄>」は１杯分ずつの使い切りパック
(バラ/5個入/10個入で、豆の量り売りではない)、「海軍さんの珈琲◯g(粉)
小箱」はお土産用の化粧箱入りギフト、「KING OF ICE」「Queen of ICE」は
瓶入りアイスコーヒー完成品、「海軍さんの冬/夏ギフト」「広島・呉のお
手土産ギフト」等は複数商品の詰め合わせギフト、「カフェインレス珈琲
30袋入」はドリップバッグ形態、「オリジナルエコバッグ」は雑貨——
いずれもコーヒー豆単品の量り売りではないため非対象。タイトルが
「レギュラーコーヒー」で始まる商品のみを対象とする。

【重量違いの重複について】
実データ確認済み: 「レギュラーコーヒー <銘柄>」はProductGroupの
hasVariantに「100gパック」「200gパック」の2バリアントを持つ。最小重量
(100g)を代表として採用する。

【flavor_notes(テイスティングノート)について(2026-09-20追記)】
実データ確認済み(33商品サンプル調査): JSON-LDのProductGroupに
"description"フィールドとして店主による風味紹介文がそのまま含まれて
おり、HTML解析なしで取得できる。以前はprice/在庫状況のみ取得し、この
フィールド自体を一切読んでいなかった。サンプル全件で定型注記等の混入は
無く、そのまま採用してよい。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "昴珈琲店",
    "url": "https://www.subarucoffee.shop/",
    "platform": "独自ECシステム",
    "address": "広島県呉市中通2丁目5-3",
    "prefecture": "広島県",
    "robots_txt_status": "実質許可(2026-09確認。www.subarucoffee.shopにrobots.txt自体が"
                          "存在せず(404)、クロール制限の記述がないため実質無制限と判断)",
}

BASE_URL = "https://www.subarucoffee.shop"
SITEMAP_URL = f"{BASE_URL}/sitemap.xml"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

TARGET_PREFIX = "レギュラーコーヒー"
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
JSON_LD_PATTERN = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


def fetch_page_text(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.text


def fetch_item_urls() -> list[str]:
    resp = requests.get(SITEMAP_URL, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    return [
        loc.get_text(strip=True) for loc in soup.find_all("loc")
        if re.search(r"/i/\d+$", loc.get_text(strip=True))
    ]


def extract_product_ld(html: str) -> dict | None:
    m = JSON_LD_PATTERN.search(html)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    if not variants:
        return None

    def weight_key(v):
        w = WEIGHT_PATTERN.search(v.get("name") or "")
        return int(w.group(1)) if w else float("inf")

    return sorted(variants, key=weight_key)[0]


def build_record(base_title: str, variant: dict, product_url: str, flavor_notes: str | None = None) -> dict | None:
    parsed = parse_product(base_title)
    offer = variant.get("offers") or {}
    price = offer.get("price")
    price = int(price) if price is not None else None
    availability = offer.get("availability") or ""
    out_of_stock = "InStock" not in availability

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": base_title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": product_url,
        }

    weight_m = WEIGHT_PATTERN.search(variant.get("name") or "")
    weight_g = int(weight_m.group(1)) if weight_m else None
    stock_status = detect_stock_status(base_title, out_of_stock)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": base_title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "flavor_notes": flavor_notes,
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    item_urls = fetch_item_urls()

    records = []
    flavored_records = []
    for url in item_urls:
        try:
            html = fetch_page_text(url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {url} ({e})")
            continue

        data = extract_product_ld(html)
        if not data:
            continue

        title = (data.get("name") or "").strip()
        if not title.startswith(TARGET_PREFIX):
            continue
        base_title = title[len(TARGET_PREFIX):].strip()

        variants = data.get("hasVariant") or ([data] if data.get("offers") else [])
        variant = pick_canonical_variant(variants)
        if variant is None:
            continue

        detail = build_record(base_title, variant, url, (data.get("description") or "").strip() or None)
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
    with open("data_subarucoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_subarucoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
