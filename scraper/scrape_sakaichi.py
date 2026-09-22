# -*- coding: utf-8 -*-
"""
scrape_sakaichi.py

焙煎工場さかいち(www.sakaichi.com、東京都新宿区戸塚町1-104神戸ビル101、
直火式焙煎機による自家焙煎豆のオンライン販売)の商品情報を取得する。Wix。

【店舗発見の経緯】
高田馬場・早稲田エリアの自家焙煎コーヒー豆店が本アプリに1件も収録されて
いないという利用者からの指摘を受けた総点検で発見(tailoredcafe.jpの
「高田馬場・早稲田のコーヒー豆おすすめ専門店10選」記事経由)。

robots.txt確認済み(2026-09時点): User-agent: * に Allow: /
(lightboxクエリパラメータのみDisallow)。一般クローラーへの制限なし。

【商品データの取得方法について】
KATARU COFFEEと同じくWix Stores標準のstore-products-sitemap.xmlから
全商品ページURLを取得し、各商品ページのJSON-LD(application/ld+json、
@type: Product)のname・description・offers.price・offers.availabilityを
取得する。

【URLスラッグと実際の商品名の不一致について】
実データ確認済み(全19件): Wixの仕様上、商品名を変更してもURLスラッグは
最初に生成された時点の名前のまま残るため、sitemap上のURL文字列(例:
「/product-page/ケニア-ギキリマ農協」)と実際にそのページに表示される
商品名(JSON-LD側のname、例:「エチオピア ケビルゲイシャ農園 100g」)が
一致しないケースが大半だった。ブラウザで実際にページを開いても同じ
食い違いが再現することを確認済みのため、スクレイパーの不具合ではなく
サイト側の実際の状態。raw_nameは必ずJSON-LD側のnameを採用し、URL文字列
からは絶対に商品名を推測しない。

【対象商品について】
実データ確認済み(全19件): 「ドリップバッグ2種15個メール便セット」
(複数ブレンドの個包装ドリップバッグ詰め合わせで単一銘柄を特定できない)
の1件のみ非対象。残る18件が単一銘柄の焙煎豆(ブレンド6・ストレート12)。

【flavor_notes】
実データ確認済み: 全18件のdescriptionが短いテイスティング文のみで、
注文/配送案内等の無関係な定型文の混入は無いため全文をそのまま採用する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "焙煎工場さかいち",
    "url": "https://www.sakaichi.com/",
    "platform": "Wix",
    "address": "東京都新宿区戸塚町1-104神戸ビル101",
    "prefecture": "東京都",
    "robots_txt_status": "許可(2026-09確認。User-agent: *にAllow: /"
                          "[lightboxクエリのみ除外]。一般クローラーへの制限なし)",
}

BASE_URL = "https://www.sakaichi.com"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["ドリップバッグ", "メール便セット", "ギフト"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
# 商品名に重量表記が無い場合のフォールバック(実データ確認済み: 「エルサルバドル
# ブルボン ダンテ農園」の1件のみ商品名に「100g」が無いが、ページ内の数量
# 単位表示「100g（グラム）」から実際の重量を確認できた)
PAGE_WEIGHT_PATTERN = re.compile(r"(\d+)g（グラム）")
JSONLD_PATTERN = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL)


def fetch_page(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def fetch_product_urls() -> list[str]:
    resp = requests.get(f"{BASE_URL}/store-products-sitemap.xml", headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc")]


def extract_product_jsonld(page_html: str) -> dict | None:
    for match in JSONLD_PATTERN.finditer(page_html):
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if data.get("@type") == "Product":
            return data
    return None


def build_record(product_url: str, data: dict, page_html: str) -> dict | None:
    title = (data.get("name") or "").strip()
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    offers = data.get("offers") or {}
    price = None
    if offers.get("price") is not None:
        try:
            price = int(float(offers["price"]))
        except (TypeError, ValueError):
            price = None
    availability = (offers.get("availability") or "").rstrip("/").split("/")[-1]
    structural_out_of_stock = availability not in ("InStock", "")

    parsed = parse_product(title)

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

    weight_m = WEIGHT_PATTERN.search(title)
    if weight_m:
        weight_g = int(weight_m.group(1))
    else:
        page_weight_m = PAGE_WEIGHT_PATTERN.search(page_html)
        weight_g = int(page_weight_m.group(1)) if page_weight_m else None
    stock_status = detect_stock_status(title, structural_out_of_stock)
    description = (data.get("description") or "").strip() or None

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
        "flavor_notes": description,
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
            page_html = fetch_page(product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        data = extract_product_jsonld(page_html)
        if not data:
            continue
        detail = build_record(product_url, data, page_html)
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


def main():
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_sakaichi.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_sakaichi.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
