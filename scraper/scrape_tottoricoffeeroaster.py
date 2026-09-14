# -*- coding: utf-8 -*-
"""
scrape_tottoricoffeeroaster.py

TOTTORI COFFEE ROASTER(shop.tottoricoffeeroaster.com、鳥取県鳥取市商栄町
251番地4、運営：有限会社鳥取珈琲館、自家焙煎豆のオンライン販売)の商品情報を
取得する。BASE。

【住所について】
公式ストアの特定商取引法ページ(https://shop.tottoricoffeeroaster.com/law)で
実データ確認済み(2026-09時点): 「会社名 有限会社鳥取珈琲館 / 事業者の所在地
〒680-0912 鳥取県鳥取市商栄町251番地4」。候補リストの住所と一致。

robots.txt確認済み(2026-09時点): 他のBASE系店舗と同一の記述。curl/python-
requests等は個別にDisallow: /指定があるが、User-agent: *ルールでは実質許可。
本スクレイパーは識別可能な独自User-Agentを使用する。

【非コーヒー豆商品の除外について】
実データ確認済み(2026-09時点、全79件): ドリップバッグ単品・セット(11g規格)、
ギフトセット各種、カフェオレベース(リキッド)、オーツミルク、手提げ袋(雑貨)、
定期便(≪定期便≫表記、産地固定でも複数袋の継続購入契約のため除外)、
お試しセット(複数ブレンドの詰め合わせ)がNON_BEAN_KEYWORDSで除外される。

【生豆(未焙煎)商品について】
実データ確認済み: 商品名が「【生豆】」で始まる3件(マンデリンスマトラ・
グァテマラSHB・コロンビア)は未焙煎の生豆売りのため対象外(本アプリは焙煎豆の
み対象)。他の商品名にも「※生豆300g有」という注記が付くことがあるが、これは
「生豆オプションも選べる」という注記であり商品自体は焙煎豆売りのため、
「【生豆】」で始まる商品のみを除外対象とする(先頭一致、部分一致にしない)。

【重量違いの重複について】
実データ確認済み: 各銘柄が100g/150g/200gの複数サイズでそれぞれ独立した商品
として登録されている(バリアントではない)。商品名の重量表記を除いた基準名で
グルーピングし、最小重量を代表として採用する。

【「※生豆300g有」注記について】
実データ確認済み: 一部の焙煎豆商品(マンデリンスマトラ・ブラウンシュガー・
イルガチェフェ等)の商品名に「※生豆300g有」という、生豆オプションの重量を
示す注記が付いている。これをそのまま重量検出にかけると実際の焙煎豆重量
(100g)ではなく注記側の300gを誤検出してしまうため、RAW_BEAN_NOTE_PATTERNで
この注記部分を重量検出・グルーピングの対象から先に除去する。

【「豆or粉」表記について】
実データ確認済み: 商品名に付く「豆or粉」「豆or粉選択」は挽き方選択のオプション
案内であり産地判定を妨げないため除去しない。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "TOTTORI COFFEE ROASTER",
    "url": "https://shop.tottoricoffeeroaster.com/",
    "platform": "BASE",
    "address": "鳥取県鳥取市商栄町251番地4",
    "prefecture": "鳥取県",
    "robots_txt_status": "実質許可(2026-09確認。他のBASE系店舗と同一の記述。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://shop.tottoricoffeeroaster.com"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

RAW_BEAN_PREFIX_PATTERN = re.compile(r"^【生豆】")
NON_BEAN_KEYWORDS = [
    "ドリップバッグ", "ドリップバック", "ギフト", "カフェオレベース", "オーツミルク",
    "手提げ袋", "定期便", "お試しセット", "セット",
]
RAW_BEAN_NOTE_PATTERN = re.compile(r"[※＊*]\s*生豆\s*\d+\s*[gｇ]\s*有")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def strip_raw_bean_note(title: str) -> str:
    return RAW_BEAN_NOTE_PATTERN.sub("", title)


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def fetch_item_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "/items/" in loc.get_text()]


def is_excluded(title: str) -> bool:
    if RAW_BEAN_PREFIX_PATTERN.match(title):
        return True  # 理由はモジュールdocstring参照(生豆売り)
    return any(kw in title for kw in NON_BEAN_KEYWORDS)


def fetch_item_fields(url: str) -> dict | None:
    soup = fetch_page(url)
    title_el = soup.select_one('meta[property="og:title"]')
    if not title_el or not title_el.get("content"):
        return None
    title = title_el["content"].split(" | ")[0].split(" powered by BASE")[0].strip()
    if not title or is_excluded(title):
        return None
    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None
    return {"title": title, "price": price, "url": url}


def pick_canonical_items(items: list[dict]) -> list[dict]:
    by_base_name: dict[str, tuple[int, dict]] = {}
    for item in items:
        cleaned = strip_raw_bean_note(item["title"])
        weight_m = WEIGHT_PATTERN.findall(cleaned)
        weight_key = int(weight_m[-1]) if weight_m else float("inf")
        base = WEIGHT_PATTERN.sub("", cleaned)
        base = re.sub(r"\s+", " ", base).strip()
        existing = by_base_name.get(base)
        if existing is None or weight_key < existing[0]:
            by_base_name[base] = (weight_key, item)
    return [item for _weight, item in by_base_name.values()]


def build_record(item: dict) -> dict | None:
    title = item["title"]
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

    weight_m = WEIGHT_PATTERN.findall(strip_raw_bean_note(title))
    weight_g = int(weight_m[-1]) if weight_m else None

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

    items = []
    for item_url in item_urls:
        try:
            fields = fetch_item_fields(item_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item_url} ({e})")
            continue
        if fields:
            items.append(fields)

    canonical_items = pick_canonical_items(items)

    records = []
    flavored_records = []
    for item in canonical_items:
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
    with open("data_tottoricoffeeroaster.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_tottoricoffeeroaster.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
