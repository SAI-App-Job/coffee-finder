# -*- coding: utf-8 -*-
"""
scrape_gooddayscoffee.py

GOOD DAYS COFFEE(gdayscoffee.thebase.in、岐阜県多治見市太平町4-50 グリュックリヒ・ファミーリエ1F D)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(岐阜県)の新規発掘で発見。

【住所について】
実データ確認済み(2026-10時点): /law(特定商取引法に基づく表記)の事業者の所在地は
「〒507-0041 岐阜県多治見市太平町4-50 グリュックリヒ・ファミーリエ1F D(事業者: 古谷嘉威)」。

【対象商品について】
実データ確認済み(2026-10時点): sitemap.xmlの商品URL9件を取得し、自家焙煎の200g豆(ストレート6種・ブレンド2種の計8種)を対象とする。ステッカー(グッズ)は
除外。商品名は「自家焙煎」「焙煎度」「重量」の表記を除いた銘柄部分を名称とし、焙煎度は商品名の
「浅煎り/中煎り/深煎り」から取得する。説明文(og:description)をflavor_notesに使う。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import html
import json
import re
import unicodedata

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "GOOD DAYS COFFEE",
    "url": "https://gdayscoffee.thebase.in/",
    "platform": "BASE",
    "address": "岐阜県多治見市太平町4-50 グリュックリヒ・ファミーリエ1F D",
    "prefecture": "岐阜県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://gdayscoffee.thebase.in"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

TITLE_PATTERN = re.compile(r'<meta property="og:title" content="([^"]*)"')
DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
ROAST_WORDS = "中浅煎り|中深煎り|浅煎り|中煎り|深煎り"
ROAST_LABELED = re.compile(r"焙煎度[:：]\s*(" + ROAST_WORDS + ")")
ROAST_ANY = re.compile("(" + ROAST_WORDS + ")")


def detect_roast(*texts: str) -> str | None:
    """「焙煎度：中煎り」の明示を優先。なければ文中に出る焙煎度表記が1種類のときのみ採用する。"""
    for t in texts:
        m = ROAST_LABELED.search(t or "")
        if m:
            return m.group(1)
    found = {m.group(1) for t in texts for m in ROAST_ANY.finditer(t or "")}
    return found.pop() if len(found) == 1 else None


EXCLUDE_KEYWORDS = ["STICKER", "ステッカー"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")


def prepare(title: str, desc: str) -> dict | None:
    norm = unicodedata.normalize("NFKC", title)
    if any(kw.lower() in norm.lower() for kw in EXCLUDE_KEYWORDS):
        return None
    m = WEIGHT_PATTERN.search(norm)
    if not m:
        return None
    name = WEIGHT_PATTERN.sub("", norm).replace("自家焙煎", "")
    roast = detect_roast(name)
    name = ROAST_ANY.sub("", name)
    name = re.sub(r"\s+", " ", name).strip().replace("No,", "No.")
    return {
        "name": name,
        "weight_g": int(m.group(1)),
        "roast_level": roast,
        "flavor_notes": desc[:400],
    }


def fetch_text(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def fetch_item_urls() -> list[str]:
    sitemap = fetch_text(f"{BASE_URL}/sitemap.xml")
    return re.findall(r"<loc>([^<]*/items/\d+)</loc>", sitemap)


def build_record(item_url: str) -> dict | None:
    page = fetch_text(item_url)
    title_m = TITLE_PATTERN.search(page)
    if not title_m:
        return None
    title = html.unescape(title_m.group(1)).split(" | ")[0].strip()
    desc_m = DESC_PATTERN.search(page)
    desc = re.sub(r"\s+", " ", html.unescape(desc_m.group(1))).strip() if desc_m else ""
    price_m = PRICE_PATTERN.search(page)
    purchasability_m = PURCHASABILITY_PATTERN.search(page)
    sold_out = bool(purchasability_m) and purchasability_m.group(1) == "unpurchasable"

    prepared = prepare(title, desc)
    if prepared is None:
        return None
    name = prepared["name"]

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if prepared.get("category"):
        parsed["category"] = prepared["category"]
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["grade"] = None  # 「No.1」等はブレンドの通し番号でありグレードではない
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
        "processing_method": prepared.get("processing_method") or parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": prepared.get("roast_level"),
        "roast_hint": None,
        "flavor_notes": prepared.get("flavor_notes") or None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [
            {"origin_country": c, "percentage": None} for c in prepared.get("blend_components", [])
        ],
        "price": int(price_m.group(1)) if price_m else None,
        "weight_g": prepared["weight_g"],
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": item_url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item_url in fetch_item_urls():
        try:
            record = build_record(item_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item_url} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_gooddayscoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_gooddayscoffee.json に出力しました")


if __name__ == "__main__":
    main()
