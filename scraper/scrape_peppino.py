# -*- coding: utf-8 -*-
"""
scrape_peppino.py

Peppino Coffee Roaster(peppino.jp、東京都台東区浅草橋、受注焙煎)の商品情報を
取得する。WooCommerce(ITSUKI Coffee Roastelyと同じプラグイン、テーマは
「ankle_tcd092」というこの店舗独自のもの)。

robots.txt確認済み(2026-09時点): User-agent: *に対し、/shop/wp-admin/・
wc-logs/woocommerce_transient_files/woocommerce_uploads の各アップロード
ディレクトリ・add-to-cartクエリパラメータのみDisallow(admin-ajax.phpは
例外的にAllow)。商品ページ自体への制限は無い。

【商品一覧の取得方法について】
実データ確認済み: カテゴリページ(/product-category/specialty-coffee/)は
コーヒー豆以外の商品(ドリップバッグ・ギフトセット・アーモンド・紅茶等)も
混在しておりページネーションもあるため、product-sitemap.xml(全40件、
コーヒー豆以外の商品も含む)を全件取得の起点とし、詳細ページの商品名で
NON_BEAN_KEYWORDSによる除外を行う(BEANS珈琲・GONZO CAFE&BEANSと同じ
「構造化カテゴリに頼らずsitemap全件+キーワード除外」パターン)。

【商品タイトルの在庫待ち表記について】
実データ確認済み: 「（入荷待ち）」がタイトル先頭に付与される商品がある
(例:「（入荷待ち）エチオピア【イルガチャフィーベレカ】...」)。
stock_status_synonyms.jsonの「一時的に品切れ」に既に「入荷待ち」が
登録済みのため、detect_stock_status()がタイトルから自動判定する。

【重量・価格バリエーションについて】
実データ確認済み: WooCommerceの標準的な変動商品(variable product)。
ITSUKI Coffee Roasteryと異なり、この店舗はバリエーションJSONの
"weight"フィールドに直接グラム数(文字列)が入っているため、
attribute_pa_gram等の属性名から正規表現で抽出する必要がない。
在庫のあるバリエーションの中から最小重量のものを代表として採用する。
"""

import json

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "Peppino Coffee Roaster",
    "url": "https://peppino.jp/",
    "platform": "WordPress + WooCommerce",
    "address": "東京都台東区浅草橋2-24-8",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-09確認。User-agent: *に対し/shop/wp-admin/・"
                          "各種アップロードディレクトリ・add-to-cartクエリパラメータのみ"
                          "Disallow。商品ページ自体への制限は無い)",
}

BASE_URL = "https://peppino.jp"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "Almond", "アーモンド", "COLD BREW", "コールドブリュー",
    "ドリップバック", "ドリップバッグ", "はじめてセット",
    "ダージリン", "アールグレイ", "TEA", "GIFT", "ギフト",
    "チョコレート", "CHOCOLATE", "フィルター", "PISTACHIO", "ピスタチオ",
]


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_sitemap_urls() -> list[str]:
    resp = requests.get(f"{BASE_URL}/product-sitemap.xml", headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc")]


def pick_canonical_variant(variations: list[dict]) -> dict | None:
    if not variations:
        return None
    in_stock = [v for v in variations if v.get("is_in_stock")]
    pool = in_stock or variations

    def sort_key(v):
        try:
            return int(v.get("weight") or 0) or float("inf")
        except (TypeError, ValueError):
            return float("inf")

    return min(pool, key=sort_key)


def build_record(soup: BeautifulSoup, product_url: str) -> dict | None:
    title_el = soup.select_one("h1.single_product_title")
    if not title_el:
        return None
    title = title_el.get_text(strip=True)

    if any(kw.lower() in title.lower() for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": None,
            "product_url": product_url,
        }

    variations = []
    form_el = soup.select_one("form.variations_form")
    raw_variations = form_el.get("data-product_variations") if form_el else None
    if raw_variations:
        try:
            variations = json.loads(raw_variations)
        except json.JSONDecodeError:
            variations = []

    variant = pick_canonical_variant(variations)
    if variant is not None:
        price = int(variant["display_price"]) if variant.get("display_price") is not None else None
        weight_g = int(variant["weight"]) if variant.get("weight") else None
    else:
        price_el = soup.select_one(".single_product_price .woocommerce-Price-amount, "
                                    ".product_price .woocommerce-Price-amount")
        price_text = price_el.get_text(strip=True).replace("¥", "").replace(",", "") if price_el else ""
        price = int(price_text) if price_text.isdigit() else None
        weight_g = None

    all_out_of_stock = bool(variations) and not any(v.get("is_in_stock") for v in variations)
    stock_status = detect_stock_status(title, all_out_of_stock)

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
    urls = fetch_sitemap_urls()
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for url in urls:
        prev = previous.get(url)
        try:
            soup = fetch_page(url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {url} ({e})")
            continue

        title_el = soup.select_one("h1.single_product_title")
        title = title_el.get_text(strip=True) if title_el else ""
        if is_unchanged(prev, raw_name=title):
            records.append(prev)
            continue

        detail = build_record(soup, url)
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        url = sys.argv[1]
        result = build_record(fetch_page(url), url)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        records, flavored_records = scrape_all_products()
        output = {
            "shop": SHOP_INFO,
            "products": records,
            "flavored_products_excluded": flavored_records,
        }
        with open("data_peppino.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_peppino.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
