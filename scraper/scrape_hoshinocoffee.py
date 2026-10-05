# -*- coding: utf-8 -*-
"""
scrape_hoshinocoffee.py

ほしの珈琲(hoshino-coffee.shop-pro.jp、愛知県豊橋市柱六番町116)の商品情報を取得する。
カラーミーショップ(文字コードEUC-JP)。

【対象商品について】
実データ確認済み(2026-10時点): カテゴリ「ブレンドコーヒー」(cbid=2926445、6件)と
「ストレートコーヒー」(cbid=2926446、6件)の計12件、全て500g袋(商品名末尾の【500g】)。
他の重量・ドリップバッグ等は存在しない。挽き方(豆のまま/粉に挽く)の選択肢があるが
価格は同額。ブレンドは名称が「ほしのブレンド」等の自家ブレンド、ストレートは
「ブラジル [シティーロースト]」のように焙煎度が角括弧で付く。

【在庫について】
商品ページのColorme JSONの商品レベルstock_numが0の商品は「SOLD OUT」表示(キリマンジャロ2件)。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "ほしの珈琲",
    "url": "https://hoshino-coffee.shop-pro.jp/",
    "platform": "カラーミーショップ",
    "address": "愛知県豊橋市柱六番町116",
    "prefecture": "愛知県",
    "robots_txt_status": "未確認(カラーミー標準構成)",
}

BASE_URL = "https://hoshino-coffee.shop-pro.jp"
CATEGORIES = [("2926445", "blend"), ("2926446", "single")]
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
MAX_PAGES = 10

WEIGHT_PATTERN = re.compile(r"【\s*(\d+)\s*[gｇ]\s*】")
BRACKET_ROAST_PATTERN = re.compile(r"\[([^\]]*ロースト)\]")
DESC_ROAST_PATTERN = re.compile(r"(中浅煎り|中深煎り|浅煎り|中煎り|深煎り)")
COLORME_PATTERN = re.compile(r"var Colorme = (\{.*?\});\s*\n")


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return resp.text


def list_items() -> list[tuple[str, str]]:
    """(pid, 区分)のリスト。"""
    items: dict[str, str] = {}
    for cbid, group in CATEGORIES:
        for page in range(1, MAX_PAGES + 1):
            t = fetch_html(f"{BASE_URL}/?mode=cate&cbid={cbid}&csid=0&page={page}")
            found = [p for p in dict.fromkeys(re.findall(r"[?&]pid=(\d+)", t)) if p not in items]
            if not found:
                break
            for p in found:
                items[p] = group
    return list(items.items())


def is_sold_out(product: dict) -> bool:
    if product.get("stock_num") == 0:
        return True
    variants = product.get("variants") or []
    return bool(variants) and all(v.get("stock_num") == 0 for v in variants)


def build_record(pid: str, group: str) -> dict | None:
    html_text = fetch_html(f"{BASE_URL}/?pid={pid}")
    m = COLORME_PATTERN.search(html_text)
    if not m:
        return None
    product = json.loads(m.group(1))["product"]
    raw = re.sub(r"\s+", " ", product["name"]).strip()
    wm = WEIGHT_PATTERN.search(raw)
    weight_g = int(wm.group(1)) if wm else None
    title = re.sub(r"\s+", " ", WEIGHT_PATTERN.sub("", raw)).strip()

    soup = BeautifulSoup(html_text, "html.parser")
    desc_el = soup.select_one("div.product_description")
    desc = re.sub(r"\s+", " ", desc_el.get_text(" ", strip=True))[:400] if desc_el else None

    parsed = parse_product(title)
    if group == "blend" or "ブレンド" in title:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"]:
            c = detect_country_name(title)
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, title)

    roast = None
    bm = BRACKET_ROAST_PATTERN.search(title)
    if bm:
        roast = bm.group(1).replace("シティーロースト", "シティロースト")
    elif desc:
        dm = DESC_ROAST_PATTERN.search(desc)
        roast = dm.group(1) if dm else None
    sold_out = is_sold_out(product)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
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
        "price": product.get("sales_price_including_tax"),
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/?pid={pid}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for pid, group in list_items():
        try:
            rec = build_record(pid, group)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={pid} ({e})")
            continue
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_hoshinocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_hoshinocoffee.json に出力しました")


if __name__ == "__main__":
    main()
