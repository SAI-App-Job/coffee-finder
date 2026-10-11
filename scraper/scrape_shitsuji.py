# -*- coding: utf-8 -*-
"""
scrape_shitsuji.py

シツジ珈琲(shitsuji.coffee、滋賀県彦根市本町1-9-24、運営: ボイスカルチャー
ジャパン株式会社)の自家焙煎豆の商品情報を取得する。WordPress+WooCommerce。

robots.txt確認済み(2026-10-11): User-agent: *に対し管理系・add-to-cartのみ
Disallow。公開Store API(/wp-json/wc/store/v1/products)は制限対象外。

【対象商品】Store APIで全136件(2026-10-11時点)。カテゴリ「レギュラー」
「高級豆」「期間限定」に属する100g(ゲイシャのみ50g)表記の焙煎豆のみ採用。
食品・日用品・KONO器具・保存容器、おためしセット・ギフト、水出しデルパック
(パック商品)は除外。「ふーたんのアイスコーヒー 100g【ブラジル】」は豆(粉/
豆選択)なので採用。挽き方はバリエーション属性で価格差なし。
"""
import json
import re

import requests

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "シツジ珈琲",
    "url": "https://shitsuji.coffee/",
    "platform": "WooCommerce",
    "address": "滋賀県彦根市本町1-9-24",
    "prefecture": "滋賀県",
    "robots_txt_status": "実質許可(2026-10確認。管理系パスとadd-to-cartのみDisallow。"
                          "Store APIは制限対象外)",
}
API_URL = "https://shitsuji.coffee/wp-json/wc/store/v1/products"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BEAN_CATEGORIES = {"レギュラー", "高級豆", "期間限定", "アイスコーヒー"}
EXCLUDE_KEYWORDS = ["おためしセット", "ギフト", "デルパック", "セット", "ペーパー"]
ROAST_RE = re.compile(r"(浅煎り|中浅煎り|中煎り|中深煎り|深煎り)")
TAG_RE = re.compile(r"<[^>]+>")


def strip_html(s):
    return re.sub(r"\s+", " ", TAG_RE.sub(" ", s or "")).strip()


def parse_weight(name):
    m = re.search(r"(\d+)\s*g", name)
    return int(m.group(1)) if m else None


def extract_flavor(desc_html):
    # 説明本文の最初の <p><strong>…</strong></p> を店主のキャッチ(風味紹介)として採用
    m = re.search(r"<p>\s*<strong[^>]*>(.+?)</strong>\s*</p>", desc_html or "", re.S)
    if m:
        t = strip_html(m.group(1))
        if t and "おうちで作れる" not in t:
            return t
    # ゲイシャ: カッピング欄
    m = re.search(r"<dt>カッピング</dt>\s*<dd>(.+?)</dd>", desc_html or "", re.S)
    return strip_html(m.group(1)) if m else None


def build_record(p):
    name = (p.get("name") or "").strip()
    cats = {c["name"] for c in p.get("categories", [])}
    if not (cats & BEAN_CATEGORIES):
        return None
    if any(k in name for k in EXCLUDE_KEYWORDS):
        return None
    weight = parse_weight(name)
    if weight is None:
        return None
    desc_html = p.get("description") or ""
    text = strip_html(desc_html)
    m = ROAST_RE.search(text)
    roast_text = m.group(1) if m else ""
    raw_name = f"{name} {roast_text}".strip() if roast_text else name
    parsed = parse_product(raw_name)
    price = int(p["prices"]["price"]) if p.get("prices", {}).get("price") else None
    stock = detect_stock_status(raw_name, not p.get("is_in_stock", True))
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": raw_name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "flavor_notes": extract_flavor(desc_html),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": stock,
        "out_of_stock": stock != "販売中",
        "product_url": p.get("permalink"),
    }


def fetch_all():
    out, page = [], 1
    while True:
        r = requests.get(API_URL, headers=HEADERS, params={"per_page": 100, "page": page}, timeout=20)
        r.raise_for_status()
        b = r.json()
        if not b:
            break
        out.extend(b)
        if len(b) < 100:
            break
        page += 1
    return out


if __name__ == "__main__":
    records = [r for r in (build_record(p) for p in fetch_all()) if r]
    with open("data_shitsuji.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_shitsuji.json に出力しました")
    for r in records:
        print(r["raw_name"], r["category"], r["origin_country"], r["roast_level"], r["price"], r["weight_g"], r["stock_status"], "|", (r["flavor_notes"] or "")[:40])
