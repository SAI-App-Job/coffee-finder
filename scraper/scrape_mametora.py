# -*- coding: utf-8 -*-
"""
scrape_mametora.py

豆虎(注文焙煎豆虎、https://www.mametora.jp/shop/、東京都港区赤坂3-6-18 赤坂焙煎所ほか都内6焙煎所)の
コーヒー豆の商品情報を取得する。Welcart(WordPress)。

【店舗・自家焙煎の確認(2026-10-21)】
https://www.mametora.jp/concept に「本格的なガス火の焙煎機を使用し、オーダー毎に生豆を焙煎する」、
https://www.mametora.jp/shopinfo に赤坂・中目黒・青山・富ヶ谷・神保町・自由が丘の6焙煎所(11店舗未満)。
住所は番地まで確認できた赤坂焙煎所(港区赤坂3-6-18 赤坂ニューロイヤルビル101、サイト代表電話
03-6435-5353と一致する本店格)を採用。神保町焙煎所は「神田神保町1-4」までしか確認できない。

【対象商品について】
カテゴリ「コーヒー豆」(shop/category/item/coffee/、27件)から、フレーバーコーヒーの「ウヰスキーコーヒー」を
除く26件。一覧の価格は「¥ x / 100g」の100gあたり単価(税込)。焙煎度は購入時に6段階から選択する方式で
商品別の固定値はなく、roastは設定しない。粉は購入時の挽き方選択で、価格は同一。在庫は商品ページの
「在庫状態」(在庫有り/売り切れ)で判定する。ドリップバッグ・ギフト・グッズは別カテゴリのため対象外。

【robots.txtについて】
User-agent: * で /mametora/wp-admin/ のみ Disallow。識別可能な独自User-Agentで1.5秒以上の間隔を空けて取得する。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "豆虎",
    "url": "https://www.mametora.jp/shop/",
    "platform": "Welcart(WordPress)",
    "address": "東京都港区赤坂3-6-18 赤坂ニューロイヤルビル101",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(User-agent: * は /mametora/wp-admin/ のみDisallow。識別可能なUser-Agentを使用)",
    "source_note": "オンラインショップ https://www.mametora.jp/shop/category/item/coffee/ と各商品ページを2026-10-21に確認。https://www.mametora.jp/concept に「ガス火の焙煎機を使用し、オーダー毎に生豆を焙煎」、"
                   "https://www.mametora.jp/shopinfo に6焙煎所(赤坂・中目黒・青山・富ヶ谷・神保町・自由が丘)。住所は番地まで確認できた赤坂焙煎所を採用(神保町は『神田神保町1-4』までしか確認できず)。"
                   "価格は100gあたり単価(税込)。焙煎度・挽き方は購入時に選択。フレーバーコーヒーのウヰスキーコーヒーは除外。お知らせの最新は2025-12。",
    "last_verified_at": "2026-10-21",
}

LIST_URL = "https://www.mametora.jp/shop/category/item/coffee/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL = 2
EXCLUDE_KEYWORDS = ["ウヰスキー", "ウイスキー", "ドリップバッグ", "ギフト", "セット"]


def fetch(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("　", " ")).strip()


def list_items() -> list[dict]:
    soup = fetch(LIST_URL)
    items, seen = [], set()
    for box in soup.select("div.item-info"):
        a = box.select_one("div.detail-btn a")
        name_el = box.select_one(".item-name")
        price_el = box.select_one(".itemprice span")
        if not (a and name_el and price_el):
            continue
        url = a["href"]
        name = norm(name_el.get_text(" ", strip=True))
        if url in seen or any(k in name for k in EXCLUDE_KEYWORDS):
            continue
        m = re.search(r"([\d,]+)", price_el.get_text())
        orijin = box.select_one(".orijin-name")
        p = box.select_one(".spec p")
        seen.add(url)
        items.append({
            "url": url,
            "name": name,
            "price": int(m.group(1).replace(",", "")) if m else None,
            "orijin": norm(orijin.get_text()) if orijin else "",
            "desc": norm(p.get_text(" ", strip=True)) if p else None,
        })
    return items


def build_record(it: dict) -> dict:
    soup = fetch(it["url"])
    text = soup.get_text("\n", strip=True)
    m = re.search(r"在庫状態：\s*(?:[^\n]*\n)?(在庫有り|売り切れ)", text)
    sold_out = bool(m) and m.group(1) == "売り切れ"
    name = it["name"]
    orijin = it["orijin"]
    is_blend = "ブレンド" in orijin or "ブレンド" in name

    parsed = parse_product(name)
    origin = None
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"], parsed["origin_source"] = None, None
    else:
        if "ハワイ" in name:
            origin = "アメリカ(ハワイ)"
        elif "ブルーマウンテン" in name:
            origin = "ジャマイカ"
        else:
            origin = re.sub(r"産$", "", orijin) or None
        if origin:
            parsed["origin_country"] = origin
            parsed["origin_source"] = "product_description"
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
        "roast_level": None,  # 焙煎度は購入時に選択
        "roast_hint": None,
        "flavor_notes": it["desc"],
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": it["price"],
        "weight_g": 100,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": it["url"],
    }


def scrape_all_products() -> list[dict]:
    records = []
    for it in list_items():
        time.sleep(REQUEST_INTERVAL)
        try:
            records.append(build_record(it))
        except requests.RequestException as e:
            print(f"[warn] 詳細取得失敗: {it['url']} ({e})")
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_mametora.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mametora.json に出力しました")


if __name__ == "__main__":
    main()
