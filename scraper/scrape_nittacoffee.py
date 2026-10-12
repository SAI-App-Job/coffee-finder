# -*- coding: utf-8 -*-
"""
scrape_nittacoffee.py

新田珈琲(https://base.nittacoffee.com/、福井県敦賀市本町1-11-3)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(福井県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): 全72ページのうち、豆の22商品(シングル13種・ブレンド9種)を収録。重量は商品ごとに固定(多くは200g、ゲイシャ等は100g/50g)で、挽き方のみバリエーション。
コーヒーバッグ・セット・ギフト・ドリンク・羊羹・定期便・卸/個人専用ページ・インフューズド(コロンビア Exotic ピーチ)は除外。
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している
(重量違いの別ページ登録・商品ページごとに重量が異なるため)。
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
    "name": "新田珈琲",
    "url": "https://base.nittacoffee.com/",
    "platform": "BASE",
    "address": "福井県敦賀市本町1-11-3",
    "prefecture": "福井県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://base.nittacoffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [('155937044', 'コロンビア CGLE ラス・マルガリータス農園 ゲイシャ ウォッシュ エクセルソ', 100, None, None),
 ('124174745', 'グァテマラ【ゲイシャ】フィラデルフィア農園 Fully Washed', 100, None, None),
 ('145122494', 'アロマ・ナティボ ゲイシャ 712 LCT(コロンビア/ハニー・乳酸発酵)', 50, None, 'ハイロースト'),
 ('144511919', 'ルワンダ ガコ農園 ウォッシュド', 200, None, '中浅煎り'),
 ('140081187', 'ブラジル セラード ホリゾンティーナ農園 樹上完熟ナチュラル', 200, None, None),
 ('153724950', 'エチオピア ウォッシュド(Yirgacheffe Genesis Washed / Grade 1)', 200, None, None),
 ('97070135', 'ケニア ガタイティ AA', 200, None, '中煎り'),
 ('95967163', 'タンザニア ンベヤ アフリカンキャノピー ウォッシュ AA【キリマンジャロ】', 200, None, '中煎り'),
 ('25954623', 'カフェインレス(デカフェ)メキシコ', 200, None, 'フレンチロースト'),
 ('88357319', 'コスタリカ ジャガー ハニー SHB', 200, None, None),
 ('69108820', 'コロンビア クラッシック ウイラ', 200, None, None),
 ('27068277', '【天然酵母発酵】ブラジル・ドナネネン・フルッタ', 200, None, 'シティロースト'),
 ('159374133', 'インドネシア マンデリン トバコ G-1', 200, None, '中煎り'),
 ('81023031', 'モカ・ブレンド', 200, 'ブレンド', 'シティロースト'),
 ('63139010', '港 ブレンド', 200, 'ブレンド', '中深煎り'),
 ('27583821', 'マイルドブレンド', 200, 'ブレンド', '中煎り'),
 ('26145280', 'リッチブレンド', 200, 'ブレンド', '中煎り'),
 ('26145259', 'ストロングブレンド', 200, 'ブレンド', None),
 ('26145228', 'ゴールドブレンド', 200, 'ブレンド', '中煎り'),
 ('33108393', '天使の珈琲', 200, 'ブレンド', '中煎り'),
 ('23980471', 'ヨーロピアンブレンド', 200, 'ブレンド', '深煎り'),
 ('23979009', 'イタリアン ブレンド', 200, 'ブレンド', '極深煎り')]

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
    desc = re.sub(r"\s+", " ", re.sub(r"[━]+", " ", desc_m.group(1))).strip()[:400] if desc_m else None
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
    with open("data_nittacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_nittacoffee.json に出力しました")


if __name__ == "__main__":
    main()
