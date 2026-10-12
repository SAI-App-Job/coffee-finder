# -*- coding: utf-8 -*-
"""
scrape_harukiya.py

春木屋「月滴庵」(HARUKIYA COFFEE ROASTERY、https://harukiya.com/、
山梨県富士吉田市下吉田4-1-11 の焙煎所併設カフェ)の商品情報を取得する。Shopify。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`のうちコーヒー豆の単品商品を対象とする。
- 除外: 茶・器具(product_typeが「コーヒー」でも空でもないもの)、セット・定期便の商品
  (タイトルに「セット」「定期便」を含む)、ドリップのみ、ジャスミン発酵の「アラビアンナイト」
  (花を加えて発酵させるインフューズド系のため除外)。
- バリエーションは「(焙煎タイプ /) 豆100g×1袋」「粉...」「ドリップ...」の組(全角数字)。
  「豆」かつ「×1袋」の最小重量のバリエーションを代表とする(焙煎タイプが複数ある商品は
  最初の焙煎タイプ)。
- 住所は店舗案内ページ(/pages/shop)の焙煎所併設カフェ。特商法の販売者住所は
  下吉田3-19-12(本店側)で異なる。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "春木屋「月滴庵」",
    "url": "https://harukiya.com/",
    "platform": "Shopify",
    "address": "山梨県富士吉田市下吉田4-1-11",
    "prefecture": "山梨県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://harukiya.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# ブレンド商品(商品名に「ブレンド」を含まないものを含む)
BLEND_HANDLES = {"p-coffee-n", "fujizakura", "furinkazan", "mocabrend-a", "akafuji", "fujiyamabrend", "black"}
# 除外する商品(花を加えて発酵させる製法)
EXCLUDE_HANDLES = {"arab"}
# 産地を明示する(商品名から検出できないもの)
ORIGIN_OVERRIDES = {
    "chelchele": "エチオピア",
    "kerincimountain": "インドネシア",
    "mandheling": "インドネシア",
    "fairtrade": "東ティモール",
    "moca-n": "エチオピア",
}

WEIGHT_PATTERN = re.compile(r"豆\s*(\d+)\s*g\s*[×x]\s*1\s*袋")
ROAST_PATTERN = re.compile(r"(フルシティ|シティ|ハイ|ミディアム|ライト|シナモン|フレンチ|イタリアン)(?:ー?ロースト|(?=\s|$))")


JP_ROAST_PATTERN = re.compile(r"(中浅煎り|中深煎り|中煎り|浅煎り|深煎り)")
BODY_JP_ROAST_PATTERN = re.compile(r"焙煎度[:：]\s*(中浅煎り|中深煎り|中煎り|浅煎り|深煎り)")


def detect_roast(variant_title: str, body_text: str) -> str | None:
    for text in (variant_title, body_text):
        m = ROAST_PATTERN.search(text)
        if m:
            return m.group(1) + "ロースト"
    m = JP_ROAST_PATTERN.search(variant_title) or BODY_JP_ROAST_PATTERN.search(body_text)
    return m.group(1) if m else None


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    products = resp.json().get("products", [])

    records = []
    for p in products:
        handle = p["handle"]
        if handle in EXCLUDE_HANDLES:
            continue
        if p.get("product_type") not in ("コーヒー", "") and handle != "p-coffee-n":
            continue
        title = unicodedata.normalize("NFKC", re.sub(r"\s+", " ", p["title"])).strip()
        if "セット" in title or "定期便" in title or "ドリップ" in title:
            continue

        weighted = []
        for v in p["variants"]:
            vt = unicodedata.normalize("NFKC", v.get("title") or "")
            m = WEIGHT_PATTERN.search(vt)
            if m:
                weighted.append((int(m.group(1)), vt, v))
        if not weighted:
            continue
        weight, vtitle, variant = min(weighted, key=lambda x: x[0])
        available = bool(variant.get("available"))

        body = unicodedata.normalize(
            "NFKC", BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True))
        body = re.sub(r"\s+", " ", body)
        i = body.find("商品説明")
        desc = (body[i + 4:] if i >= 0 else body).strip()[:400] or None

        name = re.sub(r"^【[^】]*】", "", title).strip()
        parsed = parse_product(name)
        if handle in BLEND_HANDLES or parsed["category"] == "ブレンド":
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            detected = detect_country_name(name)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, name)
            if handle in ORIGIN_OVERRIDES:
                parsed["origin_country"] = ORIGIN_OVERRIDES[handle]
                parsed["origin_source"] = "raw_name"

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": detect_roast(vtitle, body) or parsed["roast_level"],
            "roast_hint": None,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": int(float(variant["price"])),
            "weight_g": weight,
            "stock_status": "販売中" if available else "完売",
            "out_of_stock": not available,
            "product_url": f"{BASE_URL}/products/{handle}",
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_harukiya.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_harukiya.json に出力しました")


if __name__ == "__main__":
    main()
