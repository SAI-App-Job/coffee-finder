# -*- coding: utf-8 -*-
"""
scrape_kurumicoffee.py

焙煎珈琲 胡桃(くるみ。coffee-kurumi.com、香川県高松市鶴市町1034-1、胡桃珈琲 合同会社)の
オンラインショップの商品情報を取得する。Wix(Wix Stores)。

【ページ構造について】
実データ確認済み(2026-11-02時点): `/store-products-sitemap.xml`から全商品ページURL(16件)を列挙し、
各商品ページのJSON-LD(schema.org Product)から名前・説明・価格・在庫を取得する。
商品ページの「●内容量:100g〜」と「¥価格 / 100g(グラム)」の表記のとおり、価格は100gあたり
(数量オプションで100g単位に購入)。重量はすべて100gとして記録する。挽き方は豆/粉のオプション。
原産国は商品ページ本文の「●原材料名:コーヒー豆(原産国:○○)」から取る。
除外: オリーブ珈琲(3パック入り。小豆島産オリーブポマースを加えたインフューズド)。
商品名はJSON-LDのname(URL「スペシャルブレンド」のページ名は「プレミアムブレンド」)。
フレンチローストは原材料名が「ブラジル他」でブラジル・サントス主体の複数豆のため、ブレンドとして扱う。
"""

import html
import json
import re
import time
from urllib.parse import unquote

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "焙煎珈琲 胡桃",
    "url": "https://www.coffee-kurumi.com/",
    "platform": "Wix(Wix Stores)",
    "address": "香川県高松市鶴市町1034-1",
    "prefecture": "香川県",
    "robots_txt_status": "許可(User-agent: * は Allow: /。識別可能なUser-Agentを使用)",
    "source_note": "商品サイトマップ(lastmod 2026-10-09)・各商品ページのJSON-LD・公式ページ(トップ/お店/特商法 lastmod 2026-10-13)を2026-11-02に確認。住所はサイトフッタと特商法(https://www.coffee-kurumi.com/scta)。実店舗(喫茶、8:30〜16:00 月曜定休)は2024年12月の取材記事(https://kagawa-life.website/coffee-kurumi/ ほか)で確認。トップに焙煎機LUCKY TRL-1での自家焙煎の記述あり。",
    "last_verified_at": "2026-11-02",
}

BASE_URL = "https://www.coffee-kurumi.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL = 1.6
LD_PATTERN = re.compile(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
ORIGIN_PATTERN = re.compile(r'"text":"●原材料名：コーヒー豆（(?:原産国|生豆生産国名)：([^"）]*)）')
ROAST_PATTERN = re.compile(r"(中浅煎り|中深煎り|浅煎り|中煎り|深煎り)")
EXCLUDE_KEYWORDS = ("オリーブ", "セット", "ドリップバッグ")
EXTRA_BLENDS = ("フレンチロースト",)  # 名前に「ブレンド」を含まないが複数豆のもの
WEIGHT_G = 100


def list_product_urls() -> list[str]:
    resp = requests.get(f"{BASE_URL}/store-products-sitemap.xml", headers=REQUEST_HEADERS, timeout=30)
    return re.findall(r"<loc>([^<]+/product-page/[^<]+)</loc>", resp.text)


def build_record(url: str) -> dict | None:
    time.sleep(REQUEST_INTERVAL)
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    m = LD_PATTERN.search(resp.text)
    if not m:
        return None
    ld = json.loads(m.group(1))
    name = re.sub(r"\s+", " ", html.unescape(ld.get("name", "")).replace("　", " ")).strip()
    if not name or any(kw in name for kw in EXCLUDE_KEYWORDS):
        return None
    desc = re.sub(r"\s+", " ", html.unescape(ld.get("description") or "")).strip()[:400] or None
    offer = ld.get("offers") or {}
    if isinstance(offer, list):
        offer = offer[0] if offer else {}
    price = int(float(offer["price"])) if offer.get("price") else None
    in_stock = "InStock" in (offer.get("availability") or "")

    origin_m = ORIGIN_PATTERN.search(resp.text)
    origin_text = (origin_m.group(1) if origin_m else "").replace("　", "").strip()

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    is_blend = "ブレンド" in name or name in EXTRA_BLENDS
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        detected = detect_country_name(origin_text) or detect_country_name(name)
        if detected:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "description" if detect_country_name(origin_text) else "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)

    if name == "フレンチロースト":
        roast = "フレンチロースト"
    else:
        roast_m = ROAST_PATTERN.search(desc or "")
        roast = roast_m.group(1) if roast_m else None

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": None if is_blend else parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast,
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": WEIGHT_G,
        "stock_status": "販売中" if in_stock else "完売",
        "out_of_stock": not in_stock,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for url in list_product_urls():
        try:
            rec = build_record(url)
        except (requests.RequestException, ValueError) as e:
            print(f"[warn] 商品ページ取得失敗: {unquote(url)} ({e})")
            continue
        if rec is not None and rec["price"] is not None:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_kurumicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kurumicoffee.json に出力しました")


if __name__ == "__main__":
    main()
