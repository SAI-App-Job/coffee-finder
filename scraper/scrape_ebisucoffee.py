# -*- coding: utf-8 -*-
"""
scrape_ebisucoffee.py

エビスコーヒーロースターズ(ebisucoffeeroasters.com、兵庫県明石市小久保5-8-13、EBISU COFFEE ROASTERS)の
商品情報を取得する。Wix(Wix Stores)。

【ページ構造について】
実データ確認済み(2026-10時点): `/store-products-sitemap.xml`の51件のうち、URLに「drip」を含む
ドリップバッグ(アソートセット含む)24件を除いた27件が焙煎豆(ブレンド5、ストレート・デカフェ22)。
各商品ページのJSON-LD(schema.org Product)から名前・説明・価格・在庫を取得する。
重量は販売単価表示「¥1,200 / 120g(グラム)」(Wixの単位価格=120gごとの価格)から取る。
全商品120g単位で、容量違いのバリエーションは無い(選択肢は焙煎度「おまかせ/中浅煎り/…」と豆の挽目のみ)。
商品名の「【ウォッシュド】」等の角括弧は精製方法、ブレンド名の「[タンザニア・…]」は配合国。
説明文の1行目「｜フルシティ:中深煎り｜」が焙煎度表記(英語ロースト名:日本語)で、1つだけ読み取れる
場合のみroast_levelに入れ、「シティ:中煎りorハイ:中浅煎り」のように複数併記の場合はNoneとして
roast_hintに原文を残す。
"""

import html
import json
import re
import time
from urllib.parse import unquote

import requests

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name,
    normalize_processing_method, ROAST_KEYWORDS,
)

SHOP_INFO = {
    "name": "エビスコーヒーロースターズ",
    "url": "https://www.ebisucoffeeroasters.com/",
    "platform": "Wix(Wix Stores)",
    "address": "兵庫県明石市小久保5-8-13",
    "prefecture": "兵庫県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://www.ebisucoffeeroasters.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
LD_PATTERN = re.compile(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
UNIT_PATTERN = re.compile(r"(\d+)\s*gごとに")
BRACKET_PATTERN = re.compile(r"【([^】]*)】")
BLEND_COMPONENT_PATTERN = re.compile(r"［([^］]*)］")
ROAST_LINE_PATTERN = re.compile(r"｜([^｜\n]+)｜")
ROAST_HINT_PATTERN = re.compile(r"(極深煎り|中深煎り|中浅煎り|浅煎り|中煎り|深煎り)")
EXCLUDE_KEYWORDS = ("DRIP BAG", "ドリップバッグ", "アソート", "セット", "ギフト")


def list_product_urls() -> list[str]:
    resp = requests.get(f"{BASE_URL}/store-products-sitemap.xml", headers=REQUEST_HEADERS, timeout=30)
    urls = re.findall(r"<loc>([^<]+)</loc>", resp.text)
    return [u for u in urls if "drip" not in unquote(u).lower()]


def build_record(url: str) -> dict | None:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    ld_m = LD_PATTERN.search(resp.text)
    if not ld_m:
        return None
    ld = json.loads(ld_m.group(1))
    title = re.sub(r"\s+", " ", html.unescape(ld.get("name", ""))).strip()
    if any(k in title for k in EXCLUDE_KEYWORDS):
        return None
    desc_raw = html.unescape(ld.get("description") or "")
    offer = ld.get("offers") or {}
    if isinstance(offer, list):
        offer = offer[0] if offer else {}
    price = int(float(offer["price"])) if offer.get("price") else None
    in_stock = "InStock" in (offer.get("availability") or "")
    unit_m = UNIT_PATTERN.search(resp.text)
    weight = int(unit_m.group(1)) if unit_m else None

    bracket = BRACKET_PATTERN.search(title)
    processing_raw = bracket.group(1) if bracket else None
    comp_m = BLEND_COMPONENT_PATTERN.search(title)
    name = BRACKET_PATTERN.sub("", title)
    name = re.sub(r"\s+", " ", name).strip()

    parsed = parse_product(name)
    is_blend = parsed["category"] == "ブレンド"
    if is_blend:
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        processing = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"], parsed["origin_source"] = detected, "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        processing = parsed["processing_method"]
        if not processing and processing_raw:
            processing = normalize_processing_method(processing_raw)

    roast_line_m = ROAST_LINE_PATTERN.search(desc_raw)
    roast_line = roast_line_m.group(1).strip() if roast_line_m else None
    roast_level, roast_hint = None, None
    if roast_line:
        matched = []
        for kw, rl in ROAST_KEYWORDS.items():
            if kw in roast_line and rl not in matched:
                matched.append(rl)
        # 「フルシティ」は「シティ」を含むため、より長い表記が成立するときは短い方を落とす
        if "フルシティロースト" in matched and "シティロースト" in matched:
            matched.remove("シティロースト")
        roast_level = matched[0] if len(matched) == 1 else None
        hm = ROAST_HINT_PATTERN.search(roast_line)
        roast_hint = hm.group(1) if hm else None
    # 説明文本文: 焙煎度行より後ろ、「香り ■」評価行より前
    body = desc_raw
    if roast_line_m:
        body = desc_raw[roast_line_m.end():]
    body = re.split(r"\n\s*香り", body)[0]
    flavor_notes = re.sub(r"\s+", " ", body).strip()[:400] or None

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
        "flavor_notes": flavor_notes,
        "farm_note": f"配合: {comp_m.group(1)}" if comp_m else None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "販売中" if in_stock else "完売",
        "out_of_stock": not in_stock,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for url in list_product_urls():
        try:
            record = build_record(url)
        except (requests.RequestException, ValueError) as e:
            print(f"[warn] 商品ページ取得失敗: {unquote(url)} ({e})")
            continue
        if record is not None:
            records.append(record)
        time.sleep(0.5)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_ebisucoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_ebisucoffee.json に出力しました")


if __name__ == "__main__":
    main()
