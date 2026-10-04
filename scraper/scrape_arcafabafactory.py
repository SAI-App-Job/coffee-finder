# -*- coding: utf-8 -*-
"""
scrape_arcafabafactory.py

ArcaFabaFactory.(https://arcafaba.base.shop/、大阪府大阪市住之江区浜口西1-6-10)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(大阪府)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): 全46商品のうち、100gの焙煎豆(30銘柄、デカフェ3・ブレンド2を含む)を収録。ドリップバッグ(単品・10個入)とラテベース(液体)は除外。注文後焙煎で焙煎度は購入時に備考欄で指定するため未確定(roast_hintに保持)。
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
    "name": "ArcaFabaFactory.",
    "url": "https://arcafaba.base.shop/",
    "platform": "BASE",
    "address": "大阪府大阪市住之江区浜口西1-6-10",
    "prefecture": "大阪府",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://arcafaba.base.shop"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定), 焙煎度の補足(roast_hint))
ITEMS = [
    ('154393190', 'エチオピア イルガチェフェG1ナチュラル ウォテコンガ', 100, None, None, '注文後焙煎(おすすめの焙煎度で焙煎。浅煎り/中煎り/深煎りは備考欄で指定可)'),
    ('149228403', 'ボリビア コパカバーナ農園', 100, None, None, '注文後焙煎(おすすめの焙煎度で焙煎。浅煎り/中煎り/深煎りは備考欄で指定可)'),
    ('145282288', 'ルワンダ スカイヒル', 100, None, None, '注文後焙煎(おすすめの焙煎度で焙煎。浅煎り/中煎り/深煎りは備考欄で指定可)'),
    ('145280992', 'マラウイ ミスクAA', 100, None, None, '注文後焙煎(おすすめの焙煎度で焙煎。浅煎り/中煎り/深煎りは備考欄で指定可)'),
    ('136151905', 'エスプレッソブレンド', 100, 'ブレンド', None, '注文後焙煎(おすすめの焙煎度で焙煎。浅煎り/中煎り/深煎りは備考欄で指定可)'),
    ('136151296', 'ケニアAA TOP/ダハブフラミンゴ', 100, None, None, '注文後焙煎(おすすめの焙煎度で焙煎。浅煎り/中煎り/深煎りは備考欄で指定可)'),
    ('136150875', 'タンザニア ンゴロンゴロ/アカシアヒルズ農園', 100, None, None, '注文後焙煎(おすすめの焙煎度で焙煎。浅煎り/中煎り/深煎りは備考欄で指定可)'),
    ('114592598', 'ジャマイカ/ブルーマウンテンNO.1 クライスデール地区', 100, None, None, '注文後焙煎(おすすめの焙煎度で焙煎。浅煎り/中煎り/深煎りは備考欄で指定可)'),
    ('114592336', 'ミャンマー/モーテート農園', 100, None, None, '注文後焙煎(おすすめの焙煎度で焙煎。浅煎り/中煎り/深煎りは備考欄で指定可)'),
    ('114592092', 'メキシコ/チアパス トリウンフォヴェルディデカフェ', 100, None, None, '注文後焙煎(おすすめの焙煎度で焙煎。浅煎り/中煎り/深煎りは備考欄で指定可)'),
    ('114591664', 'ブラジル/フルッタメルカドン', 100, None, None, '注文後焙煎(おすすめの焙煎度で焙煎。浅煎り/中煎り/深煎りは備考欄で指定可)'),
    ('114590552', 'ベネズエラ/ムクカイ農園', 100, None, None, '注文後焙煎(おすすめの焙煎度で焙煎。浅煎り/中煎り/深煎りは備考欄で指定可)'),
    ('114590298', 'エチオピア/イルガチェフェG１ドゥメルソ ウォッシュド', 100, None, None, '注文後焙煎(おすすめの焙煎度で焙煎。浅煎り/中煎り/深煎りは備考欄で指定可)'),
    ('93868861', 'アルカファーバ ハウスブレンド', 100, 'ブレンド', None, '注文後焙煎(おすすめの焙煎度で焙煎。浅煎り/中煎り/深煎りは備考欄で指定可)'),
    ('93868848', 'コロンビア/デカフェ ラプラデーラ農園', 100, None, None, '注文後焙煎(おすすめの焙煎度で焙煎。浅煎り/中煎り/深煎りは備考欄で指定可)'),
    ('93868834', 'グァテマラ/アンティグア アゾティア農園', 100, None, None, '注文後焙煎(おすすめの焙煎度で焙煎。浅煎り/中煎り/深煎りは備考欄で指定可)'),
    ('93868821', 'コスタリカ/ジャガーハニー', 100, None, None, '注文後焙煎(おすすめの焙煎度で焙煎。浅煎り/中煎り/深煎りは備考欄で指定可)'),
    ('93868807', 'ケニア/レッドマウンテンAA TOP', 100, None, None, '注文後焙煎(おすすめの焙煎度で焙煎。浅煎り/中煎り/深煎りは備考欄で指定可)'),
    ('93868795', 'メキシコ/エルピラール農園', 100, None, None, '注文後焙煎(おすすめの焙煎度で焙煎。浅煎り/中煎り/深煎りは備考欄で指定可)'),
    ('93868780', 'インドネシア/マンデリン/SGタブー', 100, None, None, '注文後焙煎(おすすめの焙煎度で焙煎。浅煎り/中煎り/深煎りは備考欄で指定可)'),
    ('93868770', 'パプアニューギニア/ハセン農園 天空の森 修道院のコーヒー', 100, None, None, '注文後焙煎(おすすめの焙煎度で焙煎。浅煎り/中煎り/深煎りは備考欄で指定可)'),
    ('93868763', 'ブラジル/キャラメラード', 100, None, None, '注文後焙煎(おすすめの焙煎度で焙煎。浅煎り/中煎り/深煎りは備考欄で指定可)'),
    ('93868753', 'エチオピア/イルガチェフェG１フローラル ナチュラル', 100, None, None, '注文後焙煎(おすすめの焙煎度で焙煎。浅煎り/中煎り/深煎りは備考欄で指定可)'),
    ('93868741', 'コロンビア/パシオンデラシエラ', 100, None, None, '注文後焙煎(おすすめの焙煎度で焙煎。浅煎り/中煎り/深煎りは備考欄で指定可)'),
    ('93868730', 'ルワンダ/ホワイトトップブルボン', 100, None, None, '注文後焙煎(おすすめの焙煎度で焙煎。浅煎り/中煎り/深煎りは備考欄で指定可)'),
    ('93868712', 'インドネシア/バリ アラビカ神山', 100, None, None, '注文後焙煎(おすすめの焙煎度で焙煎。浅煎り/中煎り/深煎りは備考欄で指定可)'),
    ('93868693', 'タンザニア/リビングストン', 100, None, None, '注文後焙煎(おすすめの焙煎度で焙煎。浅煎り/中煎り/深煎りは備考欄で指定可)'),
    ('93868675', 'コスタリカ/フローラルハニーSHB', 100, None, None, '注文後焙煎(おすすめの焙煎度で焙煎。浅煎り/中煎り/深煎りは備考欄で指定可)'),
    ('93868658', 'ペルー/天空のコーヒー', 100, None, None, '注文後焙煎(おすすめの焙煎度で焙煎。浅煎り/中煎り/深煎りは備考欄で指定可)'),
    ('93868641', 'エルサルバドル/エンジェル', 100, None, None, '注文後焙煎(おすすめの焙煎度で焙煎。浅煎り/中煎り/深煎りは備考欄で指定可)'),
]

# coffee_parser.pyの国名辞書で検出できない表記(「タイ」「中国」「ケニヤ」等)の産地を明示する
ORIGIN_OVERRIDES = {'114591664': 'ブラジル', '145280992': 'マラウイ'}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id: str, name: str, weight_g: int, category_override: str | None, roast_level: str | None, roast_hint: str | None) -> dict | None:
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
        "roast_hint": roast_hint,
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
    for item_id, name, weight_g, category_override, roast_level, roast_hint in ITEMS:
        try:
            record = build_record(item_id, name, weight_g, category_override, roast_level, roast_hint)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        if record is not None:
            records.append(record)
        time.sleep(0.5)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_arcafabafactory.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_arcafabafactory.json に出力しました")


if __name__ == "__main__":
    main()
