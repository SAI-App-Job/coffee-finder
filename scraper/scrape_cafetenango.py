# -*- coding: utf-8 -*-
"""
scrape_cafetenango.py

カフェテナンゴ(Cafe Tenango、東京都世田谷区深沢5-8-5 NEビル102、運営: 株式会社カヤヌマコーヒー、
中米産スペシャルティコーヒー専門の焙煎店)の通販サイト(www.cafetenango.jp、MakeShop・UTF-8)から
自家焙煎コーヒー豆の商品情報を取得する。

【対象商品について】
カテゴリ「コーヒー豆」(ct23、2ページ・93件)を対象にする。同カテゴリには豆のほか、定期便・お試しセット・
おすすめセット・テイスティングセット・ドリップバッグ詰め合わせが混在するため、商品名に「セット」「定期便」
「ドリップバッグ」「pack」「お試し」「4種」を含むものは除外する。
各銘柄は【80g】【100g】【200g】の重量違いが別商品として並ぶので、商品名から重量表記(【..g】)を除いた名前で
まとめ、最小重量の商品を代表1件とする(80gの銘柄は80g、それ以外は通常100g)。
価格は一覧ページの税込価格(豆のまま選択時の価格。挽き指定でも価格は同じ)。
品切れは一覧ページの <p class="item-soldout">SOLD OUT</p> で判定する。

【焙煎度】商品名の(R:n)表記。公式トップのメニューで R:1・R:2=浅煎り / R:3・R:4=中煎り / R:5・R:6=深煎り と定義されている。
複数の焙煎度から選べる商品(例: R:1/3/5)は、最初に書かれている焙煎度を代表値とする。

robots.txt: https://www.cafetenango.jp/robots.txt は 404(制限なし。2026-10-25確認)。
"""

import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, detect_stock_status

SHOP_INFO = {
    "name": "カフェテナンゴ",
    "url": "https://www.cafetenango.jp/",
    "platform": "MakeShop",
    "address": "東京都世田谷区深沢5-8-5 NEビル102",
    "prefecture": "東京都",
    "robots_txt_status": "robots.txt なし(404、2026-10-25確認)。制限なしとみなす",
    "source_note": "通販サイトのカテゴリ「コーヒー豆」(https://www.cafetenango.jp/view/category/ct23)の一覧ページを2026-10-25に確認。お知らせの最新は2026/10/23(18周年記念ペカリブレンド発売)。住所は公式トップ・会社概要の記載(〒158-0081)。自家焙煎の根拠は弥生の導入事例(https://www.yayoi-kk.co.jp/jirei/detail/81)の記述と公式会社概要(目利き・焙煎・抽出の技術)",
    "last_verified_at": "2026-10-25",
}

BASE_URL = "https://www.cafetenango.jp"
LIST_URL = BASE_URL + "/view/category/ct23"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL = 2

EXCLUDE_KEYWORDS = ["セット", "定期便", "ドリップバッグ", "pack", "お試し", "4種"]
WEIGHT_PREFIX = re.compile(r"^\s*【\s*(\d+)\s*[gｇ]?\s*】\s*")
ROAST_MAP = {"1": "浅煎り", "2": "浅煎り", "3": "中煎り", "4": "中煎り", "5": "深煎り", "6": "深煎り"}
ROAST_PATTERN = re.compile(r"[（(]\s*R\s*[:：]?\s*(\d)")


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def fetch_listing() -> list[dict]:
    items = []
    seen = set()
    for page in range(1, 10):
        if page > 1:
            time.sleep(REQUEST_INTERVAL)
        html = fetch(f"{LIST_URL}?page={page}")
        blocks = re.findall(r'<li>\s*<div class="item-icon">(.*?)</li>', html, flags=re.S)
        found = False
        for li in blocks:
            m = re.search(r'class="item-name"><a href="/view/item/(\d+)[^"]*">([^<]*)', li)
            if not m or m.group(1) in seen:
                continue
            seen.add(m.group(1))
            found = True
            price_m = re.search(r'class="price">\s*[￥¥]\s*([\d,]+)', li)
            items.append({
                "pid": m.group(1),
                "title": re.sub(r"\s+", " ", m.group(2)).strip(),
                "price": int(price_m.group(1).replace(",", "")) if price_m else None,
                "sold_out": "item-soldout" in li,
            })
        if not found:
            break
    return items


def build_record(group: list[dict]) -> dict | None:
    group.sort(key=lambda x: x["weight"])
    item = group[0]
    name = item["name"]
    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if parsed["category"] != "ブレンド":
        if not parsed["origin_country"]:
            c = detect_country_name(name)
            if c:
                parsed["origin_country"], parsed["origin_source"] = c, "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
    roast = None
    m = ROAST_PATTERN.search(name)
    if m:
        roast = ROAST_MAP.get(m.group(1))
    stock = detect_stock_status(name, structural_out_of_stock=item["sold_out"])
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast or parsed["roast_level"],
        "flavor_notes": None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": item["weight"],
        "stock_status": stock,
        "out_of_stock": stock != "販売中",
        "product_url": f"{BASE_URL}/view/item/{item['pid']}",
    }


def scrape_all_products() -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for it in fetch_listing():
        title = it["title"]
        if any(kw in title for kw in EXCLUDE_KEYWORDS):
            continue
        wm = WEIGHT_PREFIX.match(title)
        if not wm:
            continue
        name = WEIGHT_PREFIX.sub("", title).strip()
        # 表記ゆれ(括弧の全半角、ぺ/ペ)を吸収し、焙煎度の括弧を除いた名前でまとめる
        key = re.sub(r"[（(][^）)]*[）)]?", "", name).replace("ぺ", "ペ")
        key = re.sub(r"[\s　]+", "", key)
        it = dict(it, weight=int(wm.group(1)), name=name)
        groups.setdefault(key, []).append(it)
    records = []
    for group in groups.values():
        rec = build_record(group)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_cafetenango.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_cafetenango.json に出力しました")


if __name__ == "__main__":
    main()
