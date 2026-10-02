# -*- coding: utf-8 -*-
"""
scrape_misatocoffee.py

三郷珈琲焙煎所(shop.misato.or.jp、埼玉県三郷市彦成5-149-2、NPOみさと運営の
就労継続支援事業所、自家焙煎)の商品情報を取得する。BASE。

【店舗発見の経緯】
2026-09-04の別セッションで「EC準備中」として見送られていたが、2026-08-25の
NPOお知らせで通販サイト(BASE)の開設が案内されており、全国再調査(埼玉県)で
再検証して実装した。

【対象商品について】
実データ確認済み(2026-10時点): 全8商品のうち、ドリップバッグ2種(10個セット)を
除いた豆6銘柄(ブレンド1・ストレート5)を対象とする。各商品は200g/500gの
サイズ違いを同一ページ内のバリエーションで持つため、代表として200g価格を採用する。
「ブラジル No.2」は商品説明に生豆時重量の記載があるが、ページ全体の表記は
他銘柄と同じ200gのため同様に扱う。

【robots.txtについて】
他のBASE系店舗と同一の記述。識別可能な独自User-Agentを使用する。
"""

import json
import re

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "三郷珈琲焙煎所",
    "url": "https://shop.misato.or.jp/",
    "platform": "BASE",
    "address": "埼玉県三郷市彦成5-149-2",
    "prefecture": "埼玉県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://shop.misato.or.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

ITEM_IDS = [
    "152750276",  # 三郷ブレンド
    "152750528",  # エチオピア モカシダモ
    "152750821",  # ブルンジ FW レッドブルボン
    "152750356",  # ブラジル No.2
    "154773369",  # ペルー カハマルカ ウォッシュド 有機栽培
    "154773407",  # ベトナム ロブスタ
]

NAMES = {
    "152750276": "三郷ブレンド",
    "152750528": "エチオピア モカシダモ",
    "152750821": "ブルンジ FW レッドブルボン",
    "152750356": "ブラジル No.2",
    "154773369": "ペルー カハマルカ ウォッシュド 有機栽培",
    "154773407": "ベトナム ロブスタ",
}

TITLE_PATTERN = re.compile(r'<meta property="og:title" content="([^"]*)"')
DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id: str) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=20)
    resp.encoding = "utf-8"
    html_text = resp.text

    title_m = TITLE_PATTERN.search(html_text)
    if not title_m:
        return None
    # ページタイトルは「銘柄名+キャッチコピー」形式のため、銘柄名のみをNAMESで固定する
    raw_name = NAMES[item_id]

    desc_m = DESC_PATTERN.search(html_text)
    desc = desc_m.group(1).strip() if desc_m else None

    price_m = PRICE_PATTERN.search(html_text)
    price = int(price_m.group(1)) if price_m else None
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    sold_out = bool(purchasability_m) and purchasability_m.group(1) != "purchasable"

    parsed = parse_product(raw_name)
    if parsed["category"] != "ブレンド":
        detected = detect_country_name(raw_name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, raw_name)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": raw_name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": 200,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/items/{item_id}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item_id in ITEM_IDS:
        try:
            detail = build_record(item_id)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        if detail is not None:
            records.append(detail)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_misatocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_misatocoffee.json に出力しました")


if __name__ == "__main__":
    main()
