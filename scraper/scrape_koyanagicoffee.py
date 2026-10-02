# -*- coding: utf-8 -*-
"""
scrape_koyanagicoffee.py

コヤナギコーヒーニッポン(koyanagicoffeenippon.com、埼玉県東松山市下唐子
1967-2の東松山焙煎直売所。ニュージーランドで焙煎経験を積んだオーナーによる
スペシャルティコーヒーの自家焙煎。金・土のみ営業、池袋への出張営業あり)の
商品情報を取得する。Wix(Wix Stores)。

【店舗発見の経緯】
2026-09-04の別セッションで「Wixサイトの商品データ埋め込みが部分的で確実な
自動抽出に時間を要する」として見送られていたが、全国再調査(埼玉県)で再検証し、
`/store-products-sitemap.xml`から全商品ページURLを列挙し、各商品ページの
JSON-LD(schema.org Product)から名前・説明・価格・在庫を取得できることを
確認して実装した。(`/category/all-products`は404。)

【対象商品について】
実データ確認済み(2026-10時点): サイトマップ掲載29ページのうち、ドリップバッグ・
水出しバッグ・サブスクリプション・器具・チョコレートパウダー等を除いた
豆9銘柄(ブレンド1・ストレート8、カフェインレス含む)を対象とする。
商品名の末尾「フィルターロースト105g～」は焙煎度合いと最小重量(105g)を
示すため、商品名からは除去しroast_hint・weight_gに反映する。
"""

import html
import json
import re

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method

SHOP_INFO = {
    "name": "コヤナギコーヒーニッポン",
    "url": "https://www.koyanagicoffeenippon.com/",
    "platform": "Wix(Wix Stores)",
    "address": "埼玉県東松山市下唐子1967-2",
    "prefecture": "埼玉県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://www.koyanagicoffeenippon.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

BEAN_SLUGS = [
    "colombia-lospatios-peach-geisha",
    "colombia-elcurruso-chiroso",
    "colombia-luz-helena-lychee-coferm",
    "colombia-lospatios-funkycherry",
    "guatemala-elprogreso-washed",
    "ethiopia-gedeb-halo-natural",
    "kenya-nyerihill-aa",
    "decaf-guatemala",
    "espresso-seasonal",
]

LD_PATTERN = re.compile(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
SUFFIX_PATTERN = re.compile(r"[,，]?\s*(フィルター(/エスプレッソ共通)?ロースト)\s*(\d+)g～?$")


def build_record(slug: str) -> dict | None:
    url = f"{BASE_URL}/product-page/{slug}"
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    ld_m = LD_PATTERN.search(resp.text)
    if not ld_m:
        return None
    ld = json.loads(ld_m.group(1))

    raw = re.sub(r"\s+", " ", ld.get("name", "")).strip()
    suffix_m = SUFFIX_PATTERN.search(raw)
    roast_hint = suffix_m.group(1) if suffix_m else None
    weight_g = int(suffix_m.group(3)) if suffix_m else None
    name = SUFFIX_PATTERN.sub("", raw).strip(" ,")
    if "シーズナルエスプレッソブレンド" in name:
        weight_m = re.search(r"(\d+)g～", name)
        weight_g = int(weight_m.group(1)) if weight_m else weight_g
        name = re.sub(r"\s*\d+g～$", "", name)
        roast_hint = "エスプレッソロースト"

    desc = html.unescape(ld.get("description") or "")
    desc = re.sub(r"\s+", " ", desc).strip()[:500] or None
    offer = ld.get("offers") or {}
    price = int(float(offer["price"])) if offer.get("price") else None
    in_stock = "InStock" in (offer.get("availability") or "")

    parsed = parse_product(name)
    if "ブレンド" in name:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"] or detect_processing_method(name),
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": roast_hint,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": "販売中" if in_stock else "完売",
        "out_of_stock": not in_stock,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for slug in BEAN_SLUGS:
        try:
            record = build_record(slug)
        except requests.RequestException as e:
            print(f"[warn] 商品ページ取得失敗: {slug} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_koyanagicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_koyanagicoffee.json に出力しました")


if __name__ == "__main__":
    main()
