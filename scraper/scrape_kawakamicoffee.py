# -*- coding: utf-8 -*-
"""
scrape_kawakamicoffee.py

kawakami coffee roaster(大阪府箕面市船場東1-8-58 1F、kawakamicoffee.com)のオンラインストアの
コーヒー豆情報を取得する。WordPress + WooCommerce系テーマ(ec011)。Store API は無効のため、
商品一覧(/products/blend/・/products/single/)から商品IDを集め、各商品ページの
data-product_variations(JSON)から重量バリエーションの最小重量(200g)の価格・在庫を採用する。

【対象】ブレンド・シングルオリジンの豆のみ。カテゴリ「その他」(ドリップバッグ・カフェラテベース・
リキッドアイスコーヒー等)は除外。「種類」(豆のまま/挽き目)は豆のままを代表(価格は同一)。
robots.txt は /wp-admin/ のみ禁止(取得対象外)。リクエスト間隔は2秒。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product

SHOP_INFO = {
    "name": "kawakami coffee roaster",
    "url": "https://www.kawakamicoffee.com/",
    "platform": "WordPress + WooCommerce(ec011)",
    "address": "大阪府箕面市船場東1-8-58 1F",
    "prefecture": "大阪府",
    "robots_txt_status": "取得可(/wp-admin/ のみDisallow)",
    "source_note": "公式 https://www.kawakamicoffee.com/ ・特商法 /terms/ ・商品一覧 /products/blend/ /products/single/ を2026-10-26に確認。季節限定『秋ブレンド2026』掲載あり(更新は新しい)。特商法に営業時間11:00〜17:00『間借り営業・水曜日、木曜日』とあり、箕面は間借り店舗(2026-07-04のお知らせで兵庫県芦屋市に新店舗開業予定、箕面の間借りは継続予定)。",
    "last_verified_at": "2026-10-26",
}

BASE = "https://www.kawakamicoffee.com"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
LIST_PAGES = [("blend", "ブレンド"), ("single", "ストレート")]
ROAST_PATTERN = re.compile(r"(極深煎り|中深煎り|中浅煎り|浅煎り|中煎り|深煎り)")
INTERVAL = 2.0


def get(url: str) -> str:
    time.sleep(INTERVAL)
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def collect_ids() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for slug, cat in LIST_PAGES:
        text = get(f"{BASE}/products/{slug}/")
        for pid in re.findall(r"/product/(\d+)/", text):
            if all(pid != p for p, _ in found):
                found.append((pid, cat))
    return found


def to_weight(s: str | None) -> int | None:
    if not s:
        return None
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*(kg|g)", s, re.I)
    if not m:
        return None
    v = float(m.group(1))
    return int(v * 1000) if m.group(2).lower() == "kg" else int(v)


def build_record(pid: str, cat: str) -> dict | None:
    url = f"{BASE}/product/{pid}/"
    soup = BeautifulSoup(get(url), "html.parser")
    name = re.sub(r"\s+", " ", soup.find("h1").get_text(" ", strip=True).replace("　", " "))
    form = soup.find("form", class_="variations_form")
    if not form or not form.get("data-product_variations"):
        return None
    variations = json.loads(form["data-product_variations"])
    cands = []
    for v in variations:
        w = to_weight(v["attributes"].get("attribute_pa_youryou"))
        syu = v["attributes"].get("attribute_pa_syu") or ""
        if w is None:
            continue
        # 種類が指定されるバリエーションがある場合は豆のまま(空=任意も可)のみ
        if syu and "%e8%b1%86%e3%81%ae%e3%81%be%e3%81%be" != syu and syu != "豆のまま":
            continue
        cands.append((w, v))
    if not cands:
        return None
    w, v = min(cands, key=lambda x: x[0])
    desc_parts = []
    desc_h = soup.find(string=re.compile("商品説明"))
    if desc_h:
        box = desc_h.find_parent().find_next_sibling()
        if box:
            desc_parts.append(box.get_text(" ", strip=True))
    desc = re.sub(r"\s+", " ", " ".join(desc_parts)).strip()
    parsed = parse_product(name)
    rm = ROAST_PATTERN.search(name)
    if cat == "ブレンド":
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    in_stock = bool(v.get("is_in_stock"))
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": rm.group(1) if rm else None,
        "roast_hint": None,
        "flavor_notes": desc[:300] or None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(v["display_price"]) if v.get("display_price") is not None else None,
        "weight_g": w,
        "stock_status": "販売中" if in_stock else "完売",
        "out_of_stock": not in_stock,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for pid, cat in collect_ids():
        rec = build_record(pid, cat)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    with open("data_kawakamicoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kawakamicoffee.json に出力しました")


if __name__ == "__main__":
    main()
