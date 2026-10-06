# -*- coding: utf-8 -*-
"""
scrape_pcraftcoffee.py

P-craft 珈琲豆店(pcraftcoffee.com、宮城県仙台市宮城野区岩切分台3-5-12、自家焙煎豆の通販)の
商品情報を取得する。Wix。

【取得方法】
実データ確認済み(2026-10): store-products-sitemap.xml に商品ページ(/product-page/<slug>)が16件。
うちコーヒー豆単品12件を対象とし、ドリップバッグ、水出しアイスコーヒー(バッグ)、お試しセット2種
は除外する。各ページのJSON-LD(Product)から name / description / availability を、ページ内
の埋め込みJSON(options と productItems)から「グラム」オプションごとの価格・在庫を取得する。

【代表価格について】
商品ごとにグラム選択肢が異なる(100g/200gの2択、150gのみ、200gのみ)。最小グラムの
バリエーション(挽き方違いは同価格)の価格を代表とする。100g/200g両方ある商品は100g、
ブレンド2種は150gのみ、シングルの一部は200gのみ。
在庫は代表グラムのバリエーションのinventory.statusで判定する(全て追跡なし=in_stock表示)。

【焙煎度・説明】
description の先頭に「中煎り フローラル」「中深煎り ブレンド」のようなタグ行があり、先頭の
焙煎度表記(浅煎り/中煎り/中深煎り/深煎り)を roast_hint に入れる。
description の本文は風味・産地の紹介文のため flavor_notes に入れる(400文字まで)。
"""

import html as htmllib
import json
import re
import time
from urllib.parse import quote

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "P-craft 珈琲豆店",
    "url": "https://www.pcraftcoffee.com/",
    "platform": "Wix",
    "address": "宮城県仙台市宮城野区岩切分台3-5-12",
    "prefecture": "宮城県",
    "robots_txt_status": "未確認(Wix標準構成)",
}

SITEMAP_URL = "https://www.pcraftcoffee.com/store-products-sitemap.xml"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 1

NON_BEAN_KEYWORDS = ["ドリップバッグ", "ドリップバック", "アイスコーヒー", "お試しセット", "セット", "Selection"]
ROAST_PATTERN = re.compile(r"(浅煎り|中浅煎り|中煎り|中深煎り|深煎り)")


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


def extract_json_array(html: str, key: str) -> list | None:
    i = html.find(f'"{key}":[')
    if i < 0:
        return None
    start = html.find("[", i)
    try:
        arr, _ = json.JSONDecoder().raw_decode(html[start:])
    except json.JSONDecodeError:
        return None
    return arr


def pick_min_weight_variant(html: str):
    """(weight_g, price, available) を最小グラムのバリエーションから返す。取れなければ None"""
    options = extract_json_array(html, "options") or []
    items = extract_json_array(html, "productItems") or []
    gram_opt = next((o for o in options if o.get("title") == "グラム"), None)
    if not gram_opt or not items:
        return None
    sel_weight = {}
    for sel in gram_opt.get("selections") or []:
        m = re.search(r"(\d+)\s*g", sel.get("value") or "")
        if m:
            sel_weight[sel["id"]] = int(m.group(1))
    if not sel_weight:
        return None
    min_w = min(sel_weight.values())
    min_ids = {i for i, w in sel_weight.items() if w == min_w}
    cands = [it for it in items if min_ids & set(it.get("optionsSelections") or [])]
    if not cands:
        return None
    price = min(it["price"] for it in cands)
    available = any((it.get("inventory") or {}).get("status") != "out_of_stock" for it in cands)
    return min_w, int(price), available


def scrape_all_products() -> list[dict]:
    sitemap = fetch(SITEMAP_URL)
    urls = re.findall(r"<loc>([^<]+/product-page/[^<]+)</loc>", sitemap)

    records = []
    for url in urls:
        time.sleep(CRAWL_DELAY_SECONDS)
        html = fetch(url)
        ld = extract_product_ld(html)
        if not ld:
            continue
        title = re.sub(r"\s+", " ", ld.get("name") or "").strip()
        if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
            continue

        offer = ld.get("offers") or {}
        if isinstance(offer, list):
            offer = offer[0] if offer else {}
        ld_available = "OutOfStock" not in (offer.get("availability") or "")

        variant = pick_min_weight_variant(html)
        if variant:
            weight, price, v_available = variant
            available = ld_available and v_available
        else:
            weight = None
            price = int(float(offer["price"])) if offer.get("price") not in (None, "") else None
            available = ld_available

        desc_raw = htmllib.unescape(ld.get("description") or "")
        desc_lines = [re.sub(r"\s+", " ", l).strip() for l in desc_raw.split("\n")]
        desc_lines = [l for l in desc_lines if l]
        tag_line = desc_lines[0] if desc_lines else ""
        rm = ROAST_PATTERN.search(title) or ROAST_PATTERN.search(tag_line)
        roast_hint = rm.group(1) if rm else None
        body = " ".join(desc_lines[1:]) if len(tag_line) <= 40 and len(desc_lines) > 1 else " ".join(desc_lines)
        flavor_notes = body[:400] or None

        is_blend = ("ブレンド" in title) or ("blend" in title.lower()) or ("ブレンド" in tag_line and len(tag_line) <= 40)

        parsed = parse_product(title)
        if is_blend:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
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
            "flavor_notes": flavor_notes,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": price,
            "weight_g": weight,
            "stock_status": "販売中" if available else "完売",
            "out_of_stock": not available,
            "product_url": offer.get("url") or url,
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_pcraftcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_pcraftcoffee.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], r["category"], r["origin_country"], r["roast_hint"], r["price"], r["weight_g"], r["stock_status"], (r["flavor_notes"] or "")[:25])


if __name__ == "__main__":
    main()
