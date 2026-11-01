# -*- coding: utf-8 -*-
"""
scrape_wavescoffee.py

WAVES COFFEE(https://shop.waves-coffee.com/、山口県宇部市朝日町2-1)の商品情報を取得する。BASE(独自ドメイン)。

【店舗の確認】
公式サイト https://waves-coffee.com/about/ に「WAVES COFFEEは、山口県宇部市にあるコーヒー焙煎所です」
「小回りのきく2kg焙煎機」「営業日:火〜土 11:00〜17:30」とあり、実店舗・自家焙煎を確認。
住所は特商法(https://shop.waves-coffee.com/law)と公式の店舗情報で一致(2026-11-01確認)。

【対象商品について】
実データ確認済み(2026-11-01時点): 商品24件のうち、100g単品の焙煎豆10種(ブレンド2・シングル8、デカフェ含む)が対象。
おためし3種セット(50g×3)、定期便2種、ドリップバッグ・水出しバッグ、ラテベース、器具・フィルターは除外。
商品ページの「種類」(豆のまま/中挽き/粗挽き/細挽き)は挽き目の選択肢で、豆のままの価格(同一価格)を採用。
価格・在庫(item_purchasability)・説明(og:description)・焙煎度(説明の「焙煎度合」)は商品ページから取得する。

【robots.txt】
python-requests/curl等は個別にDisallow、User-agent: * では /cart/ /web_cart/ /shops/ 等のみ禁止。
本スクレイパーは識別可能な独自User-Agentを使用し、商品ページ(/items/)のみ取得、間隔5秒。
"""

import html
import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, normalize_processing_method

SHOP_INFO = {
    "name": "WAVES COFFEE",
    "url": "https://shop.waves-coffee.com/",
    "platform": "BASE",
    "address": "山口県宇部市朝日町2-1",
    "prefecture": "山口県",
    "robots_txt_status": "実質許可(User-agent: * は /cart/ 等のみ禁止。python-requests/curl等は個別に禁止のため識別可能なUser-Agentを使用)",
    "source_note": "https://shop.waves-coffee.com/ の商品ページ・/lawと公式 https://waves-coffee.com/about/ を2026-11-01に確認。"
                   "公式に「山口県宇部市にあるコーヒー焙煎所」「2kg焙煎機」「営業日:火〜土」とあり実店舗・自家焙煎。"
                   "公式サイトに2026-10-24のイベント参加投稿へのリンクあり(現役)。100g単品の豆10種を掲載(セット・定期便・ドリップバッグ等は除外)",
    "last_verified_at": "2026-11-01",
}

BASE_URL = "https://shop.waves-coffee.com"
REQUEST_INTERVAL_SEC = 5  # BASEは5秒以上
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定))
ITEMS = [
    ("59534955", "いつものブレンド", 100, "ブレンド"),
    ("99422843", "いつものブレンド ダーク", 100, "ブレンド"),
    ("74642214", "ケニア アダロニア AA", 100, None),
    ("14885993", "エチオピア イルガチェフェ ベレカ G1", 100, None),
    ("44526919", "インド デバギリ農園", 100, None),
    ("144710763", "コロンビア カウカ SUP", 100, None),
    ("17580846", "パプア・ニューギニア トロピカルマウンテン", 100, None),
    ("85435362", "デカフェ メキシコ チアパス", 100, None),
    ("22526476", "グアテマラ アルト・デ・メディナ", 100, None),
    ("59534651", "インドネシア マンデリン アチェ ゲガラン", 100, None),
]

# coffee_parser.pyの国名辞書で検出できない表記の産地を明示する
ORIGIN_OVERRIDES = {"17580846": "パプアニューギニア", "85435362": "メキシコ"}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
ROAST_PATTERN = re.compile(r"焙煎度合[:：]\s*(\S{1,4}?煎り)")
PROCESS_PATTERN = re.compile(r"(?:生産処理|精製)[:：]\s*(.+?)(?=クロップ|$)")
FARM_KEYS = ("生産地", "品種", "標高")
FARM_PATTERN = re.compile(r"(生産地|品種|標高)[:：]\s*(.+?)(?=生産地|品種|標高|生産処理|精製|クロップ|$)")


def build_record(item_id, name, weight_g, category_override):
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    full_desc = re.sub(r"\s+", " ", html.unescape(desc_m.group(1))).strip() if desc_m else ""
    desc = full_desc.split("【発送方法")[0].strip()[:400] or None
    roast_m = ROAST_PATTERN.search(full_desc)
    roast_level = roast_m.group(1) if roast_m else None
    price_m = PRICE_PATTERN.search(html_text)
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
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
        if item_id in ORIGIN_OVERRIDES:
            parsed["origin_country"] = ORIGIN_OVERRIDES[item_id]
            parsed["origin_source"] = "raw_name"
    proc_m = PROCESS_PATTERN.search(full_desc)
    if proc_m and not parsed["processing_method"]:
        parsed["processing_method"] = normalize_processing_method(proc_m.group(1).strip())
    farm_note = "、".join(f"{k}: {v.strip()}" for k, v in FARM_PATTERN.findall(full_desc)) or None

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
        "farm_note": farm_note,
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
    for i, (item_id, name, weight_g, category_override) in enumerate(ITEMS):
        if i:
            time.sleep(REQUEST_INTERVAL_SEC)
        try:
            record = build_record(item_id, name, weight_g, category_override)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_wavescoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_wavescoffee.json に出力しました")


if __name__ == "__main__":
    main()
