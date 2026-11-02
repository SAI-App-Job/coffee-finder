# -*- coding: utf-8 -*-
"""
scrape_coffeefam.py

Coffee fam.(coffee-fam-shop.com、福井県越前市広瀬町168-8-70、焚き火カフェ併設の自家焙煎店)の
商品情報を取得する。Shopify(独自ドメイン)。

【店舗発見の経緯】
全国再調査(北陸3県)の新規発掘で発見(2026-11)。

【実店舗・自家焙煎の根拠(2026-11-03確認)】
特商法ページ https://coffee-fam-shop.com/pages/for-shipping-charges に「店舗概要」として
「越前市広瀬町168-8-70」(店主 谷川和也)。https://coffee-fam-shop.com/pages/campfire-cafe に
「福井県越前市広瀬町にて、コーヒー屋が営む焚き火カフェ」。ショップ説明に
「スペシャルティコーヒーの自家焙煎店です」。食べログにも掲載。

【対象商品について】
Shopifyの`/products.json`のうち product_type が「コーヒー豆」「デカフェ」の商品を対象とする。
バリエーションは「<焙煎度> / <豆または粉> / <重量>」の組で、豆のままの最小重量
(通常150g、デカフェは50g)の価格を代表とする(浅煎りの Strawberry Apricot は焙煎度違い
2種があり、先頭の「極浅煎り」を採用)。
定期便・セット商品・テイスティングビーンズ30g・キャンドル・ギフトカードは除外。
同名の定期便商品(product_type=定期便)は重複するため除外。

【robots.txtについて】
2026-11-03確認。/products.json は Disallow されていない(/collections/*sort_by* 等のみ)。
products.json が429を返した場合は Retry-After に従って待ち、同じURLを再試行する。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "Coffee fam.",
    "url": "https://coffee-fam-shop.com/",
    "platform": "Shopify",
    "address": "福井県越前市広瀬町168-8-70",
    "prefecture": "福井県",
    "robots_txt_status": "許可(2026-11-03確認。/products.json は禁止されていない)",
    "source_note": "https://coffee-fam-shop.com/products.json (2026-11-03確認、updated_at は2026-11-02で非常に新しい)。住所は特商法ページ・食べログ",
    "last_verified_at": "2026-11-03",
}

BASE_URL = "https://coffee-fam-shop.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BEAN_TYPES = ("コーヒー豆", "デカフェ")
WEIGHT_PATTERN = re.compile(r"^(\d+)\s*g$")
BOILERPLATE_PATTERN = re.compile(r"^飲みごろは焙煎から[^。]*。\s*時間の経過による風味の変化をお楽しみください。\s*")

# 商品名の「≫ <英語の国名>」を日本語の国名にする
COUNTRY_MAP = {
    "Ethiopia": "エチオピア", "Indonesia": "インドネシア", "Mexico": "メキシコ",
    "Costa Rica": "コスタリカ", "Brazil": "ブラジル", "Kenya": "ケニア", "Colombia": "コロンビア",
}
MAX_RETRIES = 3


def fetch_products_json() -> list[dict]:
    url = f"{BASE_URL}/products.json?limit=250"
    for attempt in range(MAX_RETRIES):
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", "60")) + 5
            print(f"[info] 429 (Retry-After)。{wait}秒待って同じURLを再試行します")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json().get("products", [])
    raise RuntimeError("products.json が429のため取得できませんでした")


def scrape_all_products() -> list[dict]:
    records = []
    for p in fetch_products_json():
        if p.get("product_type") not in BEAN_TYPES:
            continue
        title = re.sub(r"\s+", " ", p["title"]).strip()
        if "セット" in title:
            continue

        beans = []
        for v in p["variants"]:
            parts = [x.strip() for x in (v.get("title") or "").split(" / ")]
            if len(parts) != 3 or parts[1] != "豆":
                continue
            m = WEIGHT_PATTERN.match(parts[2])
            if m:
                beans.append((int(m.group(1)), parts[0], v))
        if not beans:
            continue
        weight = min(b[0] for b in beans)
        # 同重量なら先頭(商品ページ表示順)のバリエーションを代表にする
        _, roast_label, variant = next(b for b in beans if b[0] == weight)
        roast_level = re.sub(r"[（(].*$", "", roast_label).strip() or None

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        body = BOILERPLATE_PATTERN.sub("", re.sub(r"\s+", " ", body))
        desc = body[:400] or None

        parsed = parse_product(title)
        if p["product_type"] == "デカフェ" or title.startswith("【デカフェ】"):
            parsed["category"] = "デカフェ"
        elif "Blend" in title or "ブレンド" in title:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        if parsed["category"] != "ブレンド":
            m = re.search(r"≫\s*([A-Za-z ]+)$", title)
            country = COUNTRY_MAP.get(m.group(1).strip()) if m else None
            if country:
                parsed["origin_country"] = country
                parsed["origin_source"] = "raw_name"
            else:
                detected = detect_country_name(title)
                if detected and not parsed["origin_country"]:
                    parsed["origin_country"] = detected
                    parsed["origin_source"] = "raw_name"
                parsed = apply_category_hint_fallback(parsed, title)

        available = bool(variant.get("available"))
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
            "roast_hint": None,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": int(float(variant["price"])),
            "weight_g": weight,
            "stock_status": "販売中" if available else "完売",
            "out_of_stock": not available,
            "product_url": f"{BASE_URL}/products/{p['handle']}",
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_coffeefam.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeefam.json に出力しました")


if __name__ == "__main__":
    main()
