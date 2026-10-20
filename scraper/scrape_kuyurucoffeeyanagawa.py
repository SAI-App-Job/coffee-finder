# -*- coding: utf-8 -*-
"""
scrape_kuyurucoffeeyanagawa.py

kuyuru coffee(https://kuyurucoffe.thebase.in/、福岡県柳川市三橋町今古賀182-2)の商品情報を取得する。BASE。

【店舗発見の経緯】
楽天/Yahoo!等のモール・独自EC調査の新規発掘。公式サイト https://kuyurucoffee.com/ の「Online Shop」はBASE店への導線(価格表示は古いため採用せず、BASE店の現行価格を採用)。
注意: 佐賀の「kuyuru coffee ootakara」とは別店。

【対象商品について】
実データ確認済み(2026-10時点): BASE店は16商品(ドリップパックセット1を除く豆は8銘柄x100g/200g)。各銘柄の最小重量100gを代表に採用
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している
(商品ページのタイトルがキャッチコピー付き・重量違いの重複登録のため)。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "kuyuru coffee",
    "url": "https://kuyurucoffe.thebase.in/",
    "platform": "BASE",
    "address": "福岡県柳川市三橋町今古賀182-2",
    "prefecture": "福岡県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
    "source_note": "BASE店(https://kuyurucoffe.thebase.in/)の商品ページを2026-10-20に確認(sitemapの商品数16、豆は8銘柄x100g/200g)。"
                   "100gを代表に採用し、200gは除外。コスタリカ ハニーは100g/200gとも品切れ。柳川コーヒー(ブレンド)は豆のまま在庫あり(ペーパードリップ用は在庫なし)。"
                   "公式サイト(https://kuyurucoffee.com/)に住所(柳川市三橋町今古賀182-2、10:00-17:00、月曜定休)、BASEのABOUTに「福岡県柳川市でスペシャリティーコーヒーの自家焙煎をおこなっております」と記載。"
                   "公式サイトのOnline Shopは旧価格・旧商品の表示が残るためBASE店を正とした。",
    "last_verified_at": "2026-10-20",
}

BASE_URL = "https://kuyurucoffe.thebase.in"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ("43696633", "エチオピア イルガチェフェG1 100g", 100, "ストレート", None),
    ("43696712", "東ティモール オーガニック 100g", 100, "ストレート", "中深煎り"),
    ("50188466", "グァテマラ 100g", 100, "ストレート", None),
    ("50188512", "マンデリンG1 100g", 100, "ストレート", None),
    ("50188595", "コスタリカ ハニー 100g", 100, "ストレート", None),
    ("50188636", "ブラジル 100g", 100, "ストレート", None),
    ("50188666", "柳川コーヒー 100g", 100, "ブレンド", None),
    ("50432593", "エチオピア カッファ ゲイシャ 100g", 100, "ストレート", None),
]

# coffee_parser.pyの国名辞書で検出できない表記(「タイ」「中国」「ケニヤ」等)の産地を明示する
ORIGIN_OVERRIDES = {
    "43696712": "東ティモール",
}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id: str, name: str, weight_g: int, category_override: str | None, roast_level: str | None) -> dict | None:
    time.sleep(5)
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    desc = re.sub(r"\s+", " ", desc_m.group(1)).strip() if desc_m else None
    if desc:
        # 送料案内の定型文(1袋〔100g〕の場合は〜/それ以上の場合は〜)を除く
        desc = re.split(r"1袋〔|それ以上の場合は", desc)[0].strip()[:400] or None
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
    for item_id, name, weight_g, category_override, roast_level in ITEMS:
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
    with open("data_kuyurucoffeeyanagawa.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kuyurucoffeeyanagawa.json に出力しました")


if __name__ == "__main__":
    main()
