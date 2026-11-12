# -*- coding: utf-8 -*-
"""
scrape_kamoecoffee.py

鴨江珈琲(kamoe-coffee.com、静岡県浜松市中央区三組町139-8、自家焙煎コーヒー専門店)の
オンラインショップ(Buy Beans)の商品情報を取得する。Wix(Wix Stores)。

【ページ構造について】
実データ確認済み(2026-10時点): `/store-products-sitemap.xml`から全商品ページURLを列挙し、
各商品ページのJSON-LD(schema.org Product)から名前・説明・価格・在庫を取得する(全17ページ)。
商品名の末尾「(100 g)」「(50 g)」が販売重量。同一銘柄が50g版と100g版で別ページの場合は
最小重量(50g)を代表とする。ケニア スングリ AAのように焙煎度違いで別ページの商品は
別商品として扱う。「おすすめセット」と「ドリップバッグ」は除外。
メキシコ カフェインレス(デカフェ)は商品ページに重量の記載がないため weight_g は null。
挽き方は「豆 / 粉」のオプションで、豆のままを選べる。
"""

import html
import json
import re
import time
from urllib.parse import unquote

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method

SHOP_INFO = {
    "name": "鴨江珈琲",
    "url": "https://www.kamoe-coffee.com/",
    "platform": "Wix(Wix Stores)",
    "address": "静岡県浜松市中央区三組町139-8",
    "prefecture": "静岡県",
    "robots_txt_status": "許可(User-agent: * は Allow: /。識別可能なUser-Agentを使用)",
    "source_note": "Buy Beans(https://www.kamoe-coffee.com/shop)と商品サイトマップ・各商品ページのJSON-LDを2026-10-26に確認。住所は https://www.kamoe-coffee.com/access。商品ページのlastmodは2026-09-08。",
    "last_verified_at": "2026-10-26",
}

BASE_URL = "https://www.kamoe-coffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL = 1.6
LD_PATTERN = re.compile(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
SIZE_PATTERN = re.compile(r"\s*\(\s*(\d+)\s*g\s*\)\s*$")
EXCLUDE_KEYWORDS = ("セット", "ドリップバッグ")
ROAST_PATTERN = re.compile(r"(極深煎り|中深煎り|浅煎り|中煎り|深煎り)")
PROCESS_PATTERN = re.compile(r"(?:生産処理|精製(?:処理)?)[\s:：]*([^\s、。]{1,15})")


def list_product_urls() -> list[str]:
    resp = requests.get(f"{BASE_URL}/store-products-sitemap.xml", headers=REQUEST_HEADERS, timeout=30)
    return re.findall(r"<loc>([^<]+)</loc>", resp.text)


def processing_from_description(desc: str) -> str | None:
    """説明文の「生産処理/精製」項目の値だけから精製方法を判定する(カッピング表現中の語の誤検出を避ける)。"""
    m = PROCESS_PATTERN.search(desc)
    return detect_processing_method(m.group(1)) if m else None


def build_record(url: str) -> dict | None:
    time.sleep(REQUEST_INTERVAL)
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    m = LD_PATTERN.search(resp.text)
    if not m:
        return None
    ld = json.loads(m.group(1))
    full_name = re.sub(r"\s+", " ", html.unescape(ld.get("name", "")).replace("　", " ")).strip()
    if any(kw in full_name for kw in EXCLUDE_KEYWORDS):
        return None
    size_m = SIZE_PATTERN.search(full_name)
    weight = int(size_m.group(1)) if size_m else None
    name = SIZE_PATTERN.sub("", full_name).strip()
    desc = re.sub(r"\s+", " ", html.unescape(ld.get("description") or "")).strip()[:400] or None
    offer = ld.get("offers") or {}
    if isinstance(offer, list):
        offer = offer[0] if offer else {}
    price = int(float(offer["price"])) if offer.get("price") else None
    in_stock = "InStock" in (offer.get("availability") or "")

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if "ブレンド" in name:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed["category"] = "デカフェ" if "カフェインレス" in name else "ストレート"
        if not parsed["origin_country"]:
            detected = detect_country_name(name)
            if detected:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)

    roast_m = ROAST_PATTERN.search(name)
    roast_level = ("深煎り" if roast_m.group(1) == "極深煎り" else roast_m.group(1)) if roast_m else None

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"] or processing_from_description(desc or ""),
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
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
            rec = build_record(url)
        except (requests.RequestException, ValueError) as e:
            print(f"[warn] 商品ページ取得失敗: {unquote(url)} ({e})")
            continue
        if rec is not None:
            records.append(rec)
    # 同一銘柄(名前から焙煎度の括弧を除いたもの)が複数重量で並ぶ場合は最小重量を代表にする
    best: dict[str, dict] = {}
    for rec in records:
        key = rec["raw_name"]
        cur = best.get(key)
        if cur is None or (rec["weight_g"] or 10**9) < (cur["weight_g"] or 10**9):
            best[key] = rec
    return list(best.values())


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_kamoecoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kamoecoffee.json に出力しました")


if __name__ == "__main__":
    main()
