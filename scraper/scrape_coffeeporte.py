# -*- coding: utf-8 -*-
"""
scrape_coffeeporte.py

ポルトコーヒー(coffeeporte.theshop.jp、岡山県岡山市中区浜3丁目11-7
カルチェWe105、自家焙煎豆のオンライン販売)の商品情報を取得する。
THE SHOP(BASE系)。

【住所について】
特定商取引法ページ(https://coffeeporte.theshop.jp/law)を実データ確認し、
候補リストの住所と一致することを確認した(2026-09時点)。

robots.txt確認済み(2026-09時点): 他のTHE SHOP店舗と同一の記述。
curl/python-requests等は個別にDisallow: /指定があるが、User-agent: *
ルールでは実質許可。本スクレイパーは識別可能な独自User-Agentを使用する。

【対象カテゴリについて】
実データ確認済み: 「産地で選ぶ」配下のアフリカ(690760)・アジア・
オセアニア(690767)・中央アメリカ(690775)・南アメリカ(690776)・
ブレンド(692343)と、ノンカフェイン(デカフェ、1660002)の計6カテゴリの
みを対象とする。「セット＆定期便」「ギフト」「コーヒー用品」
「お手軽コーヒー」(ドリップパック/コーヒーバッグ/水だしコーヒーパック、
実データ確認済みで全件コーヒー豆単品ではない)は非対象。

【商品情報の取得方法について】
実データ確認済み: 各カテゴリページのa.c-item内、div.c-item__title
nowrapに商品名(末尾に重量表記)、div.c-item__price > pに価格(税込)が
静的HTMLで直接出力されている。

【非コーヒー豆商品の除外について】
実データ確認済み: 対象6カテゴリ内にも「家庭用お買い得1kg（500g×2袋）」
(産地非依存の汎用まとめ売り、カテゴリ横断で重複出現)・「コーヒーバッグ
≪COFFEE BAG≫」各種・「【ギフト】COFFEE BAG（28パック）」が混在して
いるためNON_BEAN_KEYWORDSで除外する。

【重量違いの重複について】
実データ確認済み: 各銘柄は100g/200g/500g(250g×2袋)の3種類の重量で別々の
商品ページとして登録されている(一部銘柄は100g/200gのみ)。商品名末尾の
重量表記を除いた基準名でグルーピングし、最小重量を代表として採用する。
デカフェのメキシコ銘柄は「中央アメリカ」「ノンカフェイン」の2カテゴリに
重複掲載されているため、商品URLで重複排除してから集計する。

【flavor_notes(2026-09-21追記)】
実データ確認済み: 商品詳細ページのdiv.p-item__bodyに「フレーバー：」
という短い記述語ラベル、またはラベル無しでテイスティング文が直接
入っている(対象13件全てで確認)。「【珈琲豆のこと】」(焙煎度/生産地/
農園/生産者/品種/グレード/精製方法/標高の構造化スペック欄の見出し)・
「【メール便での発送について】」以降を除いた残りを採用する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "ポルトコーヒー",
    "url": "https://coffeeporte.theshop.jp/",
    "platform": "THE SHOP(BASE系)",
    "address": "岡山県岡山市中区浜3丁目11-7 カルチェWe105",
    "prefecture": "岡山県",
    "robots_txt_status": "実質許可(2026-09確認。他のTHE SHOP店舗と同一の記述。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://coffeeporte.theshop.jp"
CATEGORY_IDS = [690760, 690767, 690775, 690776, 692343, 1660002]
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["家庭用お買い得", "COFFEE BAG", "ドリップパック", "水だしコーヒーパック", "ギフト】"]
TRAILING_WEIGHT_PATTERN = re.compile(r"\s*\d+\s*[gｇ](?:（[^）]*）)?\s*$")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
PRICE_PATTERN = re.compile(r"([\d,]+)")
FLAVOR_STOP_PATTERN = re.compile(r"【珈琲豆のこと】|【メール便")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def extract_flavor_notes(product_url: str) -> str | None:
    """理由はモジュールdocstring参照。"""
    try:
        soup = fetch_page(product_url)
    except requests.RequestException as e:
        print(f"[warn] 詳細ページ取得失敗(flavor_notes): {product_url} ({e})")
        return None
    for br in soup.find_all("br"):
        br.replace_with("\n")
    container = soup.select_one("div.p-item__body")
    if not container:
        return None
    lines = [l.strip() for l in container.get_text("\n", strip=True).split("\n") if l.strip()]
    stop_idx = next((i for i, l in enumerate(lines) if FLAVOR_STOP_PATTERN.search(l)), len(lines))
    text = "\n".join(lines[:stop_idx]).strip()
    return text or None


def scrape_category(category_id: int) -> list[dict]:
    soup = fetch_page(f"{BASE_URL}/categories/{category_id}")
    items = []
    for a in soup.select("a.c-item"):
        title_el = a.select_one("div.c-item__title")
        price_el = a.select_one("div.c-item__price p")
        href = a.get("href", "")
        if not title_el or not href:
            continue
        title = title_el.get_text(strip=True)
        if any(kw in title for kw in NON_BEAN_KEYWORDS):
            continue
        price = None
        if price_el:
            m = PRICE_PATTERN.search(price_el.get_text().replace(",", ""))
            if m:
                price = int(m.group(0))
        items.append({"title": title, "price": price, "url": href})
    return items


def base_name_and_weight(title: str) -> tuple[str, int | None]:
    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None
    base = TRAILING_WEIGHT_PATTERN.sub("", title).strip()
    return base, weight_g


def pick_canonical_items(items: list[dict]) -> list[dict]:
    by_base_name: dict[str, dict] = {}
    for item in items:
        base, weight_g = base_name_and_weight(item["title"])
        item["base_name"] = base
        item["weight_g"] = weight_g
        weight_key = weight_g if weight_g is not None else float("inf")
        existing = by_base_name.get(base)
        if existing is None:
            by_base_name[base] = item
            continue
        existing_weight = existing["weight_g"] if existing["weight_g"] is not None else float("inf")
        if weight_key < existing_weight:
            by_base_name[base] = item
    return list(by_base_name.values())


def build_record(item: dict) -> dict | None:
    title = item["base_name"]
    if not title:
        return None
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
        "flavor_notes": extract_flavor_notes(item["url"]),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": item["weight_g"],
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    all_items: dict[str, dict] = {}
    for category_id in CATEGORY_IDS:
        try:
            items = scrape_category(category_id)
        except requests.RequestException as e:
            print(f"[warn] カテゴリ取得失敗: {category_id} ({e})")
            continue
        for item in items:
            all_items[item["url"]] = item

    canonical_items = pick_canonical_items(list(all_items.values()))

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
    with open("data_coffeeporte.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeeporte.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
