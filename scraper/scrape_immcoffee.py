# -*- coding: utf-8 -*-
"""
scrape_immcoffee.py

imm coffee&roastery(shop.imm-coffee.com、山口県岩国市岩国1丁目20-46、
自家焙煎豆のオンライン販売、運営：株式会社イム)の商品情報を取得する。BASE。

【住所について】
公式ストアの特定商取引法ページ(https://shop.imm-coffee.com/law)で実データ
確認済み(2026-09時点): 「会社名 株式会社イム / 事業者の所在地　〒741-0062
山口県岩国市岩国1-20-46」。候補リストの住所と一致。

robots.txt確認済み(2026-09時点): 他のBASE系店舗と同一の記述。curl/python-
requests等は個別にDisallow: /指定があるが、User-agent: *ルールでは実質許可。
本スクレイパーは識別可能な独自User-Agentを使用する。

【非コーヒー豆商品の除外について】
実データ確認済み(2026-09時点、全32件): 手ぬぐい等の雑貨・ドリップバッグ(表記
ゆれ「ドリップバック」を含む)・コールドブリュー(液体)・ギフト・セット商品・
複数パック詰め合わせ(「コーヒー豆100g×3パック」のように産地非依存)・
ライト/ミディアムロースト「アソート」(複数銘柄の詰め合わせ)・OH MY COFFEE
ブランドのサコッシュ(バッグ、雑貨)・器具類が含まれる。NON_BEAN_KEYWORDSで
除外し、コーヒー豆単品(産地名を持つストレート)のみを対象とする。

【重量の「1kg」表記について】
実データ確認済み: 「Brazil 1kg」のようにキログラム単位の商品があるため、
WEIGHT_PATTERNは[kK]?[gｇ]に対応し、kg単位はグラムに変換する。

【flavor_notes(2026-09-21追記)】
実データ確認済み: og:descriptionに対象8件中7件で農園ストーリー・
テイスティング文が入っており、末尾に「配送について」で始まる配送案内の
定型文が続くため打ち切る。残り1件(Brazil 1kg)は「BrazilROASTDark
roast」という産地・焙煎度のみの簡潔な表記でテイスティング文を含まない
が、すぎた珈琲等の先例に倣いサイト上の実データをそのまま採用する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "imm coffee&roastery",
    "url": "https://shop.imm-coffee.com/",
    "platform": "BASE",
    "address": "山口県岩国市岩国1丁目20-46",
    "prefecture": "山口県",
    "robots_txt_status": "実質許可(2026-09確認。他のBASE系店舗と同一の記述。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://shop.imm-coffee.com"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "手ぬぐい", "ドリップバッグ", "ドリップバック", "ドリップパック", "ギフト",
    "セット", "雑貨", "タンブラー", "マグカップ", "Tシャツ", "トートバッグ",
    "水出し", "コールドブリュー", "パック", "アソート", "SACOCHE",
]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*(kg|[gｇ])", re.IGNORECASE)
FIXED_WEIGHT_G = 100
FLAVOR_STOP_PATTERN = re.compile(r"配送について")


def extract_flavor_notes(soup: BeautifulSoup) -> str | None:
    """理由はモジュールdocstring参照。"""
    desc_el = soup.select_one('meta[property="og:description"]')
    if not desc_el or not desc_el.get("content"):
        return None
    desc = desc_el["content"]
    m = FLAVOR_STOP_PATTERN.search(desc)
    text = desc[:m.start()] if m else desc
    return text.strip() or None


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def fetch_item_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "/items/" in loc.get_text()]


def build_record(soup: BeautifulSoup, product_url: str) -> dict | None:
    title_el = soup.select_one('meta[property="og:title"]')
    if not title_el or not title_el.get("content"):
        return None
    title = title_el["content"].split(" | ")[0].split(" powered by BASE")[0].strip()
    if not title or any(kw.lower() in title.lower() for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)

    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None

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
        if weight_m.group(2).lower() == "kg":
            weight_g *= 1000
    else:
        weight_g = FIXED_WEIGHT_G

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
        "flavor_notes": extract_flavor_notes(soup),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
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
    for item_url in item_urls:
        try:
            detail = build_record(fetch_page(item_url), item_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item_url} ({e})")
            continue
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
    with open("data_immcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_immcoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
