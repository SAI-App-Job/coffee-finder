# -*- coding: utf-8 -*-
"""
scrape_blueoceannext.py

BLUE OCEAN NEXT(blueoceancoffee.store、鳥取県境港市岬町1-43、土鍋(セラポット)焙煎の自家焙煎店)の
商品情報を取得する。Wix Stores。

【住所について】
特定商取引法ページ(https://www.blueoceancoffee.store/terms)で実データ確認済み(2026-10):
「販売業者 BLUE OCEAN NEXT / 所在地 6840017 鳥取県境港市岬町1－43」。

【取得方法】
実データ確認済み(2026-10): store-products-sitemap.xml の商品ページ(/product-page/<slug>)67件。
各ページのJSON-LD(Product)と埋め込みの productItems / additionalInfo(珈琲豆情報)を使う。
「豆の状態(豆/粉)」のオプションは価格差がない。

【対象商品】
店のラインナップは「200g×2袋」セット表記の商品が多いが、同じ銘柄に80g(一部200g)の単品ページがあるため、
それを採用する(銘柄ごとに最小重量の単品ページ。実際はすべて80g):
BLUE(青)・OCEAN(海)・FIELD(オーガニック)・GOLD(金)・SILVER(銀)・満月珈琲・遍路珈琲「結願」・遍路珈琲「遍路道」の8銘柄。
すべて複数産地のブレンド(商品説明に配合比率あり)。
【除外】「200g×2袋」セット表記の商品(BLUE/OCEAN/FIELD/満月珈琲の2袋セットは単品ページあり、
FARM(オーガニック)とSweet Dream Coffee(デカフェ)は単品ページ自体が無いため除外)、
ギフトセット、OCEAN×満月珈琲セット、ドリップ珈琲/ドリップバッグ(各種セット)、ボタニカル/ハーブ入りコーヒー
(インフューズド)、ご当地パッケージのドリップ珈琲、ひすい様注文専用ページ、Notebook Coffee、ギフトカード等。
"""

import json
import re
import time
import unicodedata
from urllib.parse import quote

import requests

from coffee_parser import parse_product

SHOP_INFO = {
    "name": "BLUE OCEAN NEXT",
    "url": "https://www.blueoceancoffee.store/",
    "platform": "Wix",
    "address": "鳥取県境港市岬町1-43",
    "prefecture": "鳥取県",
    "robots_txt_status": "許可(2026-10確認。User-agent: * は Allow: /。商品ページは制限対象外)",
}

SITEMAP_URL = "https://www.blueoceancoffee.store/store-products-sitemap.xml"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 1
EXCLUDE_KEYWORDS = ("×", "袋", "セット", "ドリップ", "ボタニカル", "注文専用", "ギフト", "各")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")
BIG = 10 ** 9
DEC = json.JSONDecoder()


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


def extract_json_after(html: str, key: str):
    k = html.find('"%s":[' % key)
    if k < 0:
        return None
    arr, _ = DEC.raw_decode(html[k + len(key) + 3:])
    return arr


def rich_text(desc_json: str) -> str:
    out = []

    def walk(n):
        if n.get("type") == "TEXT":
            out.append(n["textData"]["text"])
        for c in n.get("nodes", []):
            walk(c)
        if n.get("type") == "PARAGRAPH":
            out.append("\n")

    walk(json.loads(desc_json))
    return "".join(out)


def scrape_all_products() -> list[dict]:
    sitemap = fetch(SITEMAP_URL)
    urls = re.findall(r"<loc>([^<]+/product-page/[^<]+)</loc>", sitemap)

    candidates = {}
    for url in urls:
        time.sleep(CRAWL_DELAY_SECONDS)
        html = fetch(url)
        ld = extract_product_ld(html)
        if not ld:
            continue
        title = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", ld.get("name") or "")).strip()
        if not title or any(kw in title for kw in EXCLUDE_KEYWORDS):
            continue
        wm = WEIGHT_PATTERN.search(title)
        if not wm:
            continue
        weight = int(wm.group(1))
        name = re.sub(r"\s*\d+\s*g\s*$", "", title).strip()
        offer = ld.get("offers") or {}
        if isinstance(offer, list):
            offer = offer[0] if offer else {}
        if offer.get("price") in (None, ""):
            continue
        price = int(float(offer["price"]))
        available = "OutOfStock" not in (offer.get("availability") or "")
        desc = (ld.get("description") or "").replace("&#010;", "\n").replace("&#10;", "\n")
        desc = re.sub(r"[ \t]*\n[ \t\n]*", "\n", desc).strip()
        ai = extract_json_after(html, "additionalInfo") or []
        info = rich_text(ai[0]["description"]) if ai else ""
        rm = re.search(r"焙煎度合い\s*[：:]\s*([^\n]+)", info)
        rec = dict(name=name, weight=weight, price=price, available=available, desc=desc,
                   roast=rm.group(1).strip() if rm else None, url=offer.get("url") or url)
        cur = candidates.get(name)
        if cur is None or (weight, price) < (cur["weight"], cur["price"]):
            candidates[name] = rec

    records = []
    for rec in candidates.values():
        name = rec["name"]
        parsed = parse_product(name)
        # 商品説明に配合比率(NN%)が2つ以上あればブレンド
        n_pct = len(re.findall(r"\d+\s*[%％]", rec["desc"]))
        is_blend = n_pct >= 2 or "ブレンド" in rec["desc"]
        if is_blend:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": None,
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": rec["roast"],
            "roast_hint": None,
            "flavor_notes": rec["desc"][:400] or None,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": rec["price"],
            "weight_g": rec["weight"],
            "stock_status": "販売中" if rec["available"] else "完売",
            "out_of_stock": not rec["available"],
            "product_url": rec["url"],
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_blueoceannext.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_blueoceannext.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], r["category"], r["origin_country"], r["roast_level"], r["price"], r["weight_g"],
              r["stock_status"], r["product_url"])


if __name__ == "__main__":
    main()
