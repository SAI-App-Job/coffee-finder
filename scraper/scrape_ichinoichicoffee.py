# -*- coding: utf-8 -*-
"""
scrape_ichinoichicoffee.py

イチノイチコーヒー(ichinoichi.thebase.in、公式 ichinoichi.com、福島県郡山市熱海町熱海1-237)の
商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(福島県)の新規発掘で発見。

【住所について】
/law(特定商取引法)の事業者所在地に「〒963-1309 福島県郡山市熱海町熱海1-237」と記載(Shift_JIS、
BASE社ではなく店舗の住所)。

【対象商品について】
実データ確認済み(2026-10-12、sitemap.xmlの商品全10件): コーヒー豆はichinoichi BLEND(250g)と
シングルオリジン3銘柄(Papua New Guinea・Brazil・Kenya、各100g)の計4件。非対象は
サブスクリプション・定期便3件、おまかせドリップバッグ、おまかせ飲み比べセット2件
(NON_BEAN_KEYWORDSで除外)。
産地・精製方法・焙煎度合は商品説明の「【豆情報】」欄(原産国/精製方法/焙煎度合)から取得する。
ブレンドは原産国が複数(ブラジル・コロンビア・タンザニア・エチオピア)のため産地はNull。
ブレンドは250gのみの展開で、100gの設定が無いため250gを採用する。

【robots.txtについて】
他のBASE系店舗と同一の記述。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import html as html_lib
import json
import re

import requests

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, normalize_processing_method,
)

SHOP_INFO = {
    "name": "イチノイチコーヒー",
    "url": "https://ichinoichi.thebase.in/",
    "platform": "BASE",
    "address": "福島県郡山市熱海町熱海1-237",
    "prefecture": "福島県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://ichinoichi.thebase.in"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

NON_BEAN_KEYWORDS = ["サブスク", "定期便", "ドリップバッグ", "セット", "飲み比べ"]

TITLE_PATTERN = re.compile(r'<meta property="og:title" content="([^"]*)"')
DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*(?:g|ｇ)\s*$")
ROAST_FIELD = re.compile(r"焙煎度合:\s*([^\s(（]+)")
PROCESS_FIELD = re.compile(r"精製方法:\s*([^\s焙原風]+)")
ROAST_LABELS = {
    "City": "シティロースト",
}


def fetch_item_ids() -> list[str]:
    resp = requests.get(f"{BASE_URL}/sitemap.xml", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    return list(dict.fromkeys(re.findall(r"/items/(\d+)", resp.text)))


def build_record(item_id: str) -> dict | None:
    url = f"{BASE_URL}/items/{item_id}"
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    page = resp.text

    title_m = TITLE_PATTERN.search(page)
    if not title_m:
        return None
    raw_title = html_lib.unescape(title_m.group(1)).split(" | ")[0].strip()
    if any(kw in raw_title for kw in NON_BEAN_KEYWORDS):
        return None
    weight_m = WEIGHT_PATTERN.search(raw_title)
    weight_g = int(weight_m.group(1)) if weight_m else None
    name = re.sub(r"\s*\d+\s*(?:g|ｇ)\s*$", "", raw_title).strip()

    desc_m = DESC_PATTERN.search(page)
    desc_full = re.sub(r"\s+", " ", html_lib.unescape(desc_m.group(1))).strip() if desc_m else ""
    if weight_g is None:
        # 商品タイトルに重量が無い場合(Brazil Bom Jardim)は説明冒頭の「商品名：○○ 100g」から取る
        desc_weight_m = re.match(r"商品名：.*?(\d+)\s*(?:g|ｇ)", desc_full)
        weight_g = int(desc_weight_m.group(1)) if desc_weight_m else None
    price_m = PRICE_PATTERN.search(page)
    purchasability_m = PURCHASABILITY_PATTERN.search(page)
    sold_out = bool(purchasability_m) and purchasability_m.group(1) == "unpurchasable"

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        origin_m = re.search(r"原産国:\s*(\S+)", desc_full)
        detected = detect_country_name(name) or (detect_country_name(origin_m.group(1)) if origin_m else None)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name" if detect_country_name(name) else "description"
        parsed = apply_category_hint_fallback(parsed, name)

    roast_m = ROAST_FIELD.search(desc_full)
    roast = None
    if roast_m:
        r = roast_m.group(1)
        roast = ROAST_LABELS.get(r, r)
    process_m = PROCESS_FIELD.search(desc_full)
    processing = normalize_processing_method(process_m.group(1)) if process_m else parsed["processing_method"]

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"] or roast,
        "roast_hint": None,
        "flavor_notes": desc_full[:400] or None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price_m.group(1)) if price_m else None,
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item_id in fetch_item_ids():
        try:
            record = build_record(item_id)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_ichinoichicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_ichinoichicoffee.json に出力しました")


if __name__ == "__main__":
    main()
