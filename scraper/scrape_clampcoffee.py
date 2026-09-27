# -*- coding: utf-8 -*-
"""
scrape_clampcoffee.py

CLAMP COFFEE SARASA(clampcoffee.thebase.in、京都府京都市中京区西ノ京職司町
67-38、自家焙煎豆のオンライン販売)の商品情報を取得する。BASE。

【店舗発見の経緯】
京都エリアの空白地調査(www.kitsune-coffee.com「京都のおすすめコーヒー豆
専門店15選」)で発見。

【対象商品について】
実データ確認済み(sitemap.xml全9件、2026-09時点): コーヒー豆4銘柄
(Mandheling dark・Colombia medium dark・Brazil medium・Ethiopia light)×
100g/300gの2重量展開。Drip Bag(5個入り)はNON_BEAN_KEYWORDSで除外。
100g/300gの重複は最小重量側のみ採用する。

【商品説明の構造について】
実データ確認済み: og:descriptionが「銘柄名 焙煎度 (重量)キャッチコピー
品種 : X精製方法 : Y」という構成。品種・精製方法をラベル値として構造化
フィールドに反映し、キャッチコピー部分をflavor_notesとして採用する。
タイトルが英語表記のため、"Mandheling"はcoffee_parser.pyの国名検出
辞書(日本語「マンデリン」表記のみ)に無く未検出となるため、本スクレイパー
内で個別にインドネシアへマッピングする。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    normalize_processing_method,
    detect_stock_status,
    detect_country_name,
)

SHOP_INFO = {
    "name": "CLAMP COFFEE SARASA",
    "url": "https://www.cafe-sarasa.com/",
    "platform": "BASE",
    "address": "京都府京都市中京区西ノ京職司町67-38",
    "prefecture": "京都府",
    "robots_txt_status": "未確認(他のBASE系店舗と同様の構成を想定)",
}

BASE_URL = "https://clampcoffee.thebase.in"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["Drip Bag"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g", re.IGNORECASE)
STRIP_WEIGHT_PATTERN = re.compile(r"\s*\d+\s*g\s*", re.IGNORECASE)
LABEL_PATTERN = re.compile(r"品種\s*:\s*(.*?)精製方法\s*:\s*(.*)$")


def fetch(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_item_urls() -> list[str]:
    resp = requests.get(f"{BASE_URL}/sitemap.xml", headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "/items/" in loc.get_text()]


def extract_fields(soup: BeautifulSoup, url: str) -> dict | None:
    title_el = soup.select_one('meta[property="og:title"]')
    if not title_el or not title_el.get("content"):
        return None
    title = title_el["content"].split(" | ")[0].strip()
    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None
    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None
    desc_el = soup.select_one('meta[property="og:description"]')
    desc = desc_el["content"] if desc_el and desc_el.get("content") else ""

    m = LABEL_PATTERN.search(desc)
    variety = m.group(1).strip() if m else None
    processing_note = m.group(2).strip() if m else None
    flavor_notes = desc[:m.start()].strip() if m else desc.strip()
    flavor_notes = re.sub(r"^.*?\)", "", flavor_notes, count=1).strip() or None

    return {
        "url": url, "title": title, "price": price,
        "weight_g": int(WEIGHT_PATTERN.search(title).group(1)) if WEIGHT_PATTERN.search(title) else None,
        "variety": variety, "processing_note": processing_note, "flavor_notes": flavor_notes,
    }


def dedupe_by_base_name(items: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for item in items:
        base = STRIP_WEIGHT_PATTERN.sub("", item["title"])
        base = re.sub(r"\s+", "", base).lower()
        # 実データ確認済み: 100g版のみ「Clombia」と綴りが誤っている(300g版は
        # 正しく「Colombia」)。重複除去のため綴りを揃える。
        base = base.replace("clombia", "colombia")
        groups.setdefault(base, []).append(item)

    result = []
    for group in groups.values():
        group.sort(key=lambda x: x["weight_g"] or float("inf"))
        result.append(group[0])
    return result


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

    if "mandheling" in title.lower():
        parsed["origin_country"] = "インドネシア"
        parsed["origin_source"] = "raw_name"
    else:
        detected = detect_country_name(title)
        if detected:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
    parsed = apply_category_hint_fallback(parsed, title)

    if item.get("processing_note"):
        parsed["processing_method"] = normalize_processing_method(item["processing_note"])

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
        "variety": item.get("variety"),
        "flavor_notes": item["flavor_notes"],
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": item["weight_g"],
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    item_urls = fetch_item_urls()

    prelim = []
    for url in item_urls:
        try:
            soup = fetch(url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {url} ({e})")
            continue
        fields = extract_fields(soup, url)
        if fields:
            prelim.append(fields)

    deduped = dedupe_by_base_name(prelim)

    records = []
    flavored_records = []
    for item in deduped:
        detail = build_record(item)
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


def main():
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_clampcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_clampcoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
