# -*- coding: utf-8 -*-
"""
scrape_goodmanroaster.py

Goodman Roaster Kyoto(goodmanroaster.com、京都府京都市下京区矢田町115-2
ベアフルートイイノ1F、自家焙煎豆のオンライン販売)の商品情報を取得する。
Shopify(/products.json)。

【店舗発見の経緯】
京都エリアの空白地調査(koyo-coffee.com「京都のコーヒー豆専門店おすすめ
50選」)で発見。

【対象カテゴリについて】
実データ確認済み(/products.json全29件、2026-09時点): product_type=
"BEANS"の9件を対象とする。うちDrip Bag/Drip Pack(2件)はコーヒー豆単品と
形態が異なるためNON_BEAN_KEYWORDSで除外。"Seasonal Blend"は1kg/500g/200g
の3商品ページとして重複展開されているため、他店舗と同じ方針で最小重量
(200g)側のみ採用する。

【商品説明の構造について】
実データ確認済み: body_htmlが「Roasting :/Process :/Variety(またはVarieties)
:/Region :/Height(またはAltitude) :」+「[Flavor notes]」または「[Tasting note]」
または「Flavor Note :」に続くテイスティング文、という構成(英語表記、ラベル
表記に若干のゆれあり)。base64画像データが埋め込まれている商品があるため
img要素は除去してテキストのみ取得する。ラベル行より後の自由記述文
(産地紹介等)もflavor_notesに含める。
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
    "name": "Goodman Roaster Kyoto",
    "url": "https://goodmanroaster.com/",
    "platform": "Shopify",
    "address": "京都府京都市下京区矢田町115-2 ベアフルートイイノ1F",
    "prefecture": "京都府",
    "robots_txt_status": "未確認(Shopify標準構成を想定)",
}

BASE_URL = "https://goodmanroaster.com"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["Drip Bag", "Drip Pack"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*kg|(\d+)\s*[gｇ]", re.IGNORECASE)
STRIP_WEIGHT_PATTERN = re.compile(r"[\[<（(]\s*\d+\s*(?:kg|[gｇ])\s*[\]>）)]", re.IGNORECASE)
LABEL_PATTERN = re.compile(
    r"(Roasting|Process|Variety|Varieties|Region|Height|Altitude)\s*:\s*(.*)", re.IGNORECASE)


def fetch_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return [p for p in resp.json().get("products", []) if p.get("product_type") == "BEANS"]


def parse_weight_g(title: str) -> int | None:
    m = re.search(r"(\d+)\s*kg", title, re.IGNORECASE)
    if m:
        return int(m.group(1)) * 1000
    m = re.search(r"(\d+)\s*[gｇ]", title)
    return int(m.group(1)) if m else None


def dedupe_by_base_name(products: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for p in products:
        base = STRIP_WEIGHT_PATTERN.sub("", p["title"])
        base = re.sub(r"\s+", "", base).lower()
        groups.setdefault(base, []).append(p)

    result = []
    for group in groups.values():
        group.sort(key=lambda p: parse_weight_g(p["title"]) or float("inf"))
        result.append(group[0])
    return result


def extract_fields(body_html: str) -> tuple[dict, str | None]:
    soup = BeautifulSoup(body_html or "", "html.parser")
    for img in soup.find_all("img"):
        img.decompose()
    text = soup.get_text("\n", strip=True)

    labels = {}
    flavor_lines = []
    in_notes = False
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        m = LABEL_PATTERN.match(line)
        if m:
            key = m.group(1).lower().rstrip("s")
            labels[key] = m.group(2).strip()
            continue
        if re.match(r"^\[?(Flavor notes?|Tasting note)\]?", line, re.IGNORECASE):
            in_notes = True
            line = re.sub(r"^\[?(Flavor notes?|Tasting note)\]?\s*:?\s*", "", line, flags=re.IGNORECASE)
            if not line:
                continue
        flavor_lines.append(line)

    flavor_notes = "\n".join(flavor_lines) if flavor_lines else None
    return labels, flavor_notes


def build_record(product: dict) -> dict | None:
    title = product["title"].strip()
    variants = product.get("variants") or []
    price = int(float(variants[0]["price"])) if variants else None

    parsed = parse_product(title)
    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": f"{BASE_URL}/products/{product['handle']}",
        }

    labels, flavor_notes = extract_fields(product.get("body_html"))

    origin_note = labels.get("region")
    detected = (
        (origin_note and detect_country_name(origin_note))
        or detect_country_name(title)
        or (flavor_notes and detect_country_name(flavor_notes))
    )
    if detected:
        parsed["origin_country"] = detected
        parsed["origin_source"] = "product_description" if not detect_country_name(title) else "raw_name"
    parsed = apply_category_hint_fallback(parsed, title)

    processing_note = labels.get("process")
    if processing_note:
        parsed["processing_method"] = normalize_processing_method(processing_note)

    variety = labels.get("variety")
    farm_parts = [p for p in [labels.get("region"), labels.get("height"), labels.get("altitude")] if p]
    farm_note = "、".join(farm_parts) if farm_parts else None

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
        "flavor_notes": flavor_notes,
        "farm_note": farm_note,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": parse_weight_g(title),
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": f"{BASE_URL}/products/{product['handle']}",
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    products = fetch_products()
    products = [p for p in products if not any(kw.lower() in p["title"].lower() for kw in NON_BEAN_KEYWORDS)]
    products = dedupe_by_base_name(products)

    records = []
    flavored_records = []
    for product in products:
        detail = build_record(product)
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
    with open("data_goodmanroaster.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_goodmanroaster.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
