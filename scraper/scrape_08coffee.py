# -*- coding: utf-8 -*-
"""
scrape_08coffee.py

08COFFEE(https://08coffee.thebase.in/、秋田県秋田市山王新町13-21 三栄ビル2F)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(秋田県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): BASE全55商品のうち自家焙煎のコーヒー豆15銘柄(公式サイト 08coffee.jp はBASEストアへ誘導)。
同一銘柄が200g/500gで別ページの場合は小さい200gを代表とし、ゲイシャのみ100gのみの販売。
ドリップ/コーヒーバッグ・アイスコーヒー・カフェオレベース・ギフト・セット・定期便・チョコ・雑貨は除外。
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している
(商品ページのタイトルが人気順ラベル付き・重量違いの重複登録のため)。
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
    "name": "08COFFEE",
    "url": "https://08coffee.thebase.in/",
    "platform": "BASE",
    "address": "秋田県秋田市山王新町13-21 三栄ビル2F",
    "prefecture": "秋田県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://08coffee.thebase.in"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('91365', 'ブラジル マカウバデシーマ農園 中煎り', 200, None, '中煎り'),
    ('91375', 'ケニア カサクワ・ファクトリー 深煎り', 200, None, '深煎り'),
    ('4508336', 'ケニア カサクワ・ファクトリー 中煎り', 200, None, '中煎り'),
    ('91377', 'インドネシア オナンガンジャン マンデリン 深煎り', 200, None, '深煎り'),
    ('92225', 'BLEND No.7 浅煎り', 200, 'ブレンド', '浅煎り'),
    ('92226', 'BLEND No.8 中煎り', 200, 'ブレンド', '中煎り'),
    ('92227', 'BLEND No.9 深煎り', 200, 'ブレンド', '深煎り'),
    ('204574', '僕のケニア 中深煎り', 200, 'ブレンド', '中深煎り'),
    ('4508417', '【カフェインレス】メキシコ チアパス州 フライレスカ地区 中煎り', 200, 'デカフェ', '中煎り'),
    ('4508473', 'はつ恋 イルガチェフェ 浅煎り', 200, 'ブレンド', '浅煎り'),
    ('24152904', 'ショコラ！ショコラ！ 深煎り', 200, 'ブレンド', '深煎り'),
    ('56000657', '季節のブレンド MOON 深煎り', 200, 'ブレンド', '深煎り'),
    ('76961827', 'エチオピア グジ ハンベラ ナチュラル 浅煎り', 200, None, '浅煎り'),
    ('86741650', 'グァテマラ サンタカタリーナ農園 ピーベリー 中煎り', 200, None, '中煎り'),
    ('86741691', 'グァテマラ サンタカタリーナ農園 ピーベリー 深煎り', 200, None, '深煎り'),
    ('69566920', 'ゲイシャ アルトス・デル・アベホナル マイクロミル 浅煎り', 100, 'ストレート', '浅煎り'),
]

# coffee_parser.pyの国名辞書で検出できない表記(「タイ」「中国」「ケニヤ」等)の産地を明示する
ORIGIN_OVERRIDES = {'4508417': 'メキシコ', '69566920': 'コスタリカ'}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id: str, name: str, weight_g: int, category_override: str | None, roast_level: str | None) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    desc = re.sub(r"\s+", " ", desc_m.group(1)).strip()[:400] if desc_m else None
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
    with open("data_08coffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_08coffee.json に出力しました")


if __name__ == "__main__":
    main()
