# -*- coding: utf-8 -*-
"""
scrape_cuecoffee.py

CUE.COFFEE(cuecoffee.official.ec、公式サイト https://cue-coffee.com/、広島県広島市中区上八丁堀、
注文を受けてから焙煎する自家焙煎豆)の商品情報を取得する。BASE(official.ec ドメイン)。

【店舗発見の経緯】
全国再調査(広島県)の新規発掘で発見。ハーブコーヒー(floweree)は別店のため対象外。

【対象商品について】
実データ確認済み(2026-10時点): sitemap.xmlの商品58件のうち、タイトルに「100g」を含む
焙煎豆(シングルオリジン・ブレンド・デカフェ)46件を対象とする。オーツミルク(2件)、
HARIO/CAFEC等の器具・フィルター(10件)は除外。全商品が100g単位の1商品で、重量違いの重複は無い。

【焙煎度について】
実データ確認済み: シングルオリジンは注文時に「ローストレベル」(おまかせ/シナモン〜フレンチ)を
選択する方式(roast_selectable=True、焙煎度はNone)。ブレンド(叢雨)のみ「焙煎度は中煎り程度」と
説明文に固定の記載があるため、roast_hintとして保持する。

【価格・在庫について】
価格は税込(特商法の表記は「販売価格は税込み表記」)。在庫はitem_purchasabilityで判定。
ギフトボックス(+250円)はオプションのため価格には含めない。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "CUE.COFFEE",
    "url": "https://cuecoffee.official.ec/",
    "platform": "BASE",
    "address": "広島県広島市中区上八丁堀5-1 新上八丁堀ビル1F",
    "prefecture": "広島県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://cuecoffee.official.ec"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

TITLE_PATTERN = re.compile(r'<meta property="og:title" content="([^"]*)"')
DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
FIXED_ROAST_PATTERN = re.compile(r"焙煎度は(浅煎り|中浅煎り|中煎り|中深煎り|深煎り)")
EXCLUDE_KEYWORDS = ["オーツ", "HARIO", "CAFEC", "ドリッパー", "フィルター", "サーバー"]


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def build_record(item_url: str) -> dict | None:
    html_text = fetch(item_url)
    title_m = TITLE_PATTERN.search(html_text)
    if not title_m:
        return None
    title = re.sub(r"\s+", " ", title_m.group(1).split(" | ")[0]).strip()
    if any(kw in title for kw in EXCLUDE_KEYWORDS):
        return None
    weight_m = WEIGHT_PATTERN.search(title)
    if not weight_m:
        return None  # 重量表記のない商品(器具等)は対象外
    weight_g = int(weight_m.group(1))

    desc_m = DESC_PATTERN.search(html_text)
    desc = re.sub(r"\s+", " ", desc_m.group(1)).strip() if desc_m else ""
    price_m = PRICE_PATTERN.search(html_text)
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    sold_out = bool(purchasability_m) and purchasability_m.group(1) == "unpurchasable"

    parsed = parse_product(title)
    if parsed["is_flavored"]:
        return None
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(title)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, title)
        # coffee_parser.pyの国名辞書で検出できない表記(「タイ」)を明示する
        if not parsed["origin_country"] and title.startswith("タイ "):
            parsed["origin_country"] = "タイ"
            parsed["origin_source"] = "raw_name"
    # 商品名の「〈ウォシュ〉」(ウォッシュの表記ゆれ)は辞書で検出できないため補う
    if not parsed["processing_method"] and "ウォシュ" in title:
        parsed["processing_method"] = "ウォッシュド"

    fixed_roast_m = FIXED_ROAST_PATTERN.search(desc)
    roast_hint = fixed_roast_m.group(1) if fixed_roast_m else None
    roast_selectable = roast_hint is None and parsed["roast_level"] is None

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
        "roast_hint": roast_hint,
        "roast_selectable": roast_selectable,
        "flavor_notes": desc[:400] or None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price_m.group(1)) if price_m else None,
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": item_url,
    }


def scrape_all_products() -> list[dict]:
    sitemap = fetch(f"{BASE_URL}/sitemap.xml")
    item_urls = re.findall(r"<loc>([^<]*/items/\d+)</loc>", sitemap)
    records = []
    for item_url in item_urls:
        try:
            record = build_record(item_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item_url} ({e})")
            continue
        if record is not None:
            records.append(record)
        time.sleep(0.5)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_cuecoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_cuecoffee.json に出力しました")


if __name__ == "__main__":
    main()
