# -*- coding: utf-8 -*-
"""
scrape_hatacoffee.py

はた珈琲店(hata-coffee.com/onlineshop/、株式会社ハタ、〒650-0022 兵庫県神戸市中央区元町通5丁目7-12、
自家焙煎の深煎り珈琲)の商品情報を取得する。Welcart(WordPress)。

【店舗・自家焙煎の確認(2026-10)】
特定商取引法表示ページに「株式会社ハタ 兵庫県神戸市中央区元町通5丁目7-12」、ご挨拶ページに
「自家焙煎の深煎り珈琲一杯点ての伝統を守り」と記載。

【対象商品について】
実データ確認済み(2026-10時点): カテゴリ「オリジナルブレンド」(itemgenre/original_blend、9件)と
「ストレート豆」(itemgenre/straight、7件)の計16件(全て「<銘柄>(<味わい語>) 100g <価格>円」)。
ドリップバッグ、ギフトセット、定期購入(10回コース、300g〜)は除外。
全商品100g単位で、300g以上は10%OFFの割引案内のみ(別商品ではない)。価格は商品ページの
税込表示、在庫は「在庫状態」表示(在庫有り/在庫切れ)で判定する。
詳細ページに産地・焙煎度・精製の構造化情報は無く、短い味わい説明のみ(焙煎度は店全体が深煎り方針だが
商品別の記載が無いため未設定)。産地は商品名から判定する(「モカ」は説明文に「エチオピア」と明記)。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "はた珈琲店",
    "url": "https://hata-coffee.com/onlineshop/",
    "platform": "Welcart(WordPress)",
    "address": "兵庫県神戸市中央区元町通5-7-12",
    "prefecture": "兵庫県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://hata-coffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
# (カテゴリslug, ブレンドか)
CATEGORIES = [("original_blend", True), ("straight", False)]
TITLE_PATTERN = re.compile(r"^(.+?)\s*(\d+)\s*g\s*([\d,]+)\s*円$")
EXCLUDE_KEYWORDS = ["ドリップバッグ", "ギフト", "セット", "定期購入"]


def fetch(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s)).strip()


def list_items() -> list[dict]:
    items, seen = [], set()
    for slug, is_blend in CATEGORIES:
        soup = fetch(f"{BASE_URL}/onlineshop/category/item/itemgenre/{slug}")
        for a in soup.select('a[href*="/onlineshop/item/"]'):
            href = a["href"]
            text = norm(a.get_text(" ", strip=True))
            if href in seen or not text:
                continue
            m = TITLE_PATTERN.match(text)
            if not m or any(k in text for k in EXCLUDE_KEYWORDS):
                continue
            seen.add(href)
            items.append({"url": href, "name": m.group(1).strip(), "weight": int(m.group(2)),
                          "list_price": int(m.group(3).replace(",", "")), "is_blend": is_blend})
        time.sleep(0.5)
    return items


def build_record(it: dict) -> dict:
    soup = fetch(it["url"])
    html_text = str(soup)
    zaiko = soup.select_one(".zaikostatus")
    zaiko_text = norm(zaiko.get_text()) if zaiko else ""
    sold_out = bool(zaiko_text) and "在庫有り" not in zaiko_text
    # 一覧・商品名の「100g 1000円」が税込の通常価格(商品ページ内の「300g以上で100gあたり¥900」は割引案内)
    price = it["list_price"]
    # 商品名行の直後〜「300g以上ご購入で」より前が味わい説明
    text_lines = [norm(l) for l in soup.get_text("\n", strip=True).split("\n")]
    text_lines = [l for l in text_lines if l]
    desc = None
    for i, ln in enumerate(text_lines):
        if re.fullmatch(r"\([a-z0-9_]+\)", ln):
            body = []
            for nxt in text_lines[i + 1:]:
                if nxt.startswith("300g以上"):
                    break
                body.append(nxt)
            desc = " ".join(body)[:300] or None
            break

    name = it["name"]
    parsed = parse_product(name)
    if it["is_blend"]:
        parsed["category"] = "ブレンド"
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"], parsed["origin_source"] = detected, "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if desc:
            # 「モカ」は説明文に産地がエチオピアと明記されている
            from_desc = detect_country_name(desc)
            if from_desc and "モカ" in name and from_desc == "エチオピア":
                parsed["origin_country"], parsed["origin_source"] = from_desc, "product_description"
            elif not parsed["origin_country"] and from_desc:
                parsed["origin_country"], parsed["origin_source"] = from_desc, "product_description"
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": None,  # 商品名の「ハイカラ」が焙煎度「ハイ」に誤マッチするため使わない(焙煎度の記載は無い)
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": it["weight"],
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": it["url"],
    }


def scrape_all_products() -> list[dict]:
    records = []
    for it in list_items():
        try:
            records.append(build_record(it))
        except requests.RequestException as e:
            print(f"[warn] 詳細取得失敗: {it['url']} ({e})")
        time.sleep(0.5)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_hatacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_hatacoffee.json に出力しました")


if __name__ == "__main__":
    main()
