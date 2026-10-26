# -*- coding: utf-8 -*-
"""
scrape_mountainibaraki.py

珈琲豆焙煎所 mountain(https://mountain.base.shop/、大阪府茨木市沢良宜西1丁目19番14号)の商品情報を取得する。BASE(https://mountain.base.shop)。

【店舗発見の経緯】
大阪府の新規発掘調査(2026-10-26)で発見。

【対象商品について】
実データ確認済み(2026-10時点): BASE全32商品のうち自家焙煎のコーヒー豆15銘柄(ブレンド6・ストレート9)。同一銘柄が100g/200gの別商品で並ぶため最小の100gを代表に収録。ドリップパック・水出しコーヒーパック・ギフトセット・雑貨・作品は除外。なお高槻市の「MOUNTAIN 1999 自家焙煎コーヒーマウンテン」(mountain1999.com)とは別店舗。
商品名・重量・産地・分類は、商品ページの表記を確認したうえで下のITEMSに明示している。
価格・在庫(item_purchasability)・説明(og:description)・
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
    "name": "珈琲豆焙煎所 mountain",
    "url": "https://mountain.base.shop/",
    "platform": "BASE",
    "address": "大阪府茨木市沢良宜西1丁目19番14号",
    "prefecture": "大阪府",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
    "source_note": "https://mountain.base.shop/p/00001 (ACCESS:大阪府茨木市沢良宜西1丁目19番14号、営業時間8:00〜16:00)、/about (「阪急電鉄京都線南茨木駅より徒歩約5分の焙煎所」「そのころから自家焙煎をスタート」)、ごーがいネット摂津 https://settsu.goguynet.jp/2018/07/23/oasters-mountain/ (「お店で自家焙煎をされています」「年季が入った自家焙煎機」)、各商品ページを2026-10-26に確認。高槻市の「MOUNTAIN 1999」とは別店舗。",
    "last_verified_at": "2026-10-26",
}

BASE_URL = "https://mountain.base.shop"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL_SEC = 5

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneならページから判定), 産地(ブレンドはNone))
ITEMS = [('43303621', '沢良宜ブレンド マイルド', 100, 'ブレンド', '中煎り〜深煎り', None),
    ('9728103', '沢良宜ブレンド ストロング', 100, 'ブレンド', '中煎り〜深煎り', None),
    ('9728135', '沢良宜ブレンド アメリカン', 100, 'ブレンド', '中煎り', None),
    ('9758539', 'フレンチローストブレンド', 100, 'ブレンド', '深煎り', None),
    ('9758521', 'モカモカ(モカ中煎り+深煎りブレンド)', 100, 'ブレンド', '中煎り〜深煎り', None),
    ('86992495', 'アイスコーヒーブレンド(夏季限定)', 100, 'ブレンド', '深煎り', None),
    ('9728159', 'ブラジル サントスNo.2 S18', 100, None, '中煎り', 'ブラジル'),
    ('9728182', 'コロンビア スプレモ', 100, None, '中煎り', 'コロンビア'),
    ('9728278', 'モカ イルガチャフェ', 100, None, '中煎り', 'エチオピア'),
    ('9728300', 'キリマンジャロ タンザニアAA', 100, None, '中煎り', 'タンザニア'),
    ('92969557', 'ペルー マチュピチュ', 100, None, '中深煎り', 'ペルー'),
    ('9728222', 'マンデリンG1 マイルド', 100, None, '中煎り', 'インドネシア'),
    ('9728231', 'マンデリンG1 ストロング', 100, None, '中深煎り', 'インドネシア'),
    ('9728253', 'グァテマラ SHB ウエウエテナンゴ マイルド', 100, None, '中煎り', 'グアテマラ'),
    ('9728261', 'グァテマラ SHB ウエウエテナンゴ ストロング', 100, None, '中深煎り〜深煎り', 'グアテマラ')]

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
    with open("data_mountainibaraki.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mountainibaraki.json に出力しました")


if __name__ == "__main__":
    main()
