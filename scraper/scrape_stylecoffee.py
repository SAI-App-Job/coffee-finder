# -*- coding: utf-8 -*-
"""
scrape_stylecoffee.py

STYLE COFFEE(stylecoffee.jp、京都府京都市上京区桝屋町360-1 ペアリーフ御所東
1階、自家焙煎豆のオンライン販売)の商品情報を取得する。BASE(独自ドメイン運用)。

【店舗発見の経緯】
京都エリアの空白地調査(coffee-labo.co.jp等)で発見。

【対象商品について】
実データ確認済み(sitemap.xml全23件、2026-09時点): コーヒー豆8銘柄
(Ethiopia Bona Sedeka・Honduras Denilson Madrid Catuai・Ethiopia
Anasora Natural・Kenya Gititu・Honduras Marysabel&Moises・Honduras
Juan Carlos Geisha・[Espresso Roast]Brazil Monte Alegre・[Decaf]
Ethiopia Sidamo G2)×200g/500gの重複(Juan Carlos Geishaのみ100g単一)。
Drip Bag各種・コーヒー豆袋(空袋)・水出しコーヒー・ギフトボックス・
定期便はNON_BEAN_KEYWORDSで除外。200g/500gの重複は最小重量側のみ採用。

【商品説明の構造について】
実データ確認済み: og:descriptionが「テイスティング文+Location:/Variety:/
Process:/Altitude:のラベル(コロン区切り)+使用記録という日常での飲用
シチュエーションを綴った長文の日記+挽き方に関する注文時の注意書き」という
構成。「使用記録」以降の日記部分と末尾の注文注意書きは除去し、ラベルより
前のテイスティング文をflavor_notesとして採用、ラベル値を構造化フィールドに
反映する。
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
    "name": "STYLE COFFEE",
    "url": "https://www.stylecoffee.jp/",
    "platform": "BASE",
    "address": "京都府京都市上京区桝屋町360-1 ペアリーフ御所東1階",
    "prefecture": "京都府",
    "robots_txt_status": "未確認(他のBASE系店舗と同様の構成を想定)",
}

BASE_URL = "https://www.stylecoffee.jp"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "Drip Bag", "Drip bag", "コーヒー豆袋", "水出しコーヒー", "ギフトボックス", "定期便",
]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]", re.IGNORECASE)
STRIP_WEIGHT_PATTERN = re.compile(r"[／/]\s*(?:おすすめ|ちょっとお得な)?\s*\d+\s*[gｇG]\s*$", re.IGNORECASE)
STRIP_BRACKET_PATTERN = re.compile(r"^[【\[][^】\]]*[】\]]")
LABEL_PATTERN = re.compile(r"(Location|Variety|Process|Altitude)\s*[:：]\s*([^\n]*?)(?=Location:|Variety:|Process:|Altitude:|使用記録|$)")


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def fetch_item_urls() -> list[str]:
    text = fetch(f"{BASE_URL}/sitemap.xml")
    soup = BeautifulSoup(text, "html.parser")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "/items/" in loc.get_text()]


def parse_weight_g(title: str) -> int | None:
    m = WEIGHT_PATTERN.search(title)
    return int(m.group(1)) if m else None


def dedupe_by_base_name(items: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for item in items:
        base = STRIP_BRACKET_PATTERN.sub("", item["title"])
        base = STRIP_WEIGHT_PATTERN.sub("", base)
        base = re.sub(r"[\s　]+", "", base).lower()
        groups.setdefault(base, []).append(item)

    result = []
    for group in groups.values():
        group.sort(key=lambda x: x["weight_g"] or float("inf"))
        result.append(group[0])
    return result


def extract_fields(text: str, url: str) -> dict | None:
    title_m = re.search(r'<meta property="og:title" content="([^"]*)"', text)
    if not title_m:
        return None
    title = title_m.group(1).split(" | ")[0].strip()
    if any(kw.lower() in title.lower() for kw in NON_BEAN_KEYWORDS):
        return None
    price_m = re.search(r'<meta property="product:price:amount" content="([^"]*)"', text)
    price = int(float(price_m.group(1))) if price_m else None
    desc_m = re.search(r'<meta property="og:description" content="([^"]*)"', text)
    desc = desc_m.group(1) if desc_m else ""

    label_positions = list(LABEL_PATTERN.finditer(desc))
    labels = {m.group(1): m.group(2).strip() for m in label_positions}
    flavor_text = desc[:label_positions[0].start()] if label_positions else re.split(r"使用記録", desc)[0]

    return {
        "url": url, "title": title, "price": price,
        "weight_g": parse_weight_g(title), "labels": labels,
        "flavor_notes": flavor_text.strip() or None,
    }


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

    labels = item["labels"]
    origin_note = labels.get("Location")
    detected = (origin_note and detect_country_name(origin_note)) or detect_country_name(title)
    if detected:
        parsed["origin_country"] = detected
        parsed["origin_source"] = "product_description" if origin_note else "raw_name"
    parsed = apply_category_hint_fallback(parsed, title)

    if labels.get("Process"):
        parsed["processing_method"] = normalize_processing_method(labels["Process"])

    variety = labels.get("Variety")
    farm_note = f"標高：{labels['Altitude']}" if labels.get("Altitude") else None
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
        "variety": variety,
        "flavor_notes": item["flavor_notes"],
        "farm_note": farm_note,
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
            text = fetch(url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {url} ({e})")
            continue
        fields = extract_fields(text, url)
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
    with open("data_stylecoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_stylecoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
