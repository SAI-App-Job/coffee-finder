# -*- coding: utf-8 -*-
"""
scrape_ginzacoffeekanuma.py

銀座コーヒー 自然派カフェ・自家焙煎(https://www.ginzacoffee.net/、栃木県鹿沼市銀座2丁目1869 板屋ビルヂング)の
コーヒー豆の商品情報を取得する。Wix(Wix Stores)。

【ページ構造について】
実データ確認済み(2026-10時点): カテゴリページ「銘柄コーヒー豆」「ブレンドコーヒー」のHTMLに
埋め込まれた商品JSON("urlPart"/"name"/"price")から商品の一覧を作り、各商品ページ
(/product-page/<urlPart>)のJSON-LD(schema.org Product)から説明・価格・在庫を取得する。
銘柄豆は名前の末尾「100g」が販売重量。ブレンド2種は名前に重量がないが、商品ページに
「100gづつ小分けを希望の場合は…」とあり価格は100g単位のため100gとして扱う。
豆/粉の選択オプションがあり、豆のままを選べる。
コーヒー豆定期便(Squareのサブスク)・ふるさと納税・珈琲道具は別カテゴリのため対象外。
"""

import html
import json
import re
import time
from urllib.parse import quote, unquote

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "銀座コーヒー",
    "url": "https://www.ginzacoffee.net/",
    "platform": "Wix(Wix Stores)",
    "address": "栃木県鹿沼市銀座2丁目1869 板屋ビルヂング",
    "prefecture": "栃木県",
    "robots_txt_status": "許可(User-agent: * は Allow: /。識別可能なUser-Agentを使用)",
    "source_note": "公式サイト(https://www.ginzacoffee.net/ )のカテゴリページ「銘柄コーヒー豆」「ブレンドコーヒー」と各商品ページのJSON-LDを"
                   "2026-10-26に確認。100gを代表とし、豆のままの価格。定期便・ふるさと納税・珈琲道具は除外。",
    "last_verified_at": "2026-10-26",
}

BASE_URL = "https://www.ginzacoffee.net"
CATEGORY_URLS = [
    f"{BASE_URL}/category/{quote('銘柄コーヒー豆')}",
    f"{BASE_URL}/category/{quote('ブレンドコーヒー')}",
]
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL = 2.0
LD_PATTERN = re.compile(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
CATEGORY_PRODUCT_PATTERN = re.compile(r'"urlPart":"([^"]+)"[^{}]*?"name":"([^"]+)"')
ROAST_PATTERN = re.compile(r"(?:焙煎度の目安は|焙煎度目安|焙煎度合い?|焙煎)[：:\s]*(極深煎り|中深煎り|浅煎り|中煎り|深煎り)")
EXCLUDE_KEYWORDS = ("セット", "ドリップバッグ", "定期", "ギフト")


def get(url: str) -> str:
    r = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    r.raise_for_status()
    r.encoding = "utf-8"
    return r.text


def list_products() -> list[str]:
    """カテゴリページ内の商品JSONから urlPart を重複なく集める(商品カテゴリ内の並び順)。"""
    slugs = []
    for n, url in enumerate(CATEGORY_URLS):
        if n:
            time.sleep(REQUEST_INTERVAL)
        page = get(url)
        for m in CATEGORY_PRODUCT_PATTERN.finditer(page):
            slug = m.group(1)
            if slug not in slugs:
                slugs.append(slug)
    return slugs


def parse_page(slug: str) -> dict | None:
    url = f"{BASE_URL}/product-page/{quote(slug)}"
    page = get(url)
    for m in LD_PATTERN.finditer(page):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if data.get("@type") == "Product" and data.get("offers"):
            offers = data["offers"]
            if isinstance(offers, list):
                offers = offers[0]
            return {
                "url": f"{BASE_URL}/product-page/{slug}",
                "name": re.sub(r"\s+", " ", data["name"].replace("　", " ")).strip(),
                "desc": data.get("description") or "",
                "price": int(float(offers["price"])),
                "in_stock": "InStock" in (offers.get("availability") or ""),
            }
    return None


def build_record(p: dict) -> dict | None:
    name = p["name"]
    if any(w in name for w in EXCLUDE_KEYWORDS):
        return None
    wm = re.search(r"(\d+)\s*g\s*$", name)
    weight = int(wm.group(1)) if wm else 100  # ブレンドは100g単位の価格(商品ページの注記による)
    name = re.sub(r"\s*\d+\s*g\s*$", "", name).strip()

    is_blend = "ブレンド" in name
    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
    # 名前の焙煎度表記と商品ページの「焙煎度目安」が食い違う商品(ラオス)があるため、説明文の記載を優先する。
    # デカフェは焙煎度を購入時に選択するため説明文に固定値がなく、名前からも判定しない。
    rm = ROAST_PATTERN.search(p["desc"])
    if rm:
        roast = rm.group(1)
    elif "デカフェ" in name:
        roast = None
    else:
        roast = parsed["roast_level"]
    desc = re.sub(r"\s+", " ", p["desc"]).strip()[:400] or None
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast,
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": p["price"],
        "weight_g": weight,
        "stock_status": "販売中" if p["in_stock"] else "完売",
        "out_of_stock": not p["in_stock"],
        "product_url": p["url"],
    }


def scrape_all_products() -> list[dict]:
    records = []
    for slug in list_products():
        time.sleep(REQUEST_INTERVAL)
        try:
            p = parse_page(slug)
        except requests.RequestException as e:
            print(f"[warn] 取得失敗: {slug} ({e})")
            continue
        if not p:
            print(f"[warn] 解析できず: {slug}")
            continue
        rec = build_record(p)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    if not records:
        print("[warn] 0件のためファイルを作成しません")
        return
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_ginzacoffeekanuma.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_ginzacoffeekanuma.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], r["category"], r["origin_country"], r["roast_level"], r["price"], r["weight_g"], r["stock_status"])


if __name__ == "__main__":
    main()
