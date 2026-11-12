# -*- coding: utf-8 -*-
"""
scrape_possecoffee.py

POSSE COFFEE(https://possecoffee.base.ec/、福井県坂井市三国町運動公園2-18-20)の商品情報を取得する。BASE(base.ec)。

【店舗発見の経緯】
全国再調査(北陸3県)の新規発掘で発見(2026-11)。

【実店舗・自家焙煎の根拠(2026-11-03確認)】
BASE https://possecoffee.base.ec/about に「福井県坂井市三国町、東尋坊の近くにあるコーヒーショップです。世界各地から届くスペシャリティコーヒーを自家焙煎し販売しています。」「POSSE COFFEE 福井県坂井市三国町運動公園2-18-20 TEL 0776-43-0188」。公式 https://www.possecoffee.com/ にも店舗情報。

【対象商品について】
実データ確認済み(2026-11-03時点): BASEの「コーヒー豆」カテゴリの豆12商品(ブレンド3・シングル8・デカフェ1)。商品説明に「数量1で100gになります」とあるため全て100g価格。定期便(3)・ドリップバッグ・ドリップバッグセット・器具・アイスコーヒー(リキッド)は除外。プレミアムのゲイシャを含む。
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。

【robots.txtについて】
possecoffee.base.ec の robots.txt を2026-11-03に確認。User-Agent: * は /cart/ /web_cart/ /shops/ 等のみ Disallow で、商品ページ(/items/)・カテゴリは許可。
BASEの robots.txt は python-requests/curl 等を個別に Disallow しているため、識別可能な
独自User-Agentを使用し、リクエスト間隔は5秒以上空ける。
"""

import html as html_lib
import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "POSSE COFFEE",
    "url": "https://possecoffee.base.ec/",
    "platform": "BASE",
    "address": "福井県坂井市三国町運動公園2-18-20",
    "prefecture": "福井県",
    "robots_txt_status": "実質許可(2026-11-03確認。Disallowは/cart/等のみ。python-requests/curl等は個別禁止のため識別可能なUser-Agentを使用)",
    "source_note": "https://possecoffee.base.ec/ (BASE商品ページ2026-11-03確認)。毎月20日ごろ発送の定期便告知あり、更新は新しい",
    "last_verified_at": "2026-11-03",
}

BASE_URL = "https://possecoffee.base.ec"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
CRAWL_DELAY_SECONDS = 5

# (商品ID, 商品名, 重量(g)(商品ページに記載が無ければNone), 分類の上書き, 焙煎度(Noneなら商品名から判定))
ITEMS = [('2420629', 'POSSEブレンド', 100, 'ブレンド', 'シティロースト'),
 ('4265344', '雄島-OSHIMA-ブレンド', 100, 'ブレンド', '深煎り'),
 ('8760334', '哥川-KASEN-ブレンド', 100, 'ブレンド', '浅煎り'),
 ('163710176', 'ケニア シンバ ウォッシュト AB', 100, 'ストレート', 'フルシティロースト'),
 ('163711253', '【プレミアム】コロンビア ブエナビスタ農園 ゲイシャ ウォッシュド', 100, 'ストレート', 'ミディアムロースト'),
 ('2426829', 'インドネシア リントン マンデリン バタックブルー', 100, 'ストレート', None),
 ('163710906', 'パプアニューギニア ジワカ ウィルトン農園 ウォッシュト', 100, 'ストレート', 'フルシティロースト'),
 ('2420635', 'ブラジル アルタ・モジアナ ナチュラル', 100, 'ストレート', None),
 ('163710727', 'エチオピア イルガチェフェ アリーチャ レラ ウォッシュト G1', 100, 'ストレート', 'ハイロースト'),
 ('163709916', 'グアテマラ ラス・エスメラルダス＆カサ・ビエハ ウォッシュド', 100, 'ストレート', 'ハイロースト'),
 ('163709890', 'エルサルバドル ロマ・ラ・グロリア パカマラ レッドハニー', 100, 'ストレート', None),
 ('15700572', 'カフェインレスコーヒー豆（Guatemala）', 100, 'デカフェ', None)]

# 産地(日本語の国名)を明示する(ブレンドは対象外)
ORIGIN_OVERRIDES = {'163710176': 'ケニア',
 '163711253': 'コロンビア',
 '2426829': 'インドネシア',
 '163710906': 'パプアニューギニア',
 '2420635': 'ブラジル',
 '163710727': 'エチオピア',
 '163709916': 'グアテマラ',
 '163709890': 'エルサルバドル',
 '15700572': 'グアテマラ'}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id: str, name: str, weight_g: int | None, category_override: str | None, roast_level: str | None) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    desc = None
    if desc_m:
        desc = re.sub(r"\s+", " ", html_lib.unescape(desc_m.group(1))).strip()[:400] or None
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


def scrape_all_products() -> list[dict]:
    records = []
    for i, (item_id, name, weight_g, category_override, roast_level) in enumerate(ITEMS):
        if i:
            time.sleep(CRAWL_DELAY_SECONDS)
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
    with open("data_possecoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_possecoffee.json に出力しました")


if __name__ == "__main__":
    main()
