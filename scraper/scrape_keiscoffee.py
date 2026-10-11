# -*- coding: utf-8 -*-
"""
scrape_keiscoffee.py

ケイズコーヒー(keiscoffee.com、熊本県菊池郡菊陽町津久礼165-8)の商品情報を取得する。
自家焙煎のコーヒー豆専門店(業務用卸・ジュートバッグ等の雑貨も扱う)。MakeShop(新形式 /view/item/)。

【店舗発見の経緯】
全国再調査(熊本県)の新規発掘。

【対象商品について】
実データ確認済み(2026-10時点): カテゴリ「コーヒー豆」(ct34、全28件、12件×3ページ)
のうち、「ストレート豆」(ct36、14件)に含まれるものをストレート、「ブレンド豆」(ct37、14件)に
含まれるものをブレンドとして対象とする。カテゴリ「コーヒー(生豆)」・生豆セット・
コーヒー豆チョコ・ドリップバッグ(くまモン、Special、阿蘇産珈琲と完熟カスカラ等)・
インフュージョン(果実等を加える製法)・器具・ジュートバッグ・ティディーベア・帽子等は対象外。

【重量・価格・在庫】
商品ページの注記「数量1は100グラムです」(豆の状態・袋を選択して購入)に従い、
100gの価格(一覧の税込表示)を採用する。在庫は一覧ページの「SOLD OUT」表示で判定する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "ケイズコーヒー",
    "url": "https://www.keiscoffee.com/",
    "platform": "MakeShop",
    "address": "熊本県菊池郡菊陽町津久礼165-8",
    "prefecture": "熊本県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://www.keiscoffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CATEGORY_STRAIGHT = "ct36"
CATEGORY_BLEND = "ct37"
CATEGORY_ALL = "ct34"
# 商品名に国名が無く、商品説明に産地が明記されているもの(商品ID: 国名)
ORIGIN_OVERRIDES = {"000000002011": "ブラジル"}  # オウロベルデ農園(説明文に「Brazil Ouro Verde」と明記)
NON_BEAN_KEYWORDS = ("生豆", "ドリップバッグ", "ドリップバック", "セット", "チョコ", "インフュージョン")


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.content.decode("utf-8", errors="replace")


def parse_category(category_id: str) -> list[dict]:
    items = []
    for page in range(1, 6):
        url = f"{BASE_URL}/view/category/{category_id}" + (f"?page={page}" if page > 1 else "")
        soup = BeautifulSoup(fetch(url), "html.parser")
        cards = soup.select("li.theme-product-card")
        if not cards:
            break
        for li in cards:
            a = li.select_one("h3 a")
            price_el = li.select_one("div.mb-5 p")
            if not a or not price_el:
                continue
            m = re.search(r"/view/item/(\d+)", a["href"])
            pm = re.search(r"([\d,]+)", price_el.get_text())
            if not (m and pm):
                continue
            items.append({
                "id": m.group(1),
                "name": re.sub(r"\s+", " ", a.get_text(strip=True).replace("　", " ")).strip(),
                "price": int(pm.group(1).replace(",", "")),
                "sold_out": "SOLD OUT" in li.get_text(),
            })
    return items


def parse_detail(html_text: str) -> dict:
    soup = BeautifulSoup(html_text, "html.parser")
    text = soup.get_text("\n", strip=True)
    weight_g = None
    m = re.search(r"数量\s*[１1]\s*は\s*([0-9０-９]+)\s*(?:グラム|g|ｇ)", text)
    if m:
        weight_g = int(m.group(1).translate(str.maketrans("０１２３４５６７８９", "0123456789")))
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    desc = None
    if "この商品について問い合わせる" in lines:
        start = lines.index("この商品について問い合わせる") + 1
        desc = re.sub(r"\s+", " ", " ".join(lines[start:start + 6])).strip()[:300] or None
    return {"weight_g": weight_g, "desc": desc}


def build_record(item: dict, is_blend: bool) -> dict | None:
    name = item["name"]
    if any(kw in name for kw in NON_BEAN_KEYWORDS):
        return None
    detail = parse_detail(fetch(f"{BASE_URL}/view/item/{item['id']}"))
    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed["category"] = "ストレート" if parsed["category"] != "フレーバー" else parsed["category"]
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if item["id"] in ORIGIN_OVERRIDES:
            parsed["origin_country"] = ORIGIN_OVERRIDES[item["id"]]
            parsed["origin_source"] = "description"
    sold_out = item["sold_out"]
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
        "roast_hint": None,
        "flavor_notes": detail["desc"],
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": detail["weight_g"],
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/view/item/{item['id']}",
    }


def scrape_all_products() -> list[dict]:
    blend_ids = {i["id"] for i in parse_category(CATEGORY_BLEND)}
    straight_ids = {i["id"] for i in parse_category(CATEGORY_STRAIGHT)}
    records = []
    for item in parse_category(CATEGORY_ALL):
        if item["id"] not in blend_ids and item["id"] not in straight_ids:
            continue
        try:
            rec = build_record(item, item["id"] in blend_ids)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['id']} ({e})")
            continue
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_keiscoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_keiscoffee.json に出力しました")


if __name__ == "__main__":
    main()
