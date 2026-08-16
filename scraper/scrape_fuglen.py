# -*- coding: utf-8 -*-
"""
scrape_fuglen.py

FUGLEN COFFEE ROASTERS(fuglencoffee.jp、Shopify製)の商品情報を取得する。
World Brewers Cup優勝を輩出したノルウェー発のロースター、東京・富ヶ谷が拠点。

robots.txt確認済み(2026-08時点): `User-agent: * / Allow: /`。/collections/配下に
crawl trap除け(sort_by・filter等のクエリパターン)の個別Disallowはあるが、
今回使う `/collections/coffeebeans/products.json` は対象外で許可されている。

【products.jsonエンドポイントを優先利用する理由】
Shopifyストアは標準で `/<collection>/products.json` という公開JSON APIを持つ
(Admin APIではなくストアフロント側の公開エンドポイント)。実際にfetchして
確認したところ200 OKで商品一覧が返り、しかも各商品のbody_html内に
「生産国/生産者/地域/農園/品種/精製方法/標高/収穫時期」というth/td形式の
構造化テーブルと「Flavor Profile」欄がすでに埋め込まれていた。これにより、
他店舗のような「一覧ページ→商品詳細ページ」の2段階クロールが不要になり、
products.jsonへの数回のリクエストだけで全情報が取得できる
(コーヒー豆コレクションは13商品・1ページで収まる規模)。

【価格・重量の扱い】
Shopify商品は「100g 豆のまま」「200g フィルター用に挽く」等、複数のバリアント
(重量・挽き方の組み合わせ)を持つ。在庫があるバリアントのうち最小重量のものを
代表的な価格・重量として採用する(在庫がすべて無い場合は全バリアント中最小)。
表示価格は日本の総額表示義務により税込(他3店舗と同様、Denim bis検証時に
確認した通り)。
"""

import json
import re
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    normalize_processing_method,
    detect_stock_status,
)
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "FUGLEN COFFEE ROASTERS",
    "url": "https://fuglencoffee.jp/",
    "platform": "Shopify(collections/coffeebeans/products.jsonエンドポイントを利用)",
    "address": "東京都渋谷区富ヶ谷1-16-11",
    "prefecture": "東京都",
    "robots_txt_status": "許可(2026-08確認。User-agent:*にAllow:/。collections/products.jsonは対象外のDisallowなし)",
}

BASE_URL = "https://fuglencoffee.jp"
COLLECTION_HANDLE = "coffeebeans"
CRAWL_DELAY_SECONDS = 3
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 構造化テーブルの値が「Natural（ナチュラル）」「Brazil ( ブラジル )」のように
# 「英語 (日本語)」形式(全角/半角括弧どちらもあり)になっているため、
# 括弧内の最後の一致(=日本語表記)を取り出すためのパターン
PAREN_TEXT_PATTERN = re.compile(r"[\(（]\s*([^\)）]+?)\s*[\)）]")


def extract_paren_text(text: str | None) -> str | None:
    if not text:
        return None
    matches = PAREN_TEXT_PATTERN.findall(text)
    return matches[-1] if matches else None


def fetch_products_page(page: int) -> list[dict]:
    url = f"{BASE_URL}/collections/{COLLECTION_HANDLE}/products.json"
    resp = requests.get(url, params={"limit": 250, "page": page}, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json().get("products", [])


def parse_details_table(body_html: str) -> dict:
    """body_html内の詳細テーブル(生産国/生産者/地域/農園/品種/精製方法/標高/
    収穫時期)とFlavor Profile欄を汎用的にキーバリュー抽出する。
    PHILOCOFFEAのBEANS DATA表と同じ「th/td総当たり」方式を踏襲している。"""
    soup = BeautifulSoup(body_html or "", "html.parser")

    raw = {}
    table = soup.select_one("table.details-table")
    if table:
        for tr in table.select("tr"):
            th = tr.select_one("th")
            td = tr.select_one("td")
            if th and td:
                value = re.sub(r"\s+", " ", td.get_text(separator=" ", strip=True))
                raw[th.get_text(strip=True)] = value or None

    flavor_el = soup.select_one(".flavor-description")
    flavor_notes = re.sub(r"\s+", " ", flavor_el.get_text(separator=" ", strip=True)) if flavor_el else None

    return {"table": raw, "flavor_notes": flavor_notes}


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    """複数の重量・挽き方バリアントの中から、代表として使う1件を選ぶ。
    在庫があるバリアントの中で最小重量のものを優先し、無ければ全バリアント中
    最小重量のものを使う(サイズ違いの重複行を避け、最小構成の価格を代表値にする)。"""
    if not variants:
        return None
    available = [v for v in variants if v.get("available")]
    pool = available or variants
    return min(pool, key=lambda v: v.get("grams") or float("inf"))


def build_record(product: dict) -> dict:
    title = product.get("title", "")
    product_url = f"{BASE_URL}/products/{product.get('handle')}"
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        variant = pick_canonical_variant(product.get("variants", []))
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": int(float(variant["price"])) if variant else None,
            "product_url": product_url,
        }

    details = parse_details_table(product.get("body_html", ""))
    table = details["table"]

    # 構造化テーブルの生産国表記は商品名からのキーワード推測より確実なため優先する
    # (MiLL Coffee・PHILOCOFFEAの「説明文優先」方針を踏襲)
    origin_ja = extract_paren_text(table.get("生産国")) or table.get("生産国")
    if origin_ja:
        parsed["origin_country"] = origin_ja
        parsed["origin_source"] = "product_description"
    parsed = apply_category_hint_fallback(parsed, None)

    processing_raw = table.get("精製方法")
    if processing_raw:
        processing_ja = extract_paren_text(processing_raw) or processing_raw
        parsed["processing_method"] = normalize_processing_method(processing_ja)

    variant = pick_canonical_variant(product.get("variants", []))
    # 全バリアントが品切れかどうかの構造化フラグ(Shopifyのavailable)を、
    # 商品名の「SOLD OUT」表記(実データ確認済み: FUGLENは品切れ商品の
    # タイトル先頭に【SOLD OUT】を付ける運用)と合わせて正規化する。
    structural_out_of_stock = not any(v.get("available") for v in product.get("variants", []))
    stock_status = detect_stock_status(title, structural_out_of_stock)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": None,  # サイト上に焙煎度の指定が見当たらないため注文時選択扱い
        "roast_selectable": True,
        "producer_name": table.get("生産者"),
        "farm_name": table.get("農園"),
        "region_detail": table.get("地域"),
        "altitude_note": table.get("標高"),
        "variety": extract_paren_text(table.get("品種")) or table.get("品種"),
        "harvest_note": table.get("収穫時期"),
        "flavor_notes": details["flavor_notes"],
        "price": int(float(variant["price"])) if variant else None,
        "weight_g": variant.get("grams") if variant else None,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    all_raw = []
    page = 1
    while True:
        batch = fetch_products_page(page)
        if not batch:
            break
        all_raw.extend(batch)
        page += 1
        time.sleep(CRAWL_DELAY_SECONDS)

    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for product in all_raw:
        product_url = f"{BASE_URL}/products/{product.get('handle')}"
        variant = pick_canonical_variant(product.get("variants", []))
        current_price = int(float(variant["price"])) if variant else None
        current_out_of_stock = not any(v.get("available") for v in product.get("variants", []))

        prev = previous.get(product_url)
        if is_unchanged(
            prev,
            raw_name=product.get("title", ""),
            price=current_price,
            out_of_stock=current_out_of_stock,
        ):
            records.append(prev)
            continue

        record = build_record(product)
        if record.get("is_flavored"):
            flavored_records.append(record)
        else:
            records.append(record)

    return records, flavored_records


def main():
    records, flavored_records = scrape_all_products()

    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }

    with open("data_fuglen.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[done] {len(records)}件を data_fuglen.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
