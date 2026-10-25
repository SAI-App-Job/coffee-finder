# -*- coding: utf-8 -*-
"""
scrape_matsuishoten.py

自家焙煎珈琲 松井商店(https://dazaicoffee.theshop.jp/、東京都三鷹市下連雀2-16-9)の自家焙煎コーヒー豆の商品情報を取得する。BASE(theshop.jp)。

【店舗の実在確認(2026-10-25)】
公式ショップ about(https://dazaicoffee.theshop.jp/about)「三鷹の下連雀通りにある、自家焙煎珈琲 松井商店です」「厳選した豆を最新式の自家焙煎機で丁寧につくった…ご注文後、生豆からお好みの焙煎で」
「〒181-0013 東京都三鷹市下連雀2-16-9 電話0422-47-2303」。第三者: 中央ベストホーム(https://www.chuo-besthome.co.jp/local/dazaicoffee/)
「見せる焙煎機」、旧店舗は下連雀2-16-10で2025年3月に新店舗へ移転(BASEのshop表記2-16-9が移転後の住所と推定)。

【対象商品について】
実データ確認済み(2026-10-25): 商品ページ32件(sitemap.xml)のうち、200g入り豆単品15件(商品名に「200g」表記。粉か豆かを選べる商品は豆のままの前提で同一価格)。焙煎度は購入時に客が選ぶためroast_levelはNone。
デカフェ「コロンビア」は商品名がコロンビア、説明文がグアテマラ生豆と食い違うため産地はNone。
除外: Dazai COFFEE 500g(200gを代表)、赤缶(ギフト缶)、ドリップコーヒー各種、水出しパック、各種セット・詰め合わせ。
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
    "name": "自家焙煎珈琲 松井商店",
    "url": "https://dazaicoffee.theshop.jp/",
    "platform": "BASE(theshop.jp)",
    "address": "東京都三鷹市下連雀2-16-9",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-10-25確認。BASE共通の記述でpython-requests/curl等は個別にDisallow、User-agent: * では商品ページ(/items/)は許可。識別可能なUser-Agentを使用)",
    "source_note": "公式ショップ about・特商法・商品ページ(sitemap.xmlの/items/全32件)を2026-10-25に確認。トップの休業告知が「8月9日〜8月16日 年末年始休業」と古い文言のまま。2025年3月に隣へ移転(住所はBASE記載の2-16-9を採用)。別途Yahoo!ショッピング(store.shopping.yahoo.co.jp/dazaicoffee/)にも出店。",
    "last_verified_at": "2026-10-25",
}

BASE_URL = "https://dazaicoffee.theshop.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 5

# (商品ID, 商品名, 重量(g)またはNone, 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら説明文→商品名の順で判定))
ITEMS = [
    ('44230006', 'Dazai COFFEE', 200, 'ブレンド', None),
    ('44237387', '松井商店特選ブレンド', 200, 'ブレンド', None),
    ('44238081', 'エチオピア ゲイシャ', 200, None, None),
    ('48215809', 'ブラジル ブルボン アマレーロ', 200, None, None),
    ('48224732', 'ブラジル ショコラ ピーベリー', 200, None, None),
    ('48225649', 'グアテマラ アンティグア SUB', 200, None, None),
    ('48314760', 'ブラジル プレミアムショコラ', 200, None, None),
    ('48314933', 'マンデリン ビンタンリマ', 200, None, None),
    ('48315135', 'マンデリン G1', 200, None, None),
    ('48315332', 'エチオピア イルガチャフィー ベレカ G1', 200, None, None),
    ('48341076', 'タンザニア キゴマ ディープブルーAA', 200, None, None),
    ('48341768', 'モカマタリ', 200, None, None),
    ('48345539', 'コロンビア マグダレナ SUP(スプレモ)', 200, None, None),
    ('48346302', 'デカフェ コロンビア', 200, None, None),
    ('48347315', '連雀通りブレンド', 200, 'ブレンド', None),
]

# 産地の上書き(商品ID -> 日本語の国名。None は「商品名と説明で食い違う等で不明」とする)
ORIGIN_OVERRIDES = {'48346302': None}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)")
ROAST_PATTERN = re.compile(r"【焙煎度】\s*([^【\s]+)")


def clean_desc(raw: str) -> str | None:
    import html as _html
    text = _html.unescape(raw)
    text = re.sub(r"\s+", " ", text).strip()
    pass  # 説明文は短く定型文もないためそのまま先頭400字
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
    with open("data_matsuishoten.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_matsuishoten.json に出力しました")


if __name__ == "__main__":
    main()
