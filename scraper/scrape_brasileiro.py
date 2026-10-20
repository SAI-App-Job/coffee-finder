# -*- coding: utf-8 -*-
"""
scrape_brasileiro.py

ブラジレイロ(https://brasileiro.base.shop/、福岡県福岡市博多区店屋町1-20)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(福岡県)のモール出店・独自EC調査で発見。

【対象商品について】
実データ確認済み(2026-10時点): BASE全17商品のうち自家焙煎のコーヒー豆6銘柄(200g、豆のまま/ドリップ用に挽く/渋皮除去まで から選択。豆のままの価格)。リキッドアイスコーヒー・カフェオーレシロップ・保存缶・ドリップバッグ・ギフトセット・紅茶リーフは除外。焙煎度は商品説明に「深煎りのコーヒーの為渋皮除去を行わない」とある4銘柄のみ深煎りとし、記載のないマイルド/カリブの華は不明(null)。
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している
(商品ページのタイトル表記とは別に、分類・焙煎度を確認して補っている)。
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
    "name": "ブラジレイロ",
    "url": "https://brasileiro.base.shop/",
    "platform": "BASE",
    "address": "福岡県福岡市博多区店屋町1-20",
    "prefecture": "福岡県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
    "source_note": '販売先BASE(https://brasileiro.base.shop/)の全商品を2026-10-20に確認。公式サイト https://fbrs800.gorp.jp/ に「味わい深い自家焙煎の本格珈琲」、住所「福岡県福岡市博多区店屋町1-20」(呉服町駅徒歩2分、月〜土10:00-19:00、日祝休)の記載あり。1934年創業の喫茶店(屋号:カフェ ブラジレイロ)。',
    "last_verified_at": "2026-10-20",
}

BASE_URL = "https://brasileiro.base.shop"
REQUEST_INTERVAL = 5  # BASEは5秒以上の間隔を空ける
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('46118985', 'マイルドブレンド', 200, 'ブレンド', None),
    ('46504009', 'クラシックブレンド', 200, 'ブレンド', '深煎り'),
    ('46503892', 'カリブの華', 200, 'ブレンド', None),
    ('58113493', 'メッツェンブレンド', 200, 'ブレンド', '深煎り'),
    ('58113044', 'ベネチアンブレンド', 200, 'ブレンド', '深煎り'),
    ('50398957', 'アステカの貴婦人', 200, None, '深煎り'),
]

# coffee_parser.pyの国名辞書で検出できない表記(「タイ」「中国」「ケニヤ」等)の産地を明示する
ORIGIN_OVERRIDES = {'50398957': 'メキシコ'}

# 商品説明に発送案内の定型文が長く含まれる店は、説明を短い要約で置き換える
DESC_OVERRIDES = {'46118985': 'ブラジレイロのオリジナルブレンド。酸味と苦味のバランスのコーヒー。', '46504009': 'ブラジレイロのオリジナルブレンド。スッキリした苦味とコクのあるコーヒー。', '46503892': 'ブラジレイロのオリジナルブレンド。華やかな甘みと軽やかな香りのコーヒー。', '58113493': 'ブラジレイロのオリジナルブレンド。ドイツ語で若い女性という意味を冠した厳選ブレンド。チョコレートと味わうとより一層きわだつ。', '58113044': 'ブラジレイロのオリジナルブレンド。当店のブレンドで一番の深煎り。まろやかな苦みと独特の香りが特徴。アイスコーヒーにも。', '50398957': '高品質なメキシコのコーヒー。芳醇なアロマと甘味。華麗な味わい。使用豆:メキシコ チアパス クステペック農園。'}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id: str, name: str, weight_g: int, category_override: str | None, roast_level: str | None) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    desc = re.sub(r"\s+", " ", desc_m.group(1)).strip()[:400] if desc_m else None
    if item_id in DESC_OVERRIDES:
        desc = DESC_OVERRIDES[item_id]
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
        time.sleep(REQUEST_INTERVAL)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_brasileiro.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_brasileiro.json に出力しました")


if __name__ == "__main__":
    main()
