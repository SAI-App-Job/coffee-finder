# -*- coding: utf-8 -*-
"""
scrape_coffeefuku.py

珈琲福(https://coffeefuku.thebase.in/、神奈川県川崎市幸区小倉2-11-12)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(神奈川県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10-21時点): 全25商品のうち、福ブレンド・クリアブレンド・さわやかブレンド・アイスコーヒーブレンドと単品(シングル)9銘柄の計13商品を収録。各銘柄の最小重量の商品(ブレンド300g・シングル200g)を代表とし、福ブレンド500g、お試し3種・飲み比べセット、ドリップバッグ、水出しバッグ、定期便、靴下セットは対象外。「豆のまま」バリエーションが在庫なし(粉のみ在庫あり)の商品は品切れ扱いとした。焙煎度は商品名・説明文に1つに特定できる表記があるものだけ設定(単品の多くは中煎り〜深煎りを選択制のため未設定)。
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。
BASEの商品ページは1商品1価格(バリエーションは在庫のみ)のため、価格は商品ページの表示価格をそのまま採用する。

【実店舗・自家焙煎の根拠】
公式ABOUT「神奈川県川崎市にある小さな小さな焙煎所にて上質な珈琲豆を少量ずつ丁寧に焙煎・選定し」「川崎市幸区の住宅地に焙煎工房直売所＆週末カフェをオープンしました」、特商法「自家焙煎工房を日曜日～火曜日にオープンしており、ご注文をお受けしてから焙煎」(https://coffeefuku.thebase.in/about , /law 2026-10-21確認)。第三者サイトでは実店舗の記載を確認できなかった。住所は特商法の事業者所在地(幸区小倉2-11-12)。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用し、リクエスト間隔を5秒以上空ける。
"""

import html as html_lib
import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "珈琲福",
    "url": "https://coffeefuku.thebase.in/",
    "platform": "BASE",
    "address": "神奈川県川崎市幸区小倉2-11-12",
    "prefecture": "神奈川県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
    "source_note": "BASE(https://coffeefuku.thebase.in/)のsitemap.xmlの全商品ページとABOUT・特商法ページを2026-10-21に確認。各商品の最終更新は2026-08〜2026-10(sitemap lastmod)。住所は特商法の事業者所在地",
    "last_verified_at": "2026-10-21",
}

BASE_URL = "https://coffeefuku.thebase.in"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL_SEC = 5.0

# (商品ID, 商品名, 重量(g)(不明はNone), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名・説明文から判定))
ITEMS = [
    ('81025340', '福ブレンド', 300, 'ブレンド', None),
    ('110905094', 'クリアブレンド（コロンビア、エチオピア他）', 300, 'ブレンド', None),
    ('152751120', 'さわやかブレンド（ブラジル、エチオピア）', 300, 'ブレンド', None),
    ('86624503', 'アイスコーヒーブレンド', 300, 'ブレンド', '極深煎り'),
    ('110904226', 'ブラジル モジアナ/スールデミナス', 200, None, None),
    ('152747982', 'コロンビア', 200, None, None),
    ('75719622', 'エチオピア モカ イルガチェフェG1 コチャレ（ナチュラル）Qグレード', 200, None, None),
    ('75970340', 'インドネシア マンデリンG1', 200, None, '深煎り'),
    ('152749415', 'グアテマラ', 200, None, None),
    ('86624583', 'タンザニア AA スノートップ', 200, None, None),
    ('152750277', 'インドネシア ジャワ アラビカ G1', 200, None, None),
    ('132552821', 'ベトナム ルビーマウンテン（アラビカ）', 200, None, None),
    ('75719797', 'カフェインレス エチオピア モカ G-1 有機栽培', 200, None, None),
]

# coffee_parser.pyの国名辞書で検出できない表記の産地を明示する
ORIGIN_OVERRIDES = {}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
BEAN_OUT_PATTERN = re.compile(r'<option[^>]*data-stock="0"[^>]*>\s*在庫なし[:：]\s*豆')
ROAST_LABEL_PATTERN = re.compile(r"焙煎度[：:]\s*(極深煎り|中深煎り|中浅煎り|浅煎り|中煎り|深煎り)")


def build_record(item_id: str, name: str, weight_g, category_override, roast_level) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    raw_desc = html_lib.unescape(desc_m.group(1)) if desc_m else ""
    desc = re.sub(r"\s+", " ", raw_desc).strip()[:400] or None
    price_m = PRICE_PATTERN.search(html_text)
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    # 全バリエーション在庫なし、または「豆のまま」バリエーションが在庫なし(粉のみ在庫あり)の場合は品切れ扱い
    sold_out = (bool(purchasability_m) and purchasability_m.group(1) == "unpurchasable") or bool(BEAN_OUT_PATTERN.search(html_text))

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

    roast = roast_level or parsed["roast_level"]
    if not roast:
        label_m = ROAST_LABEL_PATTERN.search(raw_desc)
        if label_m:
            roast = label_m.group(1)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast,
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
        finally:
            time.sleep(REQUEST_INTERVAL_SEC)
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_coffeefuku.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeefuku.json に出力しました")


if __name__ == "__main__":
    main()
