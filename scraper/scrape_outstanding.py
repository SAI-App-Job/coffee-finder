# -*- coding: utf-8 -*-
"""
scrape_outstanding.py

OUTSTANDING COFFEE ROASTER(thecoffee.co.jp、京都府宇治市宇治妙楽89-1、
自家焙煎豆のオンライン販売)の商品情報を取得する。Shopify(/products.json)。

【店舗発見の経緯】
京都エリアの空白地調査(koyo-coffee.com「京都のコーヒー豆専門店おすすめ
50選」)で発見。親会社「岡田コーヒー」の50年の焙煎ノウハウを引き継ぐ
2024年開業のロースター。

【対象商品について】
実データ確認済み(/products.json全22件、2026-09時点): Cold Brew "BAG"・
UJI MATCHA(抹茶粉末)・ドリップバッグセット・CAFEC製ペーパーフィルター
(2種)はNON_BEAN_KEYWORDSで除外。残り17件(ストレート15・ブレンド2)を
対象とする。

【商品説明の構造について】
実データ確認済み: body_htmlが2つの異なる構成を取る。(A)「<strong>フレー
バーキーワード</strong>+テイスティング文→ABOUT THIS COFFEE見出し+
農園ストーリー→ROASTING見出し+焙煎方針→DETAILS見出し+ORIGIN/REGION/
FARM/PRODUCER/VARIETY/PROCESS/ALTITUDE/ROAST等のラベル(コロン無し、
全角スペース区切り)」、(B)「フレーバー: X、Y、Z(コロン区切り)→焙煎度:
Z→テイスティング文→農園ストーリー→REGION:/VARIETY:/FARM:/PROCESS:/
ALTITUDE:/ROASTING:/NOTES:のラベル(コロン区切り)」。両形式とも、行単位で
走査し「最初にラベル行が現れるまで」の非見出し行をflavor_notesとして
採用し、それ以降はラベル行のみを構造化フィールドに反映する(ラベル行に
一致しない末尾の保存方法案内等は破棄する)。
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
    "name": "OUTSTANDING COFFEE ROASTER",
    "url": "https://thecoffee.co.jp/",
    "platform": "Shopify",
    "address": "京都府宇治市宇治妙楽89-1",
    "prefecture": "京都府",
    "robots_txt_status": "未確認(Shopify標準構成を想定)",
}

BASE_URL = "https://thecoffee.co.jp"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["Cold Brew", "MATCHA", "ドリップバッグセット", "PAPER FILTER", "ドリップパックセット"]
LABEL_KEYS = [
    "ORIGIN", "REGION", "FARM", "PRODUCER", "VARIETY", "PROCESS", "ALTITUDE",
    "ROASTING", "ROAST", "ROASTER", "VILLAGE", "COLLECTION", "AREA", "NOTES", "フレーバー", "焙煎度",
]
INLINE_LABEL_PATTERN = re.compile(r"^(" + "|".join(LABEL_KEYS) + r")\s*[　:：]\s*(.+)$")
EXACT_LABEL_PATTERN = re.compile(r"^(" + "|".join(LABEL_KEYS) + r")$")


def fetch_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json().get("products", [])


def parse_body(body_html: str) -> tuple[str | None, dict]:
    soup = BeautifulSoup(body_html or "", "html.parser")
    text = soup.get_text("\n", strip=True)
    lines = [l for l in text.split("\n") if l.strip()]

    def is_label_start(i: int) -> bool:
        return bool(INLINE_LABEL_PATTERN.match(lines[i]) or EXACT_LABEL_PATTERN.match(lines[i]))

    first_label_idx = next((i for i in range(len(lines)) if is_label_start(i)), len(lines))

    flavor_lines = []
    for line in lines[:first_label_idx]:
        if line in ("ABOUT THIS COFFEE", "ROASTING", "DETAILS", "BREWING"):
            continue
        flavor_lines.append(line)

    labels: dict[str, str] = {}
    i = first_label_idx
    while i < len(lines):
        line = lines[i]
        m = INLINE_LABEL_PATTERN.match(line)
        if m:
            labels.setdefault(m.group(1), m.group(2).strip())
            i += 1
            continue
        m = EXACT_LABEL_PATTERN.match(line)
        if m and i + 1 < len(lines):
            labels.setdefault(m.group(1), lines[i + 1].strip())
            i += 2
            continue
        i += 1

    flavor_notes = "\n".join(flavor_lines) if flavor_lines else None
    return flavor_notes, labels


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    whole_bean = [v for v in variants if "粉" not in (v.get("title") or "") and "挽" not in (v.get("title") or "")]
    pool = whole_bean or variants
    return pool[0] if pool else None


WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def parse_weight_g(variant_title: str) -> int | None:
    m = WEIGHT_PATTERN.search(variant_title or "")
    return int(m.group(1)) if m else None


def build_record(product: dict) -> dict | None:
    title = product["title"].strip()
    if any(kw.lower() in title.lower() for kw in NON_BEAN_KEYWORDS):
        return None
    variants = product.get("variants") or []
    variant = pick_canonical_variant(variants)
    if not variant:
        return None
    price = int(float(variant["price"]))

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

    flavor_notes, labels = parse_body(product.get("body_html"))

    origin_note = labels.get("ORIGIN") or labels.get("REGION")
    detected = (origin_note and detect_country_name(origin_note)) or detect_country_name(title)
    if detected:
        parsed["origin_country"] = detected
        parsed["origin_source"] = "product_description" if origin_note else "raw_name"
    parsed = apply_category_hint_fallback(parsed, title)

    processing_note = labels.get("PROCESS")
    if processing_note:
        parsed["processing_method"] = normalize_processing_method(processing_note)

    variety = labels.get("VARIETY")
    farm_parts = [labels.get(k) for k in ("FARM", "PRODUCER", "VILLAGE", "AREA", "ALTITUDE") if labels.get(k)]
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
        "weight_g": parse_weight_g(variant.get("title")),
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": f"{BASE_URL}/products/{product['handle']}",
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    products = fetch_products()

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
    with open("data_outstanding.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_outstanding.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
