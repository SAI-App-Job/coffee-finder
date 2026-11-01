# -*- coding: utf-8 -*-
"""
scrape_tsuchinokoffee.py

ツチノコーヒー(tsuchinokohi.base.shop、宮城県仙台市若林区荒町66)の商品情報を取得する。BASE。

【対象商品について】
実データ確認済み(2026-10時点): ALL ITEM(23商品)のうち、コーヒー豆/粉100gの単品6銘柄と
「選べるUMAブレンド」(1ページでツチノコ・カッパ・ネッシーの3ブレンドを選択する商品。
銘柄ごとに3件に展開し、商品URLはフラグメントで一意化)を対象とする。
50g×4/100g×3の飲み比べ、ドリップバッグ・ディップ、水出しコーヒーパック、Tシャツ・
キャニスター付きセットは除外。豆のまま/挽き粉が選べるので豆のままの価格を採用。
価格・在庫(item_purchasability)・説明(og:description)・焙煎度(説明文の「焙煎度:」)は商品ページから取得する。

【robots.txtについて】
User-agent: * は許可(python-requests/curl等は個別にDisallow)。識別可能な独自UAを使用し、
リクエスト間隔は5秒以上とする。
"""

import json
import re
import time
from urllib.parse import quote

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "ツチノコーヒー",
    "url": "https://tsuchinokohi.base.shop/",
    "platform": "BASE",
    "address": "宮城県仙台市若林区荒町66",
    "prefecture": "宮城県",
    "robots_txt_status": "実質許可(User-agent: * は許可、python-requests/curl等は個別にDisallow。識別可能なUser-Agentを使用)",
    "source_note": "BASE公式ショップ(https://tsuchinokohi.base.shop/items/all)の商品ページを2026-10-26に確認。住所は食べログ(荒町に2026-08-06移転オープンの口コミ)。公式ABOUTは旧所在地の土樋表記のまま。"
                   "100g豆のままの単品6銘柄とUMAブレンド3種を採用。飲み比べ・ドリップバッグ・ディップ・水出し・Tシャツ付きセットは除外。ブログの最終更新は2023年10月。",
    "last_verified_at": "2026-10-26",
}

BASE_URL = "https://tsuchinokohi.base.shop"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
INTERVAL = 5.5

# (商品ID, 商品名, 重量(g))
ITEMS = [
    ("123428310", "コスタリカ タラス ハニー", 100),
    ("123800536", "ルワンダ ホワイトトップ ブルボン", 100),
    ("77531258", "ブラジルブルー セラード 手摘み完熟", 100),
    ("78194346", "ブラジルピンク ブルボン サンドライ", 100),
    ("77532473", "インドネシア アチェ マンデリン", 100),
    ("77532788", "ペルー トゥンキ イナンバリ農協", 100),
]
# 選べるUMAブレンド(1商品ページに3ブレンド): (商品名, 焙煎度)
UMA_ID = "127280127"
UMA_BLENDS = [
    ("UMAブレンド ツチノコブレンド", None),
    ("UMAブレンド カッパブレンド", "深煎り"),
    ("UMAブレンド ネッシーブレンド", None),
]
ORIGIN_OVERRIDES = {"123800536": "ルワンダ", "77531258": "ブラジル", "78194346": "ブラジル"}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
ROAST_PATTERN = re.compile(r"焙煎度[:：]\s*([^\s内苦酸甘]+?)(?=内容量|苦味|$)")


def fetch(item_id: str) -> str:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def make_record(item_id, name, weight_g, html_text, roast_level, is_blend, url):
    desc_m = DESC_PATTERN.search(html_text)
    desc = re.sub(r"\s+", " ", desc_m.group(1)).strip()[:400] if desc_m else None
    price_m = PRICE_PATTERN.search(html_text)
    pm = PURCHASABILITY_PATTERN.search(html_text)
    sold_out = bool(pm) and pm.group(1) == "unpurchasable"
    if roast_level is None and desc_m:
        rm = ROAST_PATTERN.search(re.sub(r"\s+", "", desc_m.group(1)))
        roast_level = rm.group(1) if rm else None

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
        if item_id in ORIGIN_OVERRIDES:
            parsed["origin_country"] = ORIGIN_OVERRIDES[item_id]
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
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for i, (item_id, name, weight_g) in enumerate(ITEMS):
        if i:
            time.sleep(INTERVAL)
        html_text = fetch(item_id)
        records.append(make_record(item_id, name, weight_g, html_text, None, False, f"{BASE_URL}/items/{item_id}"))
    time.sleep(INTERVAL)
    html_text = fetch(UMA_ID)
    for name, roast in UMA_BLENDS:
        records.append(make_record(UMA_ID, name, 100, html_text, roast, True,
                                   f"{BASE_URL}/items/{UMA_ID}#{quote(name)}"))
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_tsuchinokoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_tsuchinokoffee.json に出力しました")


if __name__ == "__main__":
    main()
