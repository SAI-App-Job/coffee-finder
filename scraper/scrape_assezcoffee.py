# -*- coding: utf-8 -*-
"""
scrape_assezcoffee.py

assez COFFEE(assez-coffee.com、宮城県仙台市青葉区中山6-5-21、自家焙煎豆の通販)の商品情報を
取得する。Wix。

【取得方法】
実データ確認済み(2026-10): store-products-sitemap.xml に商品ページ(/product-page/<slug>)が8件
(全てコーヒー豆)。各ページのJSON-LD(Product)から name / offers.price / availability を取得する。
description は農園名・産地・品種・標高・精製等の産地情報(風味文ではない)のため farm_note に入れる。

【重量について】
グラム選択式ではなく、価格は1商品1価格。8件中3件(ケニア・グアテマラ・エチオピア)は
ページ上に「100gごとに¥xxx」と明示されている。残り5件は単位の表示が無いが、店側情報
(100g 730〜1,200円)と店のメニュー構成から100g価格と判断して100gとして扱う
(ページ上に明示が無いため、店舗確認が望ましい)。

【焙煎度について】
「ロースト」オプションでHigh/City/FullCity/Frenchと挽き方(豆/粗挽き/中挽き/極細挽き)の組を選ぶ
方式。選択肢が複数ある商品は焙煎度選択式(roast_selectable=True)とし、焙煎度は未確定(None)。
City単一の商品は「シティロースト」とする。
"""

import json
import re
import time
from urllib.parse import quote

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "assez COFFEE",
    "url": "https://www.assez-coffee.com/",
    "platform": "Wix",
    "address": "宮城県仙台市青葉区中山6-5-21",
    "prefecture": "宮城県",
    "robots_txt_status": "未確認(Wix標準構成)",
}

SITEMAP_URL = "https://www.assez-coffee.com/store-products-sitemap.xml"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 1
DEFAULT_WEIGHT_G = 100

ROAST_MAP = {"High": "ハイロースト", "City": "シティロースト", "FullCity": "フルシティロースト", "French": "フレンチロースト"}


def fetch(url: str) -> str:
    resp = requests.get(quote(url, safe=":/?=&#%"), headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def extract_product_ld(html: str) -> dict | None:
    for m in re.finditer(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == "Product":
            return data
    return None


def extract_json_array(html: str, key: str) -> list | None:
    i = html.find(f'"{key}":[')
    if i < 0:
        return None
    start = html.find("[", i)
    try:
        arr, _ = json.JSONDecoder().raw_decode(html[start:])
    except json.JSONDecodeError:
        return None
    return arr


def roast_info(html: str):
    """(roast_level, roast_selectable) をロースト選択肢から決める"""
    options = extract_json_array(html, "options") or []
    for opt in options:
        if opt.get("title") == "ロースト":
            kinds = []
            for sel in opt.get("selections") or []:
                k = (sel.get("value") or "").split("/")[0]
                if k and k not in kinds:
                    kinds.append(k)
            if len(kinds) == 1:
                return ROAST_MAP.get(kinds[0]), False
            if kinds:
                return None, True
    return None, False


def scrape_all_products() -> list[dict]:
    sitemap = fetch(SITEMAP_URL)
    urls = re.findall(r"<loc>([^<]+/product-page/[^<]+)</loc>", sitemap)

    records = []
    for url in urls:
        time.sleep(CRAWL_DELAY_SECONDS)
        html = fetch(url)
        ld = extract_product_ld(html)
        if not ld:
            continue
        title = re.sub(r"\s+", " ", ld.get("name") or "").strip()
        offer = ld.get("offers") or {}
        if isinstance(offer, list):
            offer = offer[0] if offer else {}
        price = int(float(offer["price"])) if offer.get("price") not in (None, "") else None
        available = "OutOfStock" not in (offer.get("availability") or "")

        m = re.search(r'"pricePerUnitData":\{"baseQuantity":(\d+),"baseMeasurementUnit":"g"\}', html)
        weight = int(m.group(1)) if m else DEFAULT_WEIGHT_G

        farm = re.sub(r"\s+", " ", ld.get("description") or "").strip()[:400] or None
        roast_level, roast_selectable = roast_info(html)

        parsed = parse_product(title)
        detected = detect_country_name(title)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, title)

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": roast_level or parsed["roast_level"],
            "roast_selectable": roast_selectable,
            "roast_hint": None,
            "flavor_notes": None,
            "farm_note": farm,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": price,
            "weight_g": weight,
            "stock_status": "販売中" if available else "完売",
            "out_of_stock": not available,
            "product_url": offer.get("url") or url,
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_assezcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_assezcoffee.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], r["category"], r["origin_country"], r["processing_method"], r["roast_level"], r["roast_selectable"], r["price"], r["weight_g"], r["stock_status"])


if __name__ == "__main__":
    main()
