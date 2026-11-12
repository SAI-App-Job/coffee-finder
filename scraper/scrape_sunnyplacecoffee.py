# -*- coding: utf-8 -*-
"""
scrape_sunnyplacecoffee.py

サニープレイスコーヒー(https://shop.sunnyplace-coffee.com/、山形県上山市権現堂89)の商品情報を取得する。BASE。

【店舗について】
公式(https://sunnyplace-coffee.com/shop-info/)に「〒999-3111 山形県上山市権現堂89」「自家焙煎珈琲店・焙煎工房です」「業務用の小型ロースター(フジローヤル R-101)」、営業11:00〜17:30(木・金定休)。
豆はブレンド3種(200gのみ)とシングル5種(100g/200gが別ページのため100gを代表)。焙煎度はページの「焙煎度 1〜8」表記を、4=ハイロースト→中煎り、5=シティロースト→中深煎り、6=フルシティロースト→深煎りと読み替えた。ドリップバッグ・ギフトBOXは除外。

【robots.txtについて】
2026-11-03確認: User-agent: * は Allow: / で、Disallow は /cart/ /web_cart/ /shops/ 等のみ。
python-requests/curl 等は個別に Disallow: / 指定のため、本スクレイパーは識別可能な
独自User-Agent(CoffeeFinderBot)を使用し、リクエスト間隔は5秒以上とする。

【対象商品の選定について】
実データ確認済み(2026-11-03): 下のITEMSは、サイトマップの全商品ページから
豆(シングルオリジン・ブレンド・デカフェ)のみを選んだもの。ドリップバッグ・ギフトBOXは除外。シングルは100g/200gが別ページのため100gを代表にした。
商品名・重量・焙煎度は商品ページの表記を確認したうえでITEMSに明示している。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。
"""

import html
import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "サニープレイスコーヒー",
    "url": "https://shop.sunnyplace-coffee.com/",
    "platform": "BASE",
    "address": "山形県上山市権現堂89",
    "prefecture": "山形県",
    "robots_txt_status": "実質許可(2026-11-03確認。User-agent: * は Allow: / で /cart/ 等のみ禁止。python-requests/curl等は個別にDisallow: /指定のため識別可能なUser-Agentを使用、間隔5秒以上)",
    "source_note": "BASEショップ(独自ドメイン https://shop.sunnyplace-coffee.com/)のabout・サイトマップ・各商品ページと公式(https://sunnyplace-coffee.com/shop-info/)を2026-11-03に確認。住所は公式「〒999-3111 山形県上山市権現堂89」。サイトマップ最終更新2026-10-14。焙煎度はページ記載の1〜8段階とロースト名から換算",
    "last_verified_at": "2026-11-03",
}

BASE_URL = "https://shop.sunnyplace-coffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL = 5.2  # BASEは5秒以上
DESC_PREFIX = ""  # 説明文の先頭に付ける注記(該当商品IDのみ)
DESC_PREFIX_IDS = []

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定), 産地の上書き(Noneなら自動))
ITEMS = [
    ('119332784', 'ペルー ミラフローレス農園 ジャバ アナエロビック ウォッシュド', 100, None, '中煎り', None),
    ('124642028', 'ブラジル サントアントニオ プレミアムショコラ', 100, None, '中深煎り', None),
    ('131088925', 'エルサルバドル サンカエタノ農園 パカマラ ナチュラル', 100, None, '中深煎り', None),
    ('51030341', 'エチオピア イルガチェフェ G1 ウェギダブルー 無農薬栽培', 100, None, '中煎り', None),
    ('97968918', 'ジャマイカ ブルーマウンテンNo.1 クライスデール', 100, None, '中煎り', None),
    ('83764432', 'サニープレイスブレンド', 200, 'ブレンド', '中深煎り', None),
    ('93905563', '深煎りブレンド', 200, 'ブレンド', '深煎り', None),
    ('97766594', 'モカブレンド', 200, 'ブレンド', '中煎り', None),
]

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id, name, weight_g, category_override, roast_level, origin_override):
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    if resp.status_code != 200:
        print(f"[warn] 取得失敗(回避せずスキップ): item_id={item_id} status={resp.status_code}")
        return None
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    desc = re.sub(r"\s+", " ", html.unescape(desc_m.group(1))).strip()[:400] if desc_m else None
    if item_id in DESC_PREFIX_IDS:
        desc = (DESC_PREFIX + (desc or "")).strip()
    price_m = PRICE_PATTERN.search(html_text)
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    # unpurchasable=全バリエーション購入不可(品切れ)。partially_purchasable=一部のみ不可なので販売中扱い
    sold_out = bool(purchasability_m) and purchasability_m.group(1) == "unpurchasable"

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if category_override:
        parsed["category"] = category_override
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if origin_override:
            parsed["origin_country"] = origin_override
            parsed["origin_source"] = "raw_name"

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level or parsed["roast_level"],
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


def scrape_all_products():
    records = []
    for i, (item_id, name, weight_g, category_override, roast_level, origin_override) in enumerate(ITEMS):
        if i:
            time.sleep(REQUEST_INTERVAL)
        try:
            record = build_record(item_id, name, weight_g, category_override, roast_level, origin_override)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_sunnyplacecoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_sunnyplacecoffee.json に出力しました")


if __name__ == "__main__":
    main()
