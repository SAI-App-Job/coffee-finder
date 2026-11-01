# -*- coding: utf-8 -*-
"""
scrape_yukinokocoffee.py

珈琲 雪の子(yukinoko.theshop.jp、宮城県仙台市青葉区八幡4-1-13)の商品情報を取得する。BASE(theshop.jp)。

【対象商品について】
実データ確認済み(2026-10時点): ALL ITEM(7商品)のうち、100gのコーヒー豆4銘柄(月替わりの
秋のブレンド・コロンビア・ニカラグア、カフェインレスのエチオピア)を対象とする。
「コーヒー豆100g 3種セット」と定期便2件は除外。豆のまま/挽き豆の選択肢があるので
豆のままの価格・在庫を採用する(秋のブレンドは豆のままのみ在庫なしで挽き豆は在庫あり=
豆のまま基準で品切れ扱い)。
価格・説明(og:description)・在庫(商品ページの豆のままバリエーション)・焙煎度(説明文)は商品ページから取得する。

【robots.txtについて】
他のBASE系店舗と同一の記述(User-agent: * は許可)。識別可能な独自UAを使用し、
リクエスト間隔は5秒以上とする。
"""

import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "珈琲 雪の子",
    "url": "https://yukinoko.theshop.jp/",
    "platform": "BASE",
    "address": "宮城県仙台市青葉区八幡4-1-13",
    "prefecture": "宮城県",
    "robots_txt_status": "実質許可(User-agent: * は許可。識別可能なUser-Agentを使用)",
    "source_note": "BASE公式ショップ(https://yukinoko.theshop.jp/items/all)の商品ページを2026-10-26に確認。住所は食べログ。"
                   "自家焙煎の根拠は公式サイトには無く、Instagram(@yukinoko_coffee)のbioのみ。"
                   "100g豆のままの4銘柄を採用。3種セット・定期便は除外。月替わり商品(販売期間2026-10-15〜10-31)を含む。",
    "last_verified_at": "2026-10-26",
}

BASE_URL = "https://yukinoko.theshop.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
INTERVAL = 5.5

# (商品ID, 商品名, 重量(g), ブレンドか)
ITEMS = [
    ("71963775", "秋のブレンド", 100, True),
    ("72594244", "コロンビア ウイラ テラ・ヴェルデ イエローコロンビア", 100, False),
    ("72594353", "ニカラグア ラ・ウェラ エチオサル ウォッシュド", 100, False),
    ("88613662", "カフェインレスコーヒー エチオピア", 100, False),
]

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
ROAST_PATTERN = re.compile(r"(中深煎り|中浅煎り|深煎り|浅煎り|中煎り)")
BEANS_VARIATION_PATTERN = re.compile(r'<p class="cot-itemOrder-variationName"( data-type="soldOut")?>豆のまま</p>')


def build_record(item_id: str, name: str, weight_g: int, is_blend: bool) -> dict:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    desc = re.sub(r"\s+", " ", desc_m.group(1)).strip()[:400] if desc_m else None
    price_m = PRICE_PATTERN.search(html_text)
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    beans_m = BEANS_VARIATION_PATTERN.search(html_text)
    if purchasability_m and purchasability_m.group(1) == "unpurchasable":
        sold_out = True  # 品切れ・販売期間終了
    else:
        sold_out = bool(beans_m and beans_m.group(1))  # 豆のままバリエーションのみ在庫なしの場合も品切れ扱い
    roast_m = ROAST_PATTERN.search(desc or "")

    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
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
        "roast_level": (roast_m.group(1) if roast_m else None) or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price_m.group(1)) if price_m else None,
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/items/{item_id}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for i, (item_id, name, weight_g, is_blend) in enumerate(ITEMS):
        if i:
            time.sleep(INTERVAL)
        try:
            records.append(build_record(item_id, name, weight_g, is_blend))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_yukinokocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_yukinokocoffee.json に出力しました")


if __name__ == "__main__":
    main()
