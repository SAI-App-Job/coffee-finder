# -*- coding: utf-8 -*-
"""
scrape_vengacoffee.py

VENGA!COFFEE(https://vengacoffee.thebase.in/、福井県福井市宝永3丁目15-10)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(福井県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): 全41商品のうちドリップバッグ・水出しアイスコーヒーパック・器具・雑貨・配送オプションを除いたコーヒー豆19銘柄(ブレンド7・ストレート12、デカフェ1含む)。期間限定3種も販売中のため収録。商品ページ・/aboutに内容量の記載が無い(/aboutに「100gから販売」とのみ)ため重量はNone。価格は商品ページ(豆のまま/挽き方バリエーション共通)の表示価格
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している
(焙煎度が明示できない商品は商品説明の記述から補う)。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import json
import re

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "VENGA!COFFEE",
    "url": "https://vengacoffee.thebase.in/",
    "platform": "BASE",
    "address": "福井県福井市宝永3丁目15-10",
    "prefecture": "福井県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://vengacoffee.thebase.in"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('78458921', '秋味ブレンド(期間限定)', None, None, None),
    ('69511882', 'インド ごくぶか(期間限定)', None, 'ストレート', '深煎り'),
    ('105672097', '「フェスでコーヒー」ブレンド(期間限定)', None, 'ブレンド', '中深煎り'),
    ('28654509', 'ヴェンガブレンド', None, 'ブレンド', None),
    ('28654612', 'リッチブレンド', None, 'ブレンド', '深煎り'),
    ('28654660', '福の豆ブレンド', None, 'ブレンド', None),
    ('28654712', 'アフリカングリーンブレンド', None, 'ブレンド', None),
    ('28654155', '東ティモール ウォッシュド', None, None, '中煎り'),
    ('28654089', 'エチオピア イルガチェフ ナチュラル', None, None, '中煎り'),
    ('28654208', 'ブラジル', None, None, '中煎り'),
    ('28655291', 'カフェインレス メキシコ', None, None, '中深煎り'),
    ('28713265', 'パプアニューギニア', None, None, '中深煎り'),
    ('28713335', 'グアテマラ', None, None, '中深煎り'),
    ('28713378', 'コロンビア', None, None, '中深煎り'),
    ('28713414', 'エルサルバドル', None, None, '中深煎り'),
    ('28713487', 'タンザニア', None, None, '中深煎り'),
    ('28653673', 'マンデリン', None, None, '深煎り'),
    ('28653740', 'ケニア', None, None, '深煎り'),
    ('28653595', 'インド', None, None, '深煎り'),
]

# coffee_parser.pyの国名辞書で検出できない表記(「タイ」「中国」「ケニヤ」等)の産地を明示する
ORIGIN_OVERRIDES = {}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id: str, name: str, weight_g: int, category_override: str | None, roast_level: str | None) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    desc = re.sub(r"\s+", " ", desc_m.group(1)).strip() if desc_m else None
    if desc:
        desc = re.split(r"コーヒー豆[４4]００ｇ|※数量1で|100g以上ご購入|100g単位|送料無料でお届け", desc)[0].strip()[:400] or None
    price_m = PRICE_PATTERN.search(html_text)
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    sold_out = bool(purchasability_m) and purchasability_m.group(1) == "unpurchasable"

    desc_roast = None
    if desc:
        rm = re.search(r"(中深煎り|中浅煎り|深煎り|中煎り|浅煎り)", desc)
        desc_roast = rm.group(1) if rm else None
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
        "roast_level": roast_level or parsed["roast_level"] or desc_roast,
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
    with open("data_vengacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_vengacoffee.json に出力しました")


if __name__ == "__main__":
    main()
