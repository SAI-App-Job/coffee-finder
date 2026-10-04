# -*- coding: utf-8 -*-
"""
scrape_coffeehousefield.py

COFFEE HOUSE FIELD(coffeehousefield.jp、兵庫県西宮市本町5-10、阪神西宮、スペシャルティコーヒー専門店。
生豆の自社輸入・自家焙煎)の商品情報を取得する。オンライン販売は関連会社(株式会社ディーシーエス、
同住所)の器具店「ESPRESSO STORE」(www.espressostore.net、MakeShop)内の
COFFEE HOUSE FIELD専用ページ(/coffeehousefield/)に掲載されている。

【店舗・自家焙煎の確認(2026-10)】
公式サイトに「自家焙煎」「生豆の自社輸入・焙煎・抽出に至るまで自社で」「兵庫県西宮市本町5-10」と
記載。ESPRESSO STOREのフッターも同住所(株式会社ディーシーエス)。

【対象商品について】
実データ確認済み(2026-10時点): ブランドページの13商品のうち、豆のカテゴリ(/view/category/beans)に
載る3商品(えべっさん ブレンド、エチオピア イルガチェフェ、グアテマラ ワイカン)が対象。
ドリップバッグ、リキッドコーヒー、GIFTセットは除外。
各商品に「豆の挽き方(豆のまま/中挽き)」「容量(100g/200g、ブレンドは500g/1kgも)」の選択肢があり、
最小容量は100g。静的HTMLに表示されているデフォルト価格を100gの価格とみなす(JSで容量選択後に
更新される方式。他のMakeShop店舗と同じ扱い)。
在庫は一覧の「カートに入れる」ボタンの有無で判定(個別ページのボタンはJS制御で静的には判別不可)。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name,
    normalize_processing_method,
)

SHOP_INFO = {
    "name": "COFFEE HOUSE FIELD",
    "url": "https://www.espressostore.net/coffeehousefield",
    "platform": "MakeShop(ESPRESSO STORE内)",
    "address": "兵庫県西宮市本町5-10",
    "prefecture": "兵庫県",
    "robots_txt_status": "未確認(MakeShop標準構成)",
}

BASE_URL = "https://www.espressostore.net"
LIST_URL = f"{BASE_URL}/view/category/beans"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_KEYWORDS = ["ドリップバッグ", "ドリップバック", "GIFT", "ギフト", "セット", "リキッド"]
ROAST_HINT_PATTERN = re.compile(r"(極深煎り|中深煎り|中浅煎り|浅煎り|中煎り|深煎り)")
SPEC_PATTERN = re.compile(r"^■\s*(生産国|地域|農園|標高|品種|生産処理|精製)\s*[：:]\s*(.+)$")


def fetch(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def list_items() -> list[dict]:
    soup = fetch(LIST_URL)
    items = []
    for li in soup.select("ul.item-list > li"):
        a = li.select_one("h3.item-name a")
        if not a:
            continue
        name = re.sub(r"\s+", " ", a.get_text(strip=True))
        if any(k in name for k in EXCLUDE_KEYWORDS):
            continue
        # 一覧に「カートに入れる」が無い(売切れ表示)商品は完売扱い
        has_cart = li.select_one(".add-list-cart") is not None
        maker = li.select_one(".item-category")
        if maker and "FIELD" not in maker.get_text():
            continue
        items.append({
            "name": name,
            "path": re.sub(r"\?.*$", "", a["href"]),
            "sold_out": not has_cart,
        })
    return items


def build_record(it: dict) -> dict:
    url = BASE_URL + it["path"]
    soup = fetch(url)
    title = it["name"]
    h1 = soup.select_one(".item-title h1")
    if h1:
        title = re.sub(r"\s+", " ", h1.get_text(strip=True))
    sub = soup.select_one(".item-nam_jp")
    sub_text = sub.get_text(strip=True) if sub else ""
    price_el = soup.select_one('[data-id="makeshop-item-price:1"]')
    price = None
    if price_el:
        m = re.search(r"[\d,]+", price_el.get_text())
        price = int(m.group().replace(",", "")) if m else None
    weights = []
    for opt in soup.select("select option"):
        wm = re.match(r"^(\d+)\s*g", opt.get_text(strip=True))
        if wm:
            weights.append(int(wm.group(1)))
    weight = min(weights) if weights else None

    specs = {}
    for li in soup.select(".item-spec-list li"):
        m = SPEC_PATTERN.match(li.get_text(strip=True))
        if m:
            specs[m.group(1)] = m.group(2).strip()
    flavor_el = soup.select_one("p.flavor")
    flavor_h4 = flavor_el.find_next("h4") if flavor_el else None
    flavor_notes = flavor_h4.get_text(" ", strip=True) if flavor_h4 else None

    parsed = parse_product(title)
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        processing = None
    else:
        detected = detect_country_name(title)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"], parsed["origin_source"] = detected, "raw_name"
        parsed = apply_category_hint_fallback(parsed, sub_text or title)
        if not parsed["origin_country"] and specs.get("生産国"):
            c = detect_country_name(specs["生産国"])
            if c:
                parsed["origin_country"], parsed["origin_source"] = c, "country_name"
        processing = parsed["processing_method"]
        raw_proc = specs.get("生産処理") or specs.get("精製")
        if not processing and raw_proc:
            processing = normalize_processing_method(raw_proc)
    hint = ROAST_HINT_PATTERN.search(sub_text)
    farm_bits = [f"{k}: {specs[k]}" for k in ("地域", "農園", "標高", "品種") if specs.get(k)]
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": hint.group(1) if hint else None,
        "flavor_notes": flavor_notes,
        "farm_note": "、".join(farm_bits) if farm_bits else None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "完売" if it["sold_out"] else "販売中",
        "out_of_stock": it["sold_out"],
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for it in list_items():
        try:
            records.append(build_record(it))
        except requests.RequestException as e:
            print(f"[warn] 詳細取得失敗: {it['path']} ({e})")
        time.sleep(0.5)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_coffeehousefield.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeehousefield.json に出力しました")


if __name__ == "__main__":
    main()
