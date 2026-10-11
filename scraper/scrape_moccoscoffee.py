# -*- coding: utf-8 -*-
"""
scrape_moccoscoffee.py

モッコス珈琲館(moccoscoffee.raku-uru.jp「モッコスオンライン」、熊本県宇城市松橋町両仲間93-1の
松橋本店ほか宇土店・熊機能病院内店の計3店)の商品情報を取得する。熊本名産の「水洗い珈琲」
(水洗いしたコーヒー豆を焙煎する熊本独自の製法)を扱う自家焙煎店。楽々シリーズ(Raku-Uru)。

【店舗発見の経緯】
全国再調査(熊本県)の新規発掘。

【対象商品について】
実データ確認済み(2026-10時点): カテゴリ「珈琲豆販売」(categoryId=59764)全8件
(ストレート6・ブレンド2)すべてを対象とする。カテゴリ「シチリア陶器」は販売中止で0件。
各商品は内容量200g/500g × 豆/粉のバリエーションで、一覧・詳細に表示される販売価格は
最小の200g(豆)の価格のため、重量は200gとする。
商品名の「(水洗い)」は精製ではなく熊本の水洗い焙煎のことで、焙煎度の表記は無いためNone。
在庫は詳細ページの「カートに入れる」ボタン有無と「ただいまご注文いただけません」表示で判定する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "モッコス珈琲館",
    "url": "https://moccoscoffee.raku-uru.jp/",
    "platform": "楽々シリーズ(Raku-Uru)",
    "address": "熊本県宇城市松橋町両仲間93-1",
    "prefecture": "熊本県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://moccoscoffee.raku-uru.jp"
CATEGORY_ID = "59764"
WEIGHT_G = 200
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
# 国名辞書で検出できない産地名(レケンプティ=エチオピア西部ウォレガ地方のモカ)
ORIGIN_OVERRIDES = {"モカ・レケンプティ": "エチオピア"}
NON_BEAN_KEYWORDS = ("セット", "カップ", "陶器")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_item_ids() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/item-list?categoryId={CATEGORY_ID}")
    ids = []
    for a in soup.select('p.item-name a[href^="/item-detail/"]'):
        item_id = a["href"].rsplit("/", 1)[-1]
        if item_id and item_id not in ids:
            ids.append(item_id)
    return ids


def build_record(soup: BeautifulSoup, product_url: str) -> dict | None:
    title_el = soup.select_one("h1.ttl")
    title = title_el.get_text(strip=True) if title_el else ""
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None
    price = None
    price_el = soup.select_one("b.raku-item-vari-price-num")
    if price_el:
        m = re.search(r"([\d,]+)", price_el.get_text())
        if m:
            price = int(m.group(1).replace(",", ""))
    has_add_cart = soup.select_one("a.raku-add-cart") is not None
    has_invalid = soup.select_one("div.item-dtail-orderinvalid") is not None
    sold_out = has_invalid and not has_add_cart

    parsed = parse_product(title)
    if parsed["is_flavored"]:
        return None
    if "ブレンド" in title:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(title)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, title)
        for key, country in ORIGIN_OVERRIDES.items():
            if key in title and not parsed["origin_country"]:
                parsed["origin_country"] = country
                parsed["origin_source"] = "raw_name"
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
        "roast_hint": None,
        "flavor_notes": None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": WEIGHT_G,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": product_url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item_id in fetch_item_ids():
        product_url = f"{BASE_URL}/item-detail/{item_id}"
        try:
            rec = build_record(fetch_page(product_url), product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_moccoscoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_moccoscoffee.json に出力しました")


if __name__ == "__main__":
    main()
