# -*- coding: utf-8 -*-
"""
scrape_therisingsuncoffee.py

The Rising Sun Coffee(therisingsuncoffee.com、運営は株式会社ニハゼ。千葉県大網白里市の
自社焙煎所で焙煎し、都内・大網白里・鶴見・湘南の4店舗で販売。11店舗未満)の商品情報を
取得する。Shopify。

【店舗発見の経緯】
全国再調査(千葉県)の新規発掘で発見。公式サイトの「九十九里浜に面した大網白里で焙煎された
スペシャルティコーヒー」との記載と、沿革ページの「大網白里に焙煎所を移設(2024年)」で
千葉県内の自社焙煎を確認した。販売サイトの特商法表記の住所は千葉県大網白里市大網1481-3
(店舗)であり、これをSHOP_INFOの住所とした(焙煎所は同市駒込とされるが公式サイトでは
番地まで確認できなかった)。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`のうち、タイトルが
「<銘柄>【焙煎度】（200g…）」形式の焙煎済み豆8銘柄(ブレンド4・ストレート4、
デカフェ1含む)を対象とする。ブレンド4種は「200g / 1kg」の2サイズで同一ページに
載っているため、最小の200gを代表とする。お試しセット・ドリップバッグ・水出しバッグ・
アイスコーヒー・カフェラテベース・定期便・ギフト・グッズ・アパレル・スイーツは除外。
ブレンドの原産国は説明文の【ブレンド内容】に複数国があるため産地はNoneとする。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "The Rising Sun Coffee",
    "url": "https://therisingsuncoffee.com/",
    "platform": "Shopify",
    "address": "千葉県大網白里市大網1481-3",
    "prefecture": "千葉県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://therisingsuncoffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
# 例: "エチオピア・アナソラ【中浅煎り】（200g）" / "アイナハイナブレンド【中煎り】（200g / 1kg）"
TITLE_PATTERN = re.compile(r"^(?P<name>.+?)【(?P<roast>[^】]*煎り)】\s*（(?P<weight>\d+)\s*g[^）]*）\s*$")
EXCLUDE_WORDS = ("セット", "ドリップバッグ", "水出し", "アイスコーヒー", "定期便", "GIFT")


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    products = resp.json().get("products", [])

    records = []
    for p in products:
        title = re.sub(r"\s+", " ", p["title"]).strip()
        m = TITLE_PATTERN.match(title)
        if not m or any(w in title for w in EXCLUDE_WORDS):
            continue
        name = m.group("name").strip()
        roast_level = m.group("roast")
        weight = int(m.group("weight"))

        # 重量違いのバリエーションがあればタイトルの重量(最小サイズ)に一致するものを代表にする
        variants = p["variants"]
        matched = [v for v in variants if (v.get("title") or "").lower() == f"{weight}g"]
        variant = matched[0] if matched else variants[0]
        available = bool(variant.get("available"))

        body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
        desc = re.sub(r"\s+", " ", body)[:400] or None

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

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": roast_level,
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
    with open("data_therisingsuncoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_therisingsuncoffee.json に出力しました")


if __name__ == "__main__":
    main()
