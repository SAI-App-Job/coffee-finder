# -*- coding: utf-8 -*-
"""
scrape_haracoffeeroastery.py

HARA COFFEE ROASTERY(https://www.coffee-hara.com/、東京都大田区南雪谷2-1-5 安藤ビル1F)の商品情報を取得する。BASE。

【対象商品について】
実データ確認済み(2026-10-25時点): BASE全17件のうち100g単位の焙煎豆15銘柄(ブレンド3・デカフェ1。200g以上は数量を増やす方式)。リキッドアイスコーヒー・保存缶は除外。
商品名・重量・分類・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している。
価格・在庫(item_purchasability)・説明は商品ページから取得する。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用し、リクエスト間隔は5秒以上空ける。
"""

import json
import re
import time
import html as htmllib

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method

SHOP_INFO = {
    "name": "HARA COFFEE ROASTERY",
    "url": "https://www.coffee-hara.com/",
    "platform": "BASE",
    "address": "東京都大田区南雪谷2-1-5 安藤ビル1F",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用、間隔5秒以上)",
    "source_note": "BASE(独自ドメイン https://www.coffee-hara.com/)の商品一覧と各商品ページ、公式サイト https://coffee-hara.com/ (「店内の直火式焙煎機で少量ずつ焙煎」、店舗案内)を2026-10-25に確認。",
    "last_verified_at": "2026-10-25",
}

BASE_URL = "https://www.coffee-hara.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL_SEC = 5.0
DEFAULT_WEIGHT_G = 100

# (商品ID, 商品名, 分類(None=自動判定), 産地の上書き(None=商品名から判定), 焙煎度(None=商品ページから判定))
ITEMS = [
    ('114949383', '【ケニア】プティルージュ（深煎り）', None, None, None),
    ('118204329', '【ブラジル】カフェ・サウダージ（中深煎り）', None, None, None),
    ('118204543', '【ブラジル】カフェ・サウダージ（深煎り）', None, None, None),
    ('124772235', '【グアテマラ】ラス・ヌベス農園 レッドブルボン （中深煎り）', None, None, None),
    ('152497147', '【エチオピア】エチオピア ニグセ・ゲメダ シャンタウェネ ナチュラル（中煎り）', None, None, None),
    ('155836428', '【ウガンダ】マウントエルゴン ブラックハニー（中煎り）', None, None, None),
    ('157557345', '【コロンビア】スウィートベリー（深煎り）', None, None, None),
    ('159377472', '【パナマ】ボルカンバル ガリード農園（中煎り）', None, None, None),
    ('159377539', '【パナマ】ボルカンバル ガリード農園（深煎り）', None, None, None),
    ('161498878', '【インドネシア】マンデリン ジョネル農園（深煎り）', None, None, None),
    ('53971502', 'はらブレンド（深煎り）', 'ブレンド', None, None),
    ('53972438', '雪が谷ブレンド（中深煎り）', 'ブレンド', None, None),
    ('53972495', 'モカブレンド（中煎り）', 'ブレンド', None, None),
    ('58044284', '【カフェインレス】グアテマラ (中深煎り)', 'デカフェ', 'グアテマラ', None),
    ('91252646', '【エチオピア】ケビルゲイシャ農園 ゲイシャ （中煎り）', None, None, None),
]

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
ROAST_WORDS = ["中浅煎り", "中深煎り", "浅煎り", "深煎り", "中煎り"]


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("　", " ")).strip()


def page_text(html_text: str) -> str:
    txt = re.sub(r"<script.*?</script>|<style.*?</style>", "", html_text, flags=re.S)
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", txt)))


def og_desc(html_text: str) -> str | None:
    m = DESC_PATTERN.search(html_text)
    return htmllib.unescape(clean(m.group(1)))[:400] if m else None


def extract(html_text: str, name: str) -> dict:
    d = og_desc(html_text)
    out = {"desc": d}
    m = re.search(r"精製\s*：\s*([^□\s]+)", d or "")
    if m:
        out["processing"] = detect_processing_method(m.group(1))
    for w in ROAST_WORDS:
        if w in name:
            out["roast"] = w
            break
    return out


def build_record(item_id: str, name: str, category_override, origin_override, roast_level) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    html_text = resp.text

    price_m = PRICE_PATTERN.search(html_text)
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    sold_out = bool(purchasability_m) and purchasability_m.group(1) == "unpurchasable"
    extra = extract(html_text, name)

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
        elif not parsed["origin_country"] and extra.get("origin"):
            parsed["origin_country"] = extra["origin"]
            parsed["origin_source"] = "description"

    processing = parsed["processing_method"] or extra.get("processing")
    roast = roast_level or extra.get("roast") or parsed["roast_level"]

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": roast,
        "roast_hint": None,
        "flavor_notes": extra.get("desc"),
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price_m.group(1)) if price_m else None,
        "weight_g": DEFAULT_WEIGHT_G,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/items/{item_id}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item_id, name, category_override, origin_override, roast_level in ITEMS:
        try:
            record = build_record(item_id, name, category_override, origin_override, roast_level)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            record = None
        time.sleep(REQUEST_INTERVAL_SEC)
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_haracoffeeroastery.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_haracoffeeroastery.json に出力しました")


if __name__ == "__main__":
    main()
