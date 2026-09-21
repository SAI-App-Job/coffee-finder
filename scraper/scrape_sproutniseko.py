# -*- coding: utf-8 -*-
"""
scrape_sproutniseko.py

SPROUT NISEKO(sproutstore.thebase.in、北海道虻田郡倶知安町北一条西3-10、
BASE)の商品情報を取得する。

住所はBASEの特定商取引法ページ(https://sproutstore.thebase.in/law)で
実データ確認済み(2026-09時点、〒044-0051 北海道虻田郡倶知安町北一条西
3-10)。BASE株式会社自体の東京都港区六本木の代理住所ではなく、事業者本人の
住所が明記されている点を確認済み。

【商品構成について】
実データ確認済み(sitemap.xml全41件): コーヒー豆単品9件(メキシコ・
グアテマラ(2種)・コスタリカ・ケニア・ニセコオートルート・ヨウテイ
ブレンド・エチオピア・デカフェメキシコ、50g/100g)と「Coffee Aid 200g
Niseko Houte Route Blend」(チャリティー企画のブレンド、単一銘柄として
特定できるため対象)の計10件を対象とする。他31件は非対象: 「COFFEE BAG」
各種(ドリップバッグ)、「CAFÉ AU LAIT BASE」「LIQUID ICED COFFEE」
(リキッド)、「COFFEE YO-KAN」(コーヒー羊羹)、「Coffee jerry」
(コーヒーゼリー)、「LOG BOOK/LOGBOOK」「LIKE THE WIND」(雑誌・冊子)、
「Tetra DRIP ORIGINAL」(ドリッパー)、「Coffee AID 200g Single Origin &
Blend Set」(複数銘柄セット)、「POCKET羊蹄山」「Original sticker」
「Original CHICO BAG」(グッズ)。NON_BEAN_KEYWORDSで除外する。

robots.txt確認済み(2026-09時点): 他のBASE系店舗と同一の記述(curl/python-
requests等は個別にDisallow: /指定があるが、User-agent: *ルールでは実質
許可)。本スクレイパーは識別可能な独自User-Agentを使用する。

【flavor_notes(2026-09-21追記)】
実データ確認済み: 対象全11件のog:descriptionはテイスティング文(または
ブレンドの背景ストーリー)で始まり、【産地】等の構造化ラベルなしで
生産国：等のスペック行が地続きで続く場合がある(full-text-tolerance方針
により許容)。末尾は「100g以上のお買い上げで」「こちらの商品は」「オーナー
が視察・仕入れに行き」のいずれかのパッケージ/配送/ブログ案内の定型文で
始まり、共通して「配送について」という文言を含むため、これらのいずれか
最初に出現した時点で打ち切る。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "SPROUT NISEKO",
    "url": "https://sproutstore.thebase.in/",
    "platform": "BASE",
    "address": "北海道虻田郡倶知安町北一条西3-10",
    "prefecture": "北海道",
    "robots_txt_status": "実質許可(2026-09確認。他のBASE系店舗と同一の記述。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://sproutstore.thebase.in"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "COFFEE BAG", "CAFÉ AU LAIT", "LIQUID", "YO-KAN", "jerry",
    "LOG BOOK", "LOGBOOK", "LIKE THE WIND", "Tetra DRIP",
    "Single Origin & Blend Set", "POCKET", "sticker", "CHICO BAG",
]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
FLAVOR_STOP_PATTERN = re.compile(r"こちらの商品は|オーナーが視察・仕入れに行き|100[gｇ]以上のお買い上げで|配送について")


def extract_flavor_notes(description: str | None) -> str | None:
    """理由はモジュールdocstring参照。"""
    if not description:
        return None
    m = FLAVOR_STOP_PATTERN.search(description)
    text = description[:m.start()] if m else description
    return text.strip() or None


def fetch_item_urls() -> list[str]:
    resp = requests.get(f"{BASE_URL}/sitemap.xml", headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "/items/" in loc.get_text()]


def extract_fields(soup: BeautifulSoup) -> dict | None:
    title_el = soup.select_one('meta[property="og:title"]')
    if not title_el or not title_el.get("content"):
        return None
    title = title_el["content"].split(" | ")[0].strip()
    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None
    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None
    desc_el = soup.select_one('meta[property="og:description"]')
    flavor_notes = extract_flavor_notes(desc_el["content"]) if desc_el and desc_el.get("content") else None
    return {"title": title, "price": price, "flavor_notes": flavor_notes}


def build_record(item: dict) -> dict | None:
    title = item["title"].strip()
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": item["price"],
            "product_url": item["url"],
        }

    stock_status = detect_stock_status(title)
    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None

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
        "flavor_notes": item.get("flavor_notes"),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    item_urls = fetch_item_urls()

    all_items = []
    for product_url in item_urls:
        try:
            resp = requests.get(product_url, headers=REQUEST_HEADERS, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        soup = BeautifulSoup(resp.text, "html.parser")
        fields = extract_fields(soup)
        if not fields:
            continue
        all_items.append({**fields, "url": product_url})

    records = []
    flavored_records = []
    for item in all_items:
        detail = build_record(item)
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
    with open("data_sproutniseko.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_sproutniseko.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
