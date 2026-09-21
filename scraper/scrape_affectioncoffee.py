# -*- coding: utf-8 -*-
"""
scrape_affectioncoffee.py

自家焙煎アフェクショネイト珈琲(affection.shopselect.net、鳥取県鳥取市古海
633-7、自家焙煎豆のオンライン販売)の商品情報を取得する。

【プラットフォームについて】
実データ確認済み: ドメインはshopselect.net(旧BASEブランドの一つ)だが、
ページ内のCSSがthebase.in/thebase.comのアセットを参照しており、URL構成も
/items/<ID>・/law・sitemap.xmlともBASE系店舗と完全に同一。BASEと同じ方法で
スクレイピング可能なため、他のBASE系スクレイパーと同じ実装方針を採用する。

【住所について】
候補リストでは実店舗の住所(鳥取市吉岡温泉町465)とtokushoho記載の住所
(鳥取市古海633-7)のどちらを使うか要確認とされていたが、公式ストアの特定商
取引法ページ(https://affection.shopselect.net/law)で実データ確認済み
(2026-09時点): 「事業者の名称 林裕介 / 事業者の所在地　〒6800921 鳥取県
鳥取市古海633-7」。本プロジェクトの既定方針(手掛かりが競合する場合は事業者
本人が届け出た特定商取引法上の所在地を優先)に従い、こちらを採用する。

robots.txt確認済み(2026-09時点): 他のBASE系店舗と同一の記述。curl/python-
requests等は個別にDisallow: /指定があるが、User-agent: *ルールでは実質許可。
本スクレイパーは識別可能な独自User-Agentを使用する。

【非コーヒー豆商品の除外について】
実データ確認済み(2026-09時点、全16件): カフェラテベース(リキッド)、
【コーヒー詰め合わせ】150g×4種類(複数銘柄セット)、[お一人様1点限り]200g
送料無料(産地非依存のお試しトライアル、直火焙煎と半熱風焙煎の100gずつを
詰め合わせたもの)、SUZUGAMA陶器ネルドリッパー(器具、雑貨)がNON_BEAN_KEYWORDS
で除外される。残り13件(ストレート12種＋カフェインレスグアテマラ1種、いずれも
150g)を対象とする。

【flavor_notes(2026-09-21追記)】
実データ確認済み: og:descriptionにテイスティング文・産地背景が直接
入っており(対象12件全て確認)、その後に必ず「生産国：」(一部商品は
銘柄名を『』で囲んだ「『銘柄名』生産国：」の形式)で始まるスペック欄
(品種/プロセス/標高/焙煎)、続けて甘味/酸味/苦味/風味の★評価欄が続く。
「生産国：」(銘柄名付きの場合はその手前)までを採用する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "自家焙煎アフェクショネイト珈琲",
    "url": "https://affection.shopselect.net/",
    "platform": "BASE(shopselect.net)",
    "address": "鳥取県鳥取市古海633-7",
    "prefecture": "鳥取県",
    "robots_txt_status": "実質許可(2026-09確認。他のBASE系店舗と同一の記述。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://affection.shopselect.net"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "カフェラテベース", "詰め合わせ", "お一人様", "ネルドリッパー", "ドリッパー",
]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
FIXED_WEIGHT_G = 150
FLAVOR_STOP_PATTERN = re.compile(r"(『[^』]*』)?生産国[：:]")


def extract_flavor_notes(description: str | None) -> str | None:
    """理由はモジュールdocstring参照。"""
    if not description:
        return None
    m = FLAVOR_STOP_PATTERN.search(description)
    text = description[: m.start()] if m else description
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
    title = title_el["content"].split(" | ")[0].strip()
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)

    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None

    desc_el = soup.select_one('meta[property="og:description"]')
    flavor_notes = extract_flavor_notes(desc_el["content"]) if desc_el and desc_el.get("content") else None

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
    weight_g = int(weight_m.group(1)) if weight_m else FIXED_WEIGHT_G

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
    with open("data_affectioncoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_affectioncoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
