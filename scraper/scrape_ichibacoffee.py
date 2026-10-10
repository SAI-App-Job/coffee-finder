# -*- coding: utf-8 -*-
"""
scrape_ichibacoffee.py

市場珈琲焙煎所(ichiba-coffee.com、新潟県新潟市江南区茗荷谷711番地 新潟市中央卸売市場
中央棟1F)の商品情報を取得する。Wix Stores(store-products-sitemap.xml + JSON-LD)。

【対象商品】名称が「(1袋 NNNg)」の1袋商品のみ: 国別豆6種(ブラジル・コロンビア・
エチオピア・グアテマラ・タンザニア・インドネシア)とブレンド3種(ICHIBA BLEND、
あがり珈琲、ICE BLEND)、いずれも100g 1,000円。除外: 「ROAST LEVEL ... 100g×2袋セット」
「セット」「焙煎豆GIFT」「サブスク(sub-*)」「ドリップ(sub-drip-20)」。
焙煎度は国別豆1袋商品では選択肢・記載とも無いためnull。ICHIBA BLEND / あがり珈琲は
説明文の「中煎りブレンド」を採用。

robots.txt確認済み(2026-10): User-agent: *はAllow: /(lightboxクエリ除外)、PetalBotのみ全面Disallow。
"""

import html
import json
import re

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "市場珈琲焙煎所",
    "url": "https://www.ichiba-coffee.com/",
    "platform": "Wix Stores",
    "address": "新潟県新潟市江南区茗荷谷711番地 新潟市中央卸売市場 中央棟1F",
    "prefecture": "新潟県",
    "robots_txt_status": "許可(2026-10確認。User-agent: *にAllow: /[lightboxクエリのみ除外]。PetalBotのみ全面Disallow)",
}

BASE_URL = "https://www.ichiba-coffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
JSONLD_PATTERN = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL)
SINGLE_BAG_PATTERN = re.compile(r"\(\s*1袋\s*(\d+)\s*g\s*\)")
EXCLUDE_KEYWORDS = ["セット", "GIFT", "ギフト", "定期", "ドリップ"]
BLEND_NAMES = ["あがり珈琲"]


def fetch_product_urls() -> list[str]:
    resp = requests.get(f"{BASE_URL}/store-products-sitemap.xml", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    return re.findall(r"<loc>([^<]+)</loc>", resp.text)


def extract_product_jsonld(text: str) -> dict | None:
    for m in JSONLD_PATTERN.finditer(text):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == "Product":
            return data
    return None


def build_record(url: str, data: dict) -> dict | None:
    title = html.unescape((data.get("name") or "")).strip()
    wm = SINGLE_BAG_PATTERN.search(title)
    if not wm or any(k in title for k in EXCLUDE_KEYWORDS):
        return None
    weight = int(wm.group(1))
    name = SINGLE_BAG_PATTERN.sub("", title).strip()

    offers = data.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    price = int(float(offers["price"])) if offers.get("price") is not None else None
    availability = (offers.get("availability") or "").rstrip("/").split("/")[-1]
    out = availability not in ("InStock", "")

    desc_raw = html.unescape(data.get("description") or "").replace("\xa0", " ")
    lines = [l.strip() for l in desc_raw.split("\n") if l.strip()]
    lines = [l for l in lines if not l.startswith("#") and l != title]
    desc = " ".join(lines)[:400] or None

    parsed = parse_product(name)
    is_blend = "BLEND" in name.upper() or "ブレンド" in name or name in BLEND_NAMES
    roast = None
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        if desc and "中煎りブレンド" in desc:
            roast = "中煎り"
    else:
        c = detect_country_name(name)
        if c and not parsed["origin_country"]:
            parsed["origin_country"] = c
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "完売" if out else "販売中",
        "out_of_stock": out,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for url in fetch_product_urls():
        try:
            resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {url} ({e})")
            continue
        data = extract_product_jsonld(resp.content.decode("utf-8", "replace"))
        if not data:
            continue
        rec = build_record(url, data)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    with open("data_ichibacoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_ichibacoffee.json に出力しました")


if __name__ == "__main__":
    main()
