# -*- coding: utf-8 -*-
"""
scrape_alohabeans.py

ALOHA BEANS(https://alohabeans.theshop.jp/、神奈川県横浜市金沢区釜利谷東6-1-18)の商品情報を取得する。BASE(https://alohabeans.theshop.jp)。

【店舗発見の経緯】
神奈川県の新規発掘調査(2026-10-21)で発見。

【対象商品について】
実データ確認済み(2026-10時点): 全商品が200g表記のため200gを代表とする(100gの設定なし)。焙煎度は購入者がハイ〜フルシティ等から選択する方式のため未設定(null)。ドリップバッグ・器具は除外。販売中/品切れはitem_purchasabilityに従う。セール表示の商品は現行価格。
商品名・重量・産地・分類は、商品ページの表記を確認したうえで下のITEMSに明示している。
価格(割引表示がある場合は割引後の販売価格)・在庫(item_purchasability)・説明(og:description)・
焙煎度(ページ内の「■ロースト」等の表記。ITEMSで明示した場合はそちらを優先)は商品ページから取得する。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用し、リクエスト間隔は5秒以上とする。
"""

import html
import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "ALOHA BEANS",
    "url": "https://alohabeans.theshop.jp/",
    "platform": "BASE",
    "address": "神奈川県横浜市金沢区釜利谷東6-1-18",
    "prefecture": "神奈川県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
    "source_note": "https://alohabeans.theshop.jp/law (事業者所在地・営業時間10:00〜16:00・定休火水)、/about (店内・小型焙煎機による注文焙煎・電話番号掲載)、各商品ページを2026-10-20に確認。ブログ最新は2026-09-04。",
    "last_verified_at": "2026-10-20",
}

BASE_URL = "https://alohabeans.theshop.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL_SEC = 5

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneならページから判定), 産地(ブレンドはNone))
ITEMS = [   ('8458509', 'ブラジル ショコラ ピーベリー', 200, None, None, 'ブラジル'),
    ('100237524', 'デカフェ エチオピア シャキッソ TADE GG ナチュラル', 200, None, None, 'エチオピア'),
    ('155456152', 'ケニア カリンドゥンドゥAA', 200, None, None, 'ケニア'),
    ('2155294', 'エチオピア イルガチェフェ チェルチェレ ナチュラル', 200, None, None, 'エチオピア'),
    ('77728475', 'タンザニア スノートップ', 200, None, None, 'タンザニア'),
    ('67922319', 'コロンビア ナリーニョ・スプレモ', 200, None, None, 'コロンビア'),
    ('108903648', 'グアテマラ ラ・プリマベーラ ナチュラル', 200, None, None, 'グアテマラ'),
    ('30462895', 'エルサルバドル カフェ パカスSHG', 200, None, None, 'エルサルバドル'),
    ('157750867', 'インドネシア トラジャ ランテカルア', 200, None, None, 'インドネシア'),
    ('152616613', 'インドネシア バリ アラビカ ブルームーン', 200, None, None, 'インドネシア'),
    ('29331816', 'インド メルティマウンテン ロブスタハニー', 200, None, None, 'インド'),
    ('90182553', '秋のホイホイブレンド', 200, 'ブレンド', None, None),
    ('135562257', 'マイルドKopeブレンド', 200, 'ブレンド', None, None),
    ('135562353', 'ビターKopeブレンド', 200, 'ブレンド', None, None)]

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
DISCOUNT_PATTERN = re.compile(r"¥\s*([\d,]+)\s*\d+%\s*OFF\s*¥\s*([\d,]+)")
ROAST_PATTERNS = [
    re.compile(r"■\s*ロースト\s*(極深煎り|中深煎り|中浅煎り|浅煎り|中煎り|深煎り)"),
    re.compile(r"(極深煎り|中深煎り|中浅煎り|浅煎り|中煎り|深煎り)に(?:仕上げ|焙煎)"),
]


def page_text(html_text: str) -> str:
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", html_text, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    return html.unescape(re.sub(r"\s+", " ", t))


def build_record(item_id: str, name: str, weight_g: int, category_override, roast_override, origin) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    if resp.status_code != 200:
        print(f"[warn] HTTP {resp.status_code}: item_id={item_id}")
        return None
    html_text = resp.text
    text = page_text(html_text)

    desc_m = DESC_PATTERN.search(html_text)
    desc = re.sub(r"\s+", " ", html.unescape(desc_m.group(1))).strip()[:400] if desc_m else None
    price_m = PRICE_PATTERN.search(html_text)
    price = int(price_m.group(1)) if price_m else None
    disc_m = DISCOUNT_PATTERN.search(text)
    if disc_m:  # 割引表示(例: ¥1,200 10%OFF ¥1,080)がある場合は割引後の販売価格
        price = int(disc_m.group(2).replace(",", ""))
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    sold_out = bool(purchasability_m) and purchasability_m.group(1) == "unpurchasable"

    roast = roast_override
    if not roast:
        for pat in ROAST_PATTERNS:
            m = pat.search(text)
            if m:
                roast = m.group(1)
                break

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
        if origin:
            parsed["origin_country"] = origin
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
        "roast_level": roast or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/items/{item_id}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item_id, name, weight_g, category_override, roast_level, origin in ITEMS:
        try:
            record = build_record(item_id, name, weight_g, category_override, roast_level, origin)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            record = None
        if record is not None:
            records.append(record)
        time.sleep(REQUEST_INTERVAL_SEC)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_alohabeans.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_alohabeans.json に出力しました")


if __name__ == "__main__":
    main()
