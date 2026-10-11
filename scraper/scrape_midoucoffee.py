# -*- coding: utf-8 -*-
"""
scrape_midoucoffee.py

御堂珈琲店(運営:岩田焙煎珈琲/御堂オーチャード、midoucoffee.shop、熊本県熊本市中央区黒髪6-12-26)の
商品情報を取得する。カラーミーショップ(shop-pro.jp、独自ドメイン、EUC-JP)。
注文を受けてから焙煎する「注文焙煎」スタイルのスペシャルティコーヒー専門店。

【店舗発見の経緯】
全国再調査(熊本県)の新規発掘。2026年に横浜から熊本へ移転した旨がサイト上で案内されている。

【対象商品について】
実データ確認済み(2026-10時点): カテゴリ「【通常サイズ】注文焙煎 珈琲豆/挽豆
(230g生豆/焙煎後192-195g)」(cbid=2859799、2ページ、全23件)を対象とする。
ハーフサイズ(115g生豆/焙煎後90-95g)、ワンドリップ、アイスコーヒー、おまかせ珈琲セット、
ギフト、グッズ、液糖は対象外。通常サイズの価格と、重量は表記「焙煎後192-195g」から195gを採用。
焙煎度・挽き方は購入時にお客様が選ぶオプション(生豆を除く)のため、商品固有の焙煎度はNone。
価格は商品ページの表示価格(税込)。在庫は一覧の「SOLD OUT」表示で判定する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "御堂珈琲店",
    "url": "https://midoucoffee.shop/",
    "platform": "カラーミーショップ(shop-pro.jp、独自ドメイン)",
    "address": "熊本県熊本市中央区黒髪6-12-26",
    "prefecture": "熊本県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://midoucoffee.shop/"
CATEGORY_ID = "2859799"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}
WEIGHT_G = 195
NON_BEAN_KEYWORDS = ("セット", "ドリップバッグ", "ギフト")


def fetch_euc(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "euc-jp"
    return resp.text


def clean_name(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("　", " ")).strip()


def collect_items() -> list[dict]:
    items, seen = [], set()
    for page in (1, 2, 3):
        url = f"{BASE_URL}?mode=cate&cbid={CATEGORY_ID}&csid=0" + (f"&page={page}" if page > 1 else "")
        soup = BeautifulSoup(fetch_euc(url), "html.parser")
        lis = soup.select("li.c-item-list__item")
        if not lis:
            break
        for li in lis:
            a = li.select_one("div.c-item-list__ttl a")
            if not a:
                continue
            m = re.search(r"pid=(\d+)", a["href"])
            if not m or m.group(1) in seen:
                continue
            seen.add(m.group(1))
            for br in a.find_all("p"):
                br.insert_before(" ")
            name = clean_name(a.get_text(" ", strip=True))
            items.append({
                "id": m.group(1),
                "name": name,
                "sold_out": li.select_one("div.is-soldout") is not None,
            })
    return items


def parse_detail(html_text: str) -> dict:
    m = re.search(r"var\s+Colorme\s*=\s*(\{.*?\});", html_text, re.DOTALL)
    price = None
    if m:
        product = json.loads(m.group(1)).get("product") or {}
        price = product.get("sales_price_including_tax")
    soup = BeautifulSoup(html_text, "html.parser")
    lines = [ln.strip() for ln in soup.get_text("\n", strip=True).split("\n") if ln.strip()]
    desc = None
    if "DETAIL" in lines:
        start = lines.index("DETAIL") + 1
        end = next((i for i in range(start, len(lines)) if lines[i] == "RECOMMENDED ITEM"), len(lines))
        desc = re.sub(r"\s+", " ", " ".join(lines[start:end])).strip()[:300] or None
    return {"price": price, "desc": desc}


def build_record(item: dict) -> dict | None:
    name = item["name"]
    if any(kw in name for kw in NON_BEAN_KEYWORDS):
        return None
    detail = parse_detail(fetch_euc(f"{BASE_URL}?pid={item['id']}"))
    parsed = parse_product(name)
    if "ブレンド" in name or "Blend" in name or "クリスタル・ナハト" in name:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
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
        "price": detail["price"],
        "weight_g": WEIGHT_G,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}?pid={item['id']}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in collect_items():
        try:
            rec = build_record(item)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={item['id']} ({e})")
            continue
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_midoucoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_midoucoffee.json に出力しました")


if __name__ == "__main__":
    main()
