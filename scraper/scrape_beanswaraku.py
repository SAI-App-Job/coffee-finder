# -*- coding: utf-8 -*-
"""
scrape_beanswaraku.py

珈琲焙煎庵 和樂(https://beanswarku.thebase.in/、東京都日野市豊田2-32-5)の自家焙煎コーヒー豆の商品情報を取得する。BASE。

【店舗の実在確認(2026-10-25)】
公式サイト https://beanswaraku.com/「焙煎するたびにあれこれ工夫をし」「いろいろ焙煎した結果、和樂の味はフルシティローストに行き着きました。以来、頑なにフルシティローストを守っています(ブレンド「玄」だけはイタリアンロースト)」
「東京都日野市豊田2-32-5 営業時間11:00〜18:00 定休日 水曜日、第一第三木曜日 電話042-583-7383 JR中央線豊田駅南口から徒歩約9分」「「珈琲 和樂」と「珈琲挽売」の小さな看板がポストの横に」。
BASEショップ about「珈琲の甘さにこだわる自家焙煎珈琲店です」、特商法「東京都日野市豊田2-32-5」(事業者 安住和恵)。

【対象商品について】
実データ確認済み(2026-10-25): 商品ページ19件(sitemap.xml)のうち豆単品18件(ブレンド4・ストレート14)。除外: ドリップパック1件。
商品ページ・特商法・公式サイト(Deliver/Wholesaleの記述のみ)のいずれにも内容量(gram)の記載が無いため、weight_gは全件None。焙煎度は公式の「基本はフルシティロースト、ブレンド玄のみイタリアンロースト」に基づく。
商品名・重量・焙煎度は商品ページの表記を確認したうえで下のITEMSに明示している。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。

【robots.txtについて】
BASE共通の記述(python-requests/curl等は個別にDisallow: /、User-agent: *では
/cart/・/web_cart/・/shops/・/api/shops/等のみ禁止)。本スクレイパーは識別可能な
独自User-Agentを使用し、取得するのは /items/ の商品ページのみ。取得間隔は5秒。
"""

import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "珈琲焙煎庵 和樂",
    "url": "https://beanswarku.thebase.in/",
    "platform": "BASE",
    "address": "東京都日野市豊田2-32-5",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-10-25確認。BASE共通の記述でpython-requests/curl等は個別にDisallow、User-agent: * では商品ページ(/items/)は許可。識別可能なUser-Agentを使用)",
    "source_note": "BASEショップ(https://beanswarku.thebase.in/ ※綴りはbeanswarku)の商品ページ(sitemap.xmlの/items/全19件)・about・特商法と公式サイト https://beanswaraku.com/ を2026-10-25に確認。公式NEWSは2026.08.05。内容量の記載がないため重量は不明。",
    "last_verified_at": "2026-10-25",
}

BASE_URL = "https://beanswarku.thebase.in"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL = 5

# (商品ID, 商品名, 重量(g)またはNone, 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら説明文→商品名の順で判定))
ITEMS = [
    ('124269264', 'スラウェシアラビカG!', None, None, 'フルシティロースト'),
    ('134285913', 'ブラジルカルデミナスフローラルブルボン', None, None, 'フルシティロースト'),
    ('63525826', 'ブラジル ショコラ ピーベリ', None, None, 'フルシティロースト'),
    ('63525876', 'エルサルバドル ビクトリア農場', None, None, 'フルシティロースト'),
    ('63525895', 'グアテマラ ゴールデンバレンシア リオ コロラド農園', None, None, 'フルシティロースト'),
    ('63525951', 'ケニアAA', None, None, 'フルシティロースト'),
    ('63526024', 'ブレンド<楽>', None, 'ブレンド', 'フルシティロースト'),
    ('63526057', 'ブレンド<芳>', None, 'ブレンド', 'フルシティロースト'),
    ('63526085', 'ブレンド<玄>', None, 'ブレンド', 'イタリアンロースト'),
    ('63526131', 'エチオピア モカクイーン', None, None, 'フルシティロースト'),
    ('63526164', 'タンザニアAA(キリマンジャロ)', None, None, 'フルシティロースト'),
    ('75228546', 'インドモンスーン', None, None, 'フルシティロースト'),
    ('80832440', 'ブレンド<董>', None, 'ブレンド', 'フルシティロースト'),
    ('80832510', 'ペルー MCM', None, None, 'フルシティロースト'),
    ('80832541', 'コロンビアスプレモ', None, None, 'フルシティロースト'),
    ('80832558', 'ブレンド<和>', None, 'ブレンド', 'フルシティロースト'),
    ('80832709', 'コスタリカ ジャガーハニー', None, None, 'フルシティロースト'),
    ('80832738', 'マンデリンG1', None, None, 'フルシティロースト'),
]

# 産地の上書き(商品ID -> 日本語の国名。None は「商品名と説明で食い違う等で不明」とする)
ORIGIN_OVERRIDES = {}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)")
ROAST_PATTERN = re.compile(r"【焙煎度】\s*([^【\s]+)")


def clean_desc(raw: str) -> str | None:
    import html as _html
    text = _html.unescape(raw)
    text = re.sub(r"\s+", " ", text).strip()
    pass
    return text[:400] or None


def build_record(item_id, name, weight_g, category_override, roast_level):
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    raw_desc = desc_m.group(1) if desc_m else ""
    desc = clean_desc(raw_desc)
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
            parsed["origin_source"] = "raw_name" if ORIGIN_OVERRIDES[item_id] else None

    if not roast_level:
        import html as _html
        roast_m = ROAST_PATTERN.search(re.sub(r"\s+", "", _html.unescape(raw_desc)))
        roast_level = roast_m.group(1) if roast_m else None
    if not roast_level:
        roast_level = parsed["roast_level"]

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level,
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
    for index, (item_id, name, weight_g, category_override, roast_level) in enumerate(ITEMS):
        if index:
            time.sleep(REQUEST_INTERVAL)
        try:
            record = build_record(item_id, name, weight_g, category_override, roast_level)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_beanswaraku.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_beanswaraku.json に出力しました")


if __name__ == "__main__":
    main()
