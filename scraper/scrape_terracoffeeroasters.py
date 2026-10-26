# -*- coding: utf-8 -*-
"""
scrape_terracoffeeroasters.py

TERRA COFFEE ROASTERS(terracoffeeroasters.jp、本店・焙煎所の江坂公園店は大阪府吹田市垂水町3-30-9、
ほか新千里東店〈豊中市〉の2店舗)の商品情報を取得する。Shopify。
豆の焙煎はすべて江坂公園店で行う(ウォーカープラス記事の写真キャプション)。

【対象商品について】
Shopifyの`/products.json`のうち product_type が「Coffee」の商品で、バリエーションに
「<重量>g / 豆のまま」を持つもの(シングルオリジン4種とDaily Roast1種)。
除外: TEST ROAST(1kg、重量表記なし)、Cold Brew Bag、ドリップバッグ(product_type=Drip Bag)、
トライアルセット・ギフト・定期便、器具・雑貨。
バリエーションは「<重量>g / <挽き方>」の組で、豆のままの最小重量を代表にする
(シングルは100g、Daily Roastは250g)。焙煎度は本文の「Roast」欄(Filter Roast / Omni Roast)を
roast_hint に入れる(焙煎度の浅深の明記は無いため roast_level は付けない)。
"""

import json
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "TERRA COFFEE ROASTERS",
    "url": "https://terracoffeeroasters.jp/",
    "platform": "Shopify",
    "address": "大阪府吹田市垂水町3-30-9",
    "prefecture": "大阪府",
    "robots_txt_status": "許可(2026-10-26確認。Shopify標準のrobots.txtで商品・コレクションは巡回可。/products.json を使用)",
    "source_note": "公式ショップ(https://terracoffeeroasters.jp/)の /products.json を2026-10-26に取得。住所は江坂公園店(焙煎所を兼ねる本店)。ウォーカープラス記事(https://www.walkerplus.com/article/1119619/)で住所と「豆の焙煎はすべて江坂公園店で行う」を確認。店舗数2(江坂公園店・新千里東店)。",
    "last_verified_at": "2026-10-26",
}

BASE_URL = "https://terracoffeeroasters.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BEAN_TYPE = "Coffee"
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")
EXCLUDE_KEYWORDS = ("TEST ROAST", "Cold Brew", "Drip Bag", "Set", "セット", "Gift", "Subscription")
ROAST_PATTERN = re.compile(r"Roast\s*\|\s*([A-Za-z ]+?Roast)\s*\|")


def fetch_products() -> list[dict]:
    for _ in range(4):
        resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
        if resp.status_code == 429:
            time.sleep(int(resp.headers.get("Retry-After") or 60) + 1)
            continue
        resp.raise_for_status()
        return resp.json().get("products", [])
    raise RuntimeError("429が続いたため取得できませんでした")


def scrape_all_products(products: list[dict] | None = None) -> list[dict]:
    records = []
    for p in (products if products is not None else fetch_products()):
        if p.get("product_type") != BEAN_TYPE:
            continue
        title = re.sub(r"\s+", " ", p["title"]).strip()
        if any(k.lower() in title.lower() for k in EXCLUDE_KEYWORDS):
            continue
        title = re.sub(r"^【[^】]*】\s*", "", title)

        weighted = []
        for v in p["variants"]:
            vt = v.get("title") or ""
            m = WEIGHT_PATTERN.search(vt)
            if m and "豆のまま" in vt:
                weighted.append((int(m.group(1)), v))
        if not weighted:
            continue
        weight, variant = min(weighted, key=lambda x: x[0])
        available = bool(variant.get("available"))

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" | ", strip=True)
        body = re.sub(r"\s+", " ", body)
        rm = ROAST_PATTERN.search(body)
        roast_hint = rm.group(1).strip() if rm else None
        desc = body.split(" | ")[0].strip()[:400] or None

        parsed = parse_product(title.replace("Field Blend", "Field-Mix"))  # Field Blend は品種混合のシングルロットでありブレンドではない
        parsed["raw_name"] = title
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
            "roast_level": parsed["roast_level"],
            "roast_hint": roast_hint,
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
    # 引数に保存済みの products.json を渡すと、再取得せずそのファイルから生成する(429回避のため)
    products = None
    if len(sys.argv) > 1:
        with open(sys.argv[1], encoding="utf-8") as f:
            products = json.load(f).get("products", [])
    records = scrape_all_products(products)
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_terracoffeeroasters.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_terracoffeeroasters.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], "|", r["category"], r["origin_country"], r["processing_method"], r["roast_hint"], r["price"], r["weight_g"], r["stock_status"])


if __name__ == "__main__":
    main()
