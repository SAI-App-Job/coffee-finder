# -*- coding: utf-8 -*-
"""
scrape_coffeeportashiya.py

COFFEE PORT 芦屋浜ロースタリー(coffeeport.net、兵庫県芦屋市涼風町14-3、自家焙煎)の
商品情報を取得する。Shopify。(同ディレクトリの scrape_coffeeporte.py は別店舗)

【対象商品について】
実データ確認済み(2026-10時点): `/products.json`は22件でproduct_typeは「コーヒー」と空が
混在する。「豆」を含む重量付きバリエーション(100g/200g等)を持つ焙煎豆商品のみを対象とし、
以下は除外する。
  - 卸定期便2キロ、片岡様専用ご注文ページ、ドリップバッグ、ドリッパー・フィルター等の器具、
    ラッピング・送料・ギフトカード
  - 「インフューズドコーヒー」(果肉・ワイン酵母等を添加した加工コーヒーのため、
    フレーバー系として除外。現在は在庫なし)
「ofukuro no cafe オリジナルブレンド」は1ページに no.1 凪 と no.2 宵 の2ブレンドが
載っているため、2商品に分割し、product_urlは `ページURL#<商品名>` で一意にする。
バリエーションは「100g 豆」「豆100ｇ」「100ｇ中挽き粉」等の表記が混在するため、粉
(「粉」を含む)を除いた最小重量のバリエーションの価格・在庫を代表とする。

【価格について】
サイトに「5,400円(税込)以上のご購入で送料無料」と表記があり、商品ページの価格も
税込表示(`products.json`のpriceは税込)。
"""

import json
import re
import urllib.parse

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "COFFEE PORT 芦屋浜ロースタリー",
    "url": "https://coffeeport.net/",
    "platform": "Shopify",
    "address": "兵庫県芦屋市涼風町14-3",
    "prefecture": "兵庫県",
    "robots_txt_status": "未確認(Shopify標準構成)",
}

BASE_URL = "https://coffeeport.net"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_KEYWORDS = [
    "定期便", "専用ご注文", "ドリップバッグ", "ドリッパー", "フィルター", "ラッピング",
    "送料", "ギフト", "インフューズド", "gift",
]
WEIGHT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|㎏|g|ｇ)", re.I)
ROAST_HINT_PATTERN = re.compile(r"(ライト|シナモン|ミディアム|ハイ|フルシティ|シティ|フレンチダーク|フレンチ|イタリアン|ダーク)\s*ー?\s*ロースト")


def fetch_products() -> list[dict]:
    products, page = [], 1
    while True:
        resp = requests.get(f"{BASE_URL}/products.json?limit=250&page={page}", headers=REQUEST_HEADERS, timeout=30)
        resp.raise_for_status()
        batch = resp.json().get("products", [])
        if not batch:
            break
        products.extend(batch)
        page += 1
    return products


def variant_weight(title: str):
    m = WEIGHT_PATTERN.search(title or "")
    if not m:
        return None
    val = float(m.group(1))
    return int(round(val * 1000)) if m.group(2).lower() in ("kg", "㎏") else int(round(val))


def pick_variant(variants: list[dict]):
    cands = []
    for v in variants:
        t = v.get("title") or ""
        if "粉" in t:
            continue
        if "豆" not in t and "bean" not in t.lower():
            continue
        w = variant_weight(t)
        if w:
            cands.append((w, v))
    if not cands:
        return None
    return min(cands, key=lambda x: x[0])


def clean_title(title: str) -> str:
    title = title.replace("　", " ")
    return re.sub(r"\s+", " ", title).strip()


def make_record(name: str, p: dict, variants: list[dict], url: str) -> dict | None:
    picked = pick_variant(variants)
    if not picked:
        return None
    weight, variant = picked
    body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
    desc = re.sub(r"\s+", " ", body)[:400] or None

    parsed = parse_product(name)
    if "ブレンド" in name or "blend" in name.lower():
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"]:
            # 「ぺルー」(ひらがなぺ)の表記ゆれを「ペルー」に正規化して判定
            detected = detect_country_name(name.replace("ぺルー", "ペルー"))
            if detected:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)

    roast_hint = None
    m = ROAST_HINT_PATTERN.search(name)
    if m:
        roast_hint = m.group(0).replace(" ", "")
    available = bool(variant.get("available"))
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
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
        "product_url": url,
    }


def build_records(p: dict) -> list[dict]:
    title = clean_title(p["title"])
    if any(kw.lower() in title.lower() for kw in EXCLUDE_KEYWORDS):
        return []
    page_url = f"{BASE_URL}/products/{p['handle']}"

    # 1ページに複数ブレンドが載るケース(ofukuro no cafe オリジナルブレンド: no.1 凪 / no.2 宵)
    prefixes = []
    for v in p["variants"]:
        pre = (v.get("title") or "").split(" / ")[0].strip() if " / " in (v.get("title") or "") else None
        if pre and variant_weight(pre) is None and pre not in prefixes:
            prefixes.append(pre)
    if len(prefixes) >= 2 and "ofukuro" in title:
        base = re.sub(r"\s*no\.1.*$", "", title).strip()
        records = []
        for pre in prefixes:
            vs = [v for v in p["variants"] if (v.get("title") or "").startswith(pre + " / ")]
            name = clean_title(f"{base} {pre}")
            rec = make_record(name, p, vs, page_url + "#" + urllib.parse.quote(name))
            if rec:
                records.append(rec)
        return records

    rec = make_record(title, p, p["variants"], page_url)
    return [rec] if rec else []


def scrape_all_products() -> list[dict]:
    records = []
    for p in fetch_products():
        records.extend(build_records(p))
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_coffeeportashiya.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeeportashiya.json に出力しました")


if __name__ == "__main__":
    main()
