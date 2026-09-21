# -*- coding: utf-8 -*-
"""
scrape_kscoffee.py

K's coffee(自家焙煎珈琲専門店、kscoffee.shopselect.net、沖縄県浦添市城間4-34-2)の
商品情報を取得する。BASE系(shopselect.net、URL構成・sitemap.xml・/lawページ
ともBASE系店舗と同一)。

【住所について】
特定商取引法ページ(https://kscoffee.shopselect.net/law)で実際に確認したところ
「事業者の名称: k's coffee廣田薫 / 事業者の所在地: 〒901-2133 沖縄県浦添市城間
4-34-2」であることを確認した(2026-09時点)。候補リストの住所と一致。

robots.txt確認済み(2026-09時点): 他のBASE系(shopselect.net)店舗と同一の記述。
curl/python-requests等は個別にDisallow: /指定があるが、User-agent: *
ルールでは実質許可。本スクレイパーは識別可能な独自User-Agentを使用する。

【非コーヒー豆商品の除外について】
実データ確認済み(全13件): 水出しアイスコーヒーパック(コールドブリュー)・
ドリップパック(10個/20個セット、ギフト箱有無問わず)・珈琲ギフト
(100g×2/180g×2パックセット等の詰め合わせ)がNON_BEAN_KEYWORDSで除外される。
残り6件(ストレート4種＋ブレンド2種、いずれも200g)を対象とする。

【flavor_notes(2026-09-21追記)】
実データ確認済み: og:descriptionに対象6件全てでテイスティング文が入って
いる。末尾に「※ご購入の際には、豆の状態を選択してください。挽き豆を
ご希望の場合は…」または「(ご注文の際は)豆のままか挽き豆（細挽き・中挽
き・粗挽き）かお選びください。」という挽き方選択案内の定型文が続くため、
この見出しの直前で打ち切る。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "K's coffee",
    "url": "https://kscoffee.shopselect.net/",
    "platform": "BASE(shopselect.net)",
    "address": "沖縄県浦添市城間4-34-2",
    "prefecture": "沖縄県",
    "robots_txt_status": "実質許可(2026-09確認。他のBASE系(shopselect.net)店舗と同一の記述。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://kscoffee.shopselect.net"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["水出し", "ドリップパック", "ギフト"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
FLAVOR_STOP_PATTERN = re.compile(r"※?ご購入の際には、豆の状態を|(?:ご注文の際は)?豆のままか挽き豆")


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
    title = title_el["content"].split(" | ")[0].strip()
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)

    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None

    desc_el = soup.select_one('meta[property="og:description"]')
    flavor_notes = desc_el["content"].strip() if desc_el and desc_el.get("content") else ""
    m = FLAVOR_STOP_PATTERN.search(flavor_notes)
    if m:
        flavor_notes = flavor_notes[:m.start()].strip()
    flavor_notes = flavor_notes or None

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
    weight_g = int(weight_m.group(1)) if weight_m else None

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
        "flavor_notes": flavor_notes,
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
    with open("data_kscoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kscoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
