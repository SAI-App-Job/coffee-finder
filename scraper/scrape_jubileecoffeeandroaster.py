# -*- coding: utf-8 -*-
"""
scrape_jubileecoffeeandroaster.py

Jubilee Coffee and Roaster(https://jubilee.thebase.in/、東京都港区白金台3-18-10 1F)の商品情報を取得する。BASE。

【対象商品について】
実データ確認済み(2026-10-25時点): BASE全22件のうち自家焙煎のコーヒー豆13銘柄(200g。ブレンド3・シングル9・デカフェ1。同一産地の焙煎度違いは別銘柄)。リキッドアイスコーヒー・ドリップバッグ・ラッピング・クール便チケット・HARIOフィルターは除外。
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
    "name": "Jubilee Coffee and Roaster",
    "url": "https://jubilee.thebase.in/",
    "platform": "BASE",
    "address": "東京都港区白金台3-18-10 1F",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用、間隔5秒以上)",
    "source_note": "BASE(https://jubilee.thebase.in/)の商品一覧と各商品ページ、公式サイト http://jubilee-coffee.jp/about/ (「毎日、店内でコーヒー豆を丁寧に焙煎しています」)を2026-10-25に確認。住所は食べログ・公式Access表記。",
    "last_verified_at": "2026-10-25",
}

BASE_URL = "https://jubilee.thebase.in"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL_SEC = 5.0
DEFAULT_WEIGHT_G = 200

# (商品ID, 商品名, 分類(None=自動判定), 産地の上書き(None=商品名から判定), 焙煎度(None=商品ページから判定))
ITEMS = [
    ('102520', 'ジュビリーブレンド#50（シティ）', 'ブレンド', None, '中深煎り'),
    ('102522', 'ジュビリーブレンド#75（フレンチ）', 'ブレンド', None, '深煎り'),
    ('46153178', 'ジュビリーブレンド アイスコーヒー（フレンチ）', 'ブレンド', None, '深煎り'),
    ('84519859', 'エチオピア イルガチェフェ ウォテ2300（ミディアム）Washed', None, None, '中浅煎り'),
    ('146005849', 'ケニア ギチャサイニファクトリー （ハイ）', None, None, '中浅煎り'),
    ('72982452', 'エチオピア イルガチェフェ ウォテ2300（シティ）Natural', None, None, '中深煎り'),
    ('163096479', 'ペルー フェスパ農園 ジャバ（シティ）', None, None, '中深煎り'),
    ('4668516', 'グアテマラ サンタカタリーナ農園（シティ）', None, None, '中深煎り'),
    ('141955602', '【DECAF】メキシコ サン・フェルナンド（シティ）', 'デカフェ', None, '中深煎り'),
    ('146003420', 'ケニア ギチャサイニファクトリー （フレンチ）', None, None, '深煎り'),
    ('716634', 'ペルー フェスパ農園 ブルボン種（フレンチ）', None, None, '深煎り'),
    ('25131175', 'インドネシア オナンガンジャン マンデリン（フレンチ）', None, None, '深煎り'),
    ('81923808', 'ブラジル マカウバ・デ・シーマ農園（フレンチ）', None, None, '深煎り'),
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
    return {"desc": og_desc(html_text)}


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
    with open("data_jubileecoffeeandroaster.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_jubileecoffeeandroaster.json に出力しました")


if __name__ == "__main__":
    main()
