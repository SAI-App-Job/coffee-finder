# -*- coding: utf-8 -*-
"""
scrape_littlewingcoffee.py

リトルウイング珈琲(広島県福山市、公式 littlewing-coffee.com〈グーペ〉、1号店マツナガ=福山市今津町3-2-28
さんらいず内、2号店フクヤマ=福山市大黒町1-23-A)の商品情報を取得する。店舗のwebshopは
littlewing-coffee.raku-uru.jp(楽々シリーズ/Raku-Uru。scrape_sabucoffee.py等と同一プラットフォーム)。

【ソース選択の経緯(2026-10-06確認)】
公式サイトの「メール・FAX注文」ページ(/free/coffeetuuhan)には豆10銘柄(200g 1,600〜2,000円)の
通販商品リストがあるが、同じ銘柄(例: グァテマラ・サンセバスチャン農園 中深煎り)のRaku-Uru上の販売価格は
2,380円で、メール・FAX注文リストと価格が食い違う。Raku-Uruは商品ごとのページ・在庫フラグを持ち、
実際のカート価格であるため、本スクリプトはRaku-Uruを正とする。

【対象商品について】
豆のまま(粉を除く)のカテゴリのみ: 浅煎り(58432)、中深煎り(58434)、深煎り(58436)。
粉カテゴリ(58433/58435/58437)は同一商品の挽き違いのため対象外。ギフト・ドリップバッグ・リキッド
アイスコーヒー・水出し用パックも対象外。焙煎度はカテゴリ名から取得する。
各商品は「(豆のまま・200g)」の1重量のみで、重量は商品名から取得する。
在庫は a.raku-add-cart の有無、div.item-dtail-orderinvalid の有無で判定する(scrape_sabucoffee.pyと同じ)。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "リトルウイング珈琲",
    "url": "https://littlewing-coffee.raku-uru.jp/",
    "platform": "楽々シリーズ(Raku-Uru)",
    "address": "広島県福山市今津町3-2-28",
    "prefecture": "広島県",
    "robots_txt_status": "未確認(標準的なRaku-Uru設定。一覧・詳細ページのみ使用)",
}

BASE_URL = "https://littlewing-coffee.raku-uru.jp"
BEAN_CATEGORIES = {
    "58432": "浅煎り",
    "58434": "中深煎り",
    "58436": "深煎り",
}
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 1
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    return BeautifulSoup(resp.content.decode("utf-8", errors="replace"), "html.parser")


def fetch_items() -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    seen = set()
    for cat, roast in BEAN_CATEGORIES.items():
        soup = fetch_page(f"{BASE_URL}/item-list?categoryId={cat}")
        for a in soup.select('a[href^="/item-detail/"]'):
            item_id = a["href"].rsplit("/", 1)[-1]
            if item_id and item_id not in seen and a.get_text(strip=True):
                seen.add(item_id)
                items.append((item_id, roast))
        time.sleep(CRAWL_DELAY_SECONDS)
    return items


def clean_title(title: str) -> str:
    name = re.sub(r"[（(][^）)]*[gｇ][^）)]*[）)]", "", title)  # 「（豆のまま・200g）」を除去
    return re.sub(r"[\s　]+", " ", name).strip()


def build_record(item_id: str, roast: str) -> dict | None:
    product_url = f"{BASE_URL}/item-detail/{item_id}"
    soup = fetch_page(product_url)
    title_el = soup.select_one("h1.title1")
    if not title_el:
        return None
    title = title_el.get_text(strip=True)

    price = None
    price_el = soup.select_one("b.raku-item-vari-price-num")
    if price_el:
        m = re.search(r"([\d,]+)", price_el.get_text())
        if m:
            price = int(m.group(1).replace(",", ""))

    wm = WEIGHT_PATTERN.search(title)
    weight = int(wm.group(1)) if wm else None
    name = clean_title(title)

    desc_el = soup.select_one("div.item-detail-txt1")
    desc = re.sub(r"\n+", " ", desc_el.get_text("\n", strip=True)) if desc_el else None
    if desc:
        desc = re.sub(r"^商品詳細\s*", "", desc)[:400]

    parsed = parse_product(name)
    if "ブレンド" in name:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)

    has_orderinvalid = soup.select_one("div.item-dtail-orderinvalid") is not None
    has_add_cart = soup.select_one("a.raku-add-cart") is not None
    stock_status = detect_stock_status(title, has_orderinvalid and not has_add_cart)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast,
        "roast_hint": None,
        "flavor_notes": desc or None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item_id, roast in fetch_items():
        time.sleep(CRAWL_DELAY_SECONDS)
        rec = build_record(item_id, roast)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_littlewingcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_littlewingcoffee.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], "|", r["category"], r["origin_country"], r["roast_level"], r["price"], r["weight_g"], r["stock_status"])
        print("     ", (r["flavor_notes"] or "")[:80])


if __name__ == "__main__":
    main()
