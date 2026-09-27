# -*- coding: utf-8 -*-
"""
scrape_vendedor.py

珈房ベンデドール(946jp.com/vendedor、北海道釧路郡釧路町、自家焙煎豆の
オンライン販売)の商品情報を取得する。独自CGI注文フォーム。

【店舗発見の経緯】
全国再調査(北海道)で再発見。2026-09-16の北海道エリア調査では「珈屋Lamp・
B.BROWN・珈琲豆工房ムク・珈房ベンデドール」等12店舗をまとめて
「オンライン販売用のカートが存在せず」という理由で見送っていたが、
実際には注文フォームページ(quickorder.cgi)に全13商品の産地・価格が
明記されていることを確認できたため、この店舗のみ見送りを撤回し実装
対象に追加する(他11店舗は前回調査時点の確認結果を維持)。

【対象商品について】
実データ確認済み(quickorder.cgi、2026-09時点): 全13商品(ストレート9・
ブレンド3・カフェインレス1)を対象とする。非対象商品なし。「フレンチ」は
商品名自体には産地の言及が無いが、本文に「グァテマラを深く焙煎しました」
と明記されているためグァテマラのストレートとして扱う。

【商品説明の構造について】
実データ確認済み: 1枚の静的HTMLページに`<div class="prdt">`という商品
ブロックが連続し、`<div class="prdt_ttl">`(商品名)・直後の`<p>`(テイスティング
文、定型のアイコン説明文言を含まない)・「100g N 円」という価格表記が
続く。個別の商品ページURLが存在しないため、`product_url`は一覧ページの
URLに、注文フォームの`<select name="...">`属性値(商品ごとに一意な
実在のフォーム部品名、例:SPOT_COFFEE_3)をアンカーとして付けて一意にする
(aggregate_shops.py側はproduct_urlの一意性を前提にIDを構築するため)。
"""

import re

import requests

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    detect_stock_status,
    detect_country_name,
)

SHOP_INFO = {
    "name": "珈房ベンデドール",
    "url": "https://www.946jp.com/vendedor/",
    "platform": "独自EC(CGI注文フォーム)",
    "address": "北海道釧路郡釧路町曙2丁目9-13",
    "prefecture": "北海道",
    "robots_txt_status": "未確認(独自CGI構成)",
}

LIST_URL = "https://www.946jp.com/vendedor/quickorder.cgi"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}

PRODUCT_BLOCK_PATTERN = re.compile(
    r'<div class="prdt_ttl">(?P<title>[^<]+)</div>\s*<p>\s*(?P<desc>.*?)\s*</p>.*?'
    r'100g\s*<span class="price">(?P<price>[\d,]+)</span>\s*円.*?'
    r'<select name="(?P<code>[^"]+)"',
    re.DOTALL,
)
ICON_LINE_PATTERN = re.compile(r'<span class="icn[^"]*">[^<]*</span>')


def fetch_products() -> list[dict]:
    resp = requests.get(LIST_URL, headers=REQUEST_HEADERS, timeout=20)
    resp.encoding = "utf-8"
    html = resp.text

    records = []
    for m in PRODUCT_BLOCK_PATTERN.finditer(html):
        title = m.group("title").strip()
        desc_html = ICON_LINE_PATTERN.sub("", m.group("desc"))
        desc = re.sub(r"<br\s*/?>", "\n", desc_html)
        desc = re.sub(r"<[^>]+>", "", desc).strip()
        # 30kg限定商品の在庫カウンター行(30ｋg限定商品！→9 kg (更新日時))は
        # 商品固有のテイスティング情報ではないため除去する
        desc = re.sub(r"\d+[kｋ]g限定商品！.*", "", desc).strip()
        price = int(m.group("price").replace(",", ""))
        records.append({"title": title, "desc": desc, "price": price, "code": m.group("code")})
    return records


def build_record(raw: dict) -> dict:
    title = raw["title"]
    flavor_notes = raw["desc"] or None
    url = f"{LIST_URL}#{raw['code']}"

    parsed = parse_product(title)
    detected = (
        detect_country_name(title)
        or (flavor_notes and detect_country_name(flavor_notes))
    )
    if detected:
        parsed["origin_country"] = detected
        parsed["origin_source"] = "raw_name" if detect_country_name(title) else "product_description"
    parsed = apply_category_hint_fallback(parsed, title)

    stock_status = detect_stock_status(title)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "flavor_notes": flavor_notes,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": raw["price"],
        "weight_g": 100,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    records = []
    flavored_records = []
    for raw in fetch_products():
        detail = build_record(raw)
        if parse_product(raw["title"])["is_flavored"]:
            flavored_records.append(detail)
        else:
            records.append(detail)
    return records, flavored_records


def main():
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_vendedor.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_vendedor.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
