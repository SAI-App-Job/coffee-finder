# -*- coding: utf-8 -*-
"""
scrape_cafecajon.py

カフェカホン(CafeCajon、cafecajon.info、東京都調布市若葉町2-1-3 ハイム川原1A、京王線仙川駅近く、
スペシャルティコーヒー専門自家焙煎店。店舗は仙川の1店舗)のオンラインショップの商品情報を取得する。
Shopify(/collections/beans/products.json)。

【対象商品について】
実データ確認済み(2026-10時点): コレクション「beans」(現行の豆24件)のうち、複数銘柄のセット
「店主におまかせセット」を除く23件(ブレンド3・シングルオリジン・デカフェ。商品の最新公開は
2026-09)を収録する。商品全体(91件)には過去に販売した豆(コレクション「過去に販売していた豆」
56件、2022〜2025年登録で在庫なし)・コーヒー器具・定期便が含まれるが、これらは除外する。

【重量・価格・在庫】
バリエーションは「サイズ(100g/150g/200g/500g/1kg/1.5kg) / 挽き方」の組合せ。最小サイズ100g・
豆のままのバリエーションの価格(税込)を採用し、在庫は100gバリエーションのavailableで判定する。
焙煎度はタグ(「シティロースト」「浅めのシティロースト」等)をroast_hintに、焙煎度の
正式名はroast_levelに保持する。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "カフェカホン",
    "url": "https://cafecajon.info/",
    "platform": "Shopify",
    "address": "東京都調布市若葉町2-1-3 ハイム川原1A",
    "prefecture": "東京都",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://cafecajon.info"
COLLECTION_JSON = f"{BASE_URL}/collections/beans/products.json?limit=250"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_KEYWORDS = ("セット", "定期便", "ドリッパー", "フィルター")


def fetch_products() -> list[dict]:
    products: list[dict] = []
    page = 1
    while True:
        resp = requests.get(f"{COLLECTION_JSON}&page={page}", headers=REQUEST_HEADERS, timeout=30)
        resp.raise_for_status()
        batch = resp.json().get("products", [])
        if not batch:
            break
        products.extend(batch)
        if len(batch) < 250:
            break
        page += 1
    return products


def pick_variant(p: dict) -> dict | None:
    cands = []
    for v in p.get("variants") or []:
        title = unicodedata.normalize("NFKC", v.get("title") or "")
        m = re.match(r"^\s*(\d+)\s*g\b\s*(?:/\s*(.*))?$", title, re.I)
        if not m:
            continue
        grind = m.group(2) or ""
        cands.append((int(m.group(1)), 0 if "豆のまま" in grind else 1, v))
    if not cands:
        return None
    cands.sort(key=lambda c: (c[0], c[1]))
    return cands[0][2] | {"_weight": cands[0][0]}


def build_record(p: dict) -> dict | None:
    title = unicodedata.normalize("NFKC", p["title"]).strip()
    if any(kw in title for kw in EXCLUDE_KEYWORDS) or "セット" in (p.get("tags") or []):
        return None
    variant = pick_variant(p)
    if variant is None:
        return None
    weight = variant["_weight"]
    # 同一サイズの全バリエーション(挽き方違い)のいずれかが買えれば在庫あり
    same_size = [
        v for v in p["variants"]
        if re.match(rf"^\s*{weight}\s*g\b", unicodedata.normalize("NFKC", v.get("title") or ""), re.I)
    ]
    available = any(v.get("available") for v in same_size)
    tags = p.get("tags") or []
    parsed = parse_product(title)
    if "ブレンド" in title or "ブレンド" in tags:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        parsed = apply_category_hint_fallback(parsed, title)
        if not parsed["origin_country"]:
            c = detect_country_name(" ".join(tags))
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "tags"
    roast_tags = [t for t in tags if "ロースト" in t]
    roast_hint = roast_tags[0] if roast_tags else None
    roast_level = parsed["roast_level"]
    if roast_hint and not roast_level:
        # 「浅めのシティロースト」等は修飾語を除いた正式名を採用
        base = re.sub(r"^(浅め|深め)の", "", roast_hint)
        roast_level = parse_product(base)["roast_level"]
    soup = BeautifulSoup(p.get("body_html") or "", "html.parser")
    lines = [ln.strip() for ln in soup.get_text("\n", strip=True).split("\n") if ln.strip()]
    flavor_notes = " ".join(lines)[:300] or None
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_hint": roast_hint,
        "flavor_notes": flavor_notes,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(float(variant["price"])),
        "weight_g": weight,
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
    with open("data_cafecajon.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_cafecajon.json に出力しました")


if __name__ == "__main__":
    main()
