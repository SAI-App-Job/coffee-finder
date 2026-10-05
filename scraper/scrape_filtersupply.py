# -*- coding: utf-8 -*-
"""
scrape_filtersupply.py

FILTER SUPPLY(https://filter-supply.jp/、福岡県福岡市中央区高砂2-12-33 石井ビル1F)の
商品情報を取得する。Shopify(`/products.json`)。

【対象商品について】
実データ確認済み(2026-10時点): `/products.json`のうちproduct_typeが「Beans」の商品
(自家焙煎の焙煎豆。公式サイトのaboutに「自家焙煎のスペシャルティコーヒー」と記載)を対象とする。
ギフト・飲み比べ・トライアルセット・限定セット・定期便は除外。
同一銘柄が「瓶(100g)」と「リフィルパック(100/200/400g)」の別商品で並ぶため、
銘柄(商品名から「瓶」「リフィルパック」を除いたもの)ごとに最小重量の商品を代表とし、
重量が同じ場合は価格の安いリフィルパックを代表とする。
(ジャンソン・ゲイシャ等の希少ロットはリフィルパックが50gのため、50gが代表になる。)
バリエーションは重量(g)を含むものを対象とし、最小重量のバリエーションの価格を採用する
(いずれかの挽き方で在庫があれば販売中)。
産地・精製方法・焙煎度は商品説明の「生産国 - 」「精製方法 - 」「焙煎度 - 」欄から取得する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method,
)

SHOP_INFO = {
    "name": "FILTER SUPPLY",
    "url": "https://filter-supply.jp/",
    "platform": "Shopify",
    "address": "福岡県福岡市中央区高砂2-12-33 石井ビル1F",
    "prefecture": "福岡県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://filter-supply.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BEAN_TYPE = "Beans"
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g", re.I)
EXCLUDE_TITLE_KEYWORDS = (
    "set", "セット", "trial", "ギフト", "gift", "定期便", "subscription", "飲み比べ", "予約販売",
    "キャンドル", "bag",
)

COARSE_ROASTS = (
    ("中浅煎り", re.compile(r"中浅煎り|ミディアムライト|medium\s*light", re.I)),
    ("中深煎り", re.compile(r"中深煎り|ミディアムダーク|medium\s*dark", re.I)),
    ("浅煎り", re.compile(r"浅煎り|ライト\s*ロースト|light\s*roast|\blight\b", re.I)),
    ("中煎り", re.compile(r"中煎り|ミディアム\s*ロースト|medium\s*roast|\bmedium\b", re.I)),
    ("深煎り", re.compile(r"深煎り|ダーク\s*ロースト|dark\s*roast|\bdark\b|フレンチ|イタリアン|french\s*roast", re.I)),
)
ROAST_LABEL_PATTERN = re.compile(r"(?:焙煎度|roast\s*level)[\s\-:：]*([^\n]{0,40})", re.I)
PACK_SUFFIX_PATTERN = re.compile(r"\s*(リフィルパック|瓶)\s*(\d+\s*g)?\s*$")


def coarse_roast(text: str) -> tuple[str | None, str | None]:
    for label, pat in COARSE_ROASTS:
        m = pat.search(text or "")
        if m:
            return label, m.group(0)
    return None, None


def variant_weight(title: str) -> int | None:
    m = WEIGHT_PATTERN.search(title or "")
    return int(m.group(1)) if m else None


def brand_key(title: str) -> str:
    return PACK_SUFFIX_PATTERN.sub("", title).strip()


def fetch_products() -> list[dict]:
    products = []
    page = 1
    while True:
        resp = requests.get(f"{BASE_URL}/products.json?limit=250&page={page}", headers=REQUEST_HEADERS, timeout=30)
        resp.raise_for_status()
        batch = resp.json().get("products", [])
        products.extend(batch)
        if len(batch) < 250:
            break
        page += 1
    return products


def build_flavor_notes(body_text: str) -> str | None:
    m = re.search(r"フレーバー\s*-\s*\n(.+)", body_text)
    notes = m.group(1).strip() if m else ""
    c = re.search(r"(?:フレーバーコメント|カップコメント)\s*\n(.+)", body_text)
    if c:
        notes = (notes + " / " if notes else "") + c.group(1).strip()
    return re.sub(r"\s+", " ", notes)[:400] or None


def build_record(p: dict) -> dict | None:
    title = re.sub(r"\s+", " ", p["title"]).strip()
    lowered = title.lower()
    if any(k.lower() in lowered for k in EXCLUDE_TITLE_KEYWORDS):
        return None
    if p.get("product_type") != BEAN_TYPE:
        return None

    weighted = []
    for v in p["variants"]:
        w = variant_weight(v.get("title"))
        if w:
            weighted.append((w, v))
    if not weighted:
        return None
    weight, variant = min(weighted, key=lambda x: x[0])
    price = int(float(variant["price"]))
    if price <= 0:
        return None
    available = any(v.get("available") for w, v in weighted if w == weight)

    body_text = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text("\n", strip=True)
    tags = p.get("tags") or []
    tag_text = " ".join(tags)
    name = brand_key(title)

    is_blend = "ブレンド" in tags or "blend" in lowered
    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
        parsed["grade"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"]:
            m = re.search(r"生産国\s*-\s*([^\n]+)", body_text)
            c = detect_country_name(m.group(1)) if m else None
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "description"
        parsed = apply_category_hint_fallback(parsed, tag_text)
    processing = parsed["processing_method"]
    if not processing and not is_blend:
        m = re.search(r"精製方法\s*-\s*(.*?)\s*標高", body_text, re.S)
        if m:
            processing = detect_processing_method(m.group(1))
    if is_blend:
        processing = None

    roast_level, roast_hint = coarse_roast(name)
    if not roast_level:
        m = ROAST_LABEL_PATTERN.search(body_text)
        if m:
            roast_level, roast_hint = coarse_roast(m.group(1))
    if not roast_level:
        roast_level, roast_hint = coarse_roast(tag_text)

    status = "販売中" if available else "完売"
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_hint": roast_hint,
        "flavor_notes": build_flavor_notes(body_text),
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": status,
        "out_of_stock": status != "販売中",
        "product_url": f"{BASE_URL}/products/{p['handle']}",
    }


def scrape_all_products() -> list[dict]:
    # 銘柄ごとに最小重量(同重量なら安い方=リフィルパック)の商品を代表にする
    best: dict[str, dict] = {}
    order: list[str] = []
    for p in fetch_products():
        record = build_record(p)
        if record is None:
            continue
        key = record["raw_name"]
        if key not in best:
            best[key] = record
            order.append(key)
        else:
            cur = best[key]
            if (record["weight_g"], record["price"]) < (cur["weight_g"], cur["price"]):
                best[key] = record
    return [best[k] for k in order]


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_filtersupply.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_filtersupply.json に出力しました")


if __name__ == "__main__":
    main()
