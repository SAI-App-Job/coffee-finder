# -*- coding: utf-8 -*-
"""
scrape_agricoffee.py

椏久里珈琲(AgriCoffee、shop.agricoffee.com、福島県福島市東中央3-20-2、
1992年飯舘村創業・東日本大震災の避難指示により福島市へ移転した自家焙煎
スペシャルティコーヒー専門店)の商品情報を取得する。カラーミーショップ
(shop-pro.jp、独自ドメイン、新テーマ"itemList__unit"系クラス)。

【店舗発見の経緯】
全国再調査(福島県)でmamenavi.info「福島の自家焙煎珈琲店ガイド」から発見。

【対象商品について】
実データ確認済み(2026-09時点): 「コーヒー豆」カテゴリ(cbid=1740609)全25件
(2ページ、全25件件数表示で確認)のうち、「水出しコーヒーパック」(通常の
焙煎豆とは形態が異なる)を除いた24銘柄(ストレート17・ブレンド7)を対象と
する。

【商品データの取得元について】
実データ確認済み: カテゴリ一覧ページはli.itemList__unit(p.itemName・
p.itemPrice)で商品名・価格が取得できる。商品詳細ページには自由記述の
商品説明が無く(画像のみのシンプルな構成)、var Colorme JSON内のvariants
(100g/200g/300g×豆/挽き/細挽きの3×3マトリクス)から100g×豆のまま
価格を取得する。在庫はinventory_control="none"でstock_numが常にnullの
ため、商品名のテキストのみで判定する(detect_stock_status)。

robots.txt確認済み(2026-09): shop-pro.jp標準の記述で、User-agent: *は
/secure/と/cart/のみDisallow。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, detect_stock_status

SHOP_INFO = {
    "name": "椏久里珈琲",
    "url": "https://www.agricoffee.com/",
    "platform": "カラーミーショップ(shop-pro.jp、独自ドメイン)",
    "address": "福島県福島市東中央3-20-2",
    "prefecture": "福島県",
    "tel": "024-563-7871",
    "robots_txt_status": "許可(2026-09確認。/secure/と/cart/以外は制限なし)",
}

BASE_URL = "https://shop.agricoffee.com/"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}
CATEGORY_ID = "1740609"
NON_BEAN_KEYWORDS = ["水出しコーヒーパック"]


def fetch_euc(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.encoding = "euc-jp"
    return resp.text


def collect_product_ids() -> list[str]:
    ids = []
    for page in (1, 2):
        url = f"{BASE_URL}?mode=cate&cbid={CATEGORY_ID}&csid=0" + (f"&page={page}" if page > 1 else "")
        html = fetch_euc(url)
        soup = BeautifulSoup(html, "html.parser")
        for li in soup.select("li.itemList__unit"):
            a = li.select_one("a.itemWrap")
            name_el = li.select_one("p.itemName")
            if not a or not name_el:
                continue
            if any(kw in name_el.get_text() for kw in NON_BEAN_KEYWORDS):
                continue
            m = re.search(r"pid=(\d+)", a["href"])
            if m:
                ids.append(m.group(1))
    return ids


def build_record(pid: str) -> dict | None:
    html = fetch_euc(f"{BASE_URL}?pid={pid}")
    m = re.search(r"var\s+Colorme\s*=\s*(\{.*?\});", html, re.DOTALL)
    if not m:
        return None
    colorme = json.loads(m.group(1))
    product = colorme.get("product") or {}
    title = (product.get("name") or "").strip()
    if not title:
        return None

    price = None
    for variant in product.get("variants", []):
        if variant.get("option1_value") == "100ｇ" and variant.get("option2_value") == "豆":
            price = variant.get("option_price_including_tax")
            break
    if price is None:
        price = product.get("sales_price_including_tax")

    parsed = parse_product(title)
    stock_status = detect_stock_status(title)
    sold_out = stock_status != "販売中"

    url = f"{BASE_URL}?pid={pid}"
    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": url,
        }

    if parsed["category"] != "ブレンド":
        detected = detect_country_name(title)
        if detected:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, title)

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
        "flavor_notes": None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": 100,
        "stock_status": stock_status,
        "out_of_stock": sold_out,
        "product_url": url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    records = []
    flavored_records = []
    for pid in collect_product_ids():
        try:
            detail = build_record(pid)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={pid} ({e})")
            continue
        if detail is None:
            continue
        (flavored_records if detail.get("is_flavored") else records).append(detail)
    return records, flavored_records


def main():
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_agricoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_agricoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
