# -*- coding: utf-8 -*-
"""
scrape_cafedelambre.py

カフェ・ド・ランブル(CAFÉ DE L'AMBRE、cafedelambre.com、東京都中央区銀座8-10-15、1948年創業・
店舗は銀座の1店舗。夜に焙煎機に火を入れる自家焙煎・手縫いネルドリップの店。運営は株式会社
カフェドランブル)のオンラインショップの商品情報を取得する。Shopify(/products.json)。

【住所】特定商取引法に基づく表記ページの所在地「東京都中央区銀座8丁目10番15号」(2026-10確認)。
【焙煎】商品ページに「ご注文をいただいてから焙煎しております」と明記(受注焙煎)。

【対象商品について】
実データ確認済み(2026-10時点): /products.json の product_type が coffee_beans の商品のみを
収録する(ブレンド・ストレート・「少量限定」シリーズ・オールドコーヒー(2016年収穫の
熟成豆)を含む)。ディップバッグ(drip_bag)・Tシャツ(apparel)・ランブルポット(other)は除外。
商品名の「｜50g」等の末尾の容量表記は除去し、容量はバリエーションから取る。

【重量・価格・在庫】
バリエーション(100g〜500gの5種、希少品は50g〜)のうち最小サイズ(通常100g、一部50g)と
その価格(税込)を採用する。バリエーションが1つのみの「少量限定オールドコーヒー」は
説明文の「内容量：100g」を採用する。在庫はバリエーションの available で判定する。
「ブレンド」はコロンビア・ケニア・ブラジル・タンザニア・エチオピアの5種配合のため
産地None・ブレンド扱い。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method

SHOP_INFO = {
    "name": "カフェ・ド・ランブル",
    "url": "https://cafedelambre.com/",
    "platform": "Shopify",
    "address": "東京都中央区銀座8-10-15",
    "prefecture": "東京都",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://cafedelambre.com"
PRODUCTS_JSON = f"{BASE_URL}/products.json?limit=250"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
ROAST_HINT_PATTERN = re.compile(r"(中深煎り|浅煎り|中煎り|深煎り)")
ORIGIN_OVERRIDES = {"スマトラ": "インドネシア"}


def fetch_products() -> list[dict]:
    products: list[dict] = []
    page = 1
    while True:
        resp = requests.get(f"{PRODUCTS_JSON}&page={page}", headers=REQUEST_HEADERS, timeout=30)
        resp.raise_for_status()
        batch = resp.json().get("products", [])
        if not batch:
            break
        products.extend(batch)
        if len(batch) < 250:
            break
        page += 1
    return products


def html_to_lines(body_html: str) -> list[str]:
    soup = BeautifulSoup(body_html or "", "html.parser")
    text = soup.get_text("\n", strip=True)
    return [ln.strip() for ln in text.split("\n") if ln.strip()]


def build_record(p: dict) -> dict | None:
    if p.get("product_type") != "coffee_beans":
        return None
    title = p["title"].strip()
    name = re.sub(r"\s*[｜|]\s*\d+\s*g\s*$", "", title).strip()
    variants = p.get("variants") or []
    if not variants:
        return None

    def vweight(v: dict) -> int | None:
        m = re.match(r"^\s*(\d+)\s*g", v.get("title") or "")
        return int(m.group(1)) if m else None

    sized = [(vweight(v), v) for v in variants if vweight(v) is not None]
    if sized:
        weight_g, variant = min(sized, key=lambda x: x[0])
    else:
        variant = variants[0]
        weight_g = None
    lines = html_to_lines(p.get("body_html"))
    body = " ".join(lines)
    if weight_g is None:
        wm = re.search(r"内容量[：:]\s*(\d+)\s*g", body)
        weight_g = int(wm.group(1)) if wm else None

    parsed = parse_product(name)
    is_blend = name.endswith("ブレンド") or "ブレンド" in name or parsed["category"] == "ブレンド"
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        parsed = apply_category_hint_fallback(parsed, name)
        if not parsed["origin_country"]:
            for kw, c in ORIGIN_OVERRIDES.items():
                if kw in name:
                    parsed["origin_country"] = c
                    parsed["origin_source"] = "raw_name"
                    break
        if not parsed["origin_country"]:
            c = detect_country_name(" ".join(p.get("tags") or []))
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "tags"
    # 説明文の冒頭(「※」注意書きの手前)をテイスティング・説明文とする
    desc_lines = []
    for ln in lines:
        if ln.startswith("※") or ln.startswith("■"):
            break
        desc_lines.append(ln)
    desc = " ".join(desc_lines)
    rm = ROAST_HINT_PATTERN.search(name) or ROAST_HINT_PATTERN.search(body)
    processing = parsed["processing_method"] or detect_processing_method(name + " " + body[:300])
    available = bool(variant.get("available"))
    price = int(float(variant["price"])) if variant.get("price") else None
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": rm.group(1) if rm else None,
        "flavor_notes": desc[:300] or None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": "販売中" if available else "完売",
        "out_of_stock": not available,
        "product_url": f"{BASE_URL}/products/{p['handle']}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for p in fetch_products():
        rec = build_record(p)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_cafedelambre.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_cafedelambre.json に出力しました")


if __name__ == "__main__":
    main()
