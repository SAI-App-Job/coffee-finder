# -*- coding: utf-8 -*-
"""
scrape_terasucoffee.py

てらす珈琲(https://terasucoffee.theshop.jp/、神奈川県相模原市南区相模大野6-17-3 MKステージ1F-2)の商品情報を取得する。BASE(theshop.jpドメイン)。

【店舗発見の経緯】
全国再調査(神奈川県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10-21時点): 全33商品のうち、季節ブレンド2・定番ブレンド4・シングルオリジン/デカフェ10の計16商品を収録。ギフトセット、器具、フィルターは対象外。商品ページは容量(100g/200g/500g/1kg)と豆/粉を選ぶ形式で、表示価格(「100g ￥X～」)は100gの価格のため重量100gとして採用。同一銘柄で焙煎度違いの別商品は焙煎度を名前に付けて区別した。
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。
BASEの商品ページは1商品1価格(バリエーションは在庫のみ)のため、価格は商品ページの表示価格をそのまま採用する。

【実店舗・自家焙煎の根拠】
販売ページABOUT「2015年創業。相模大野駅(神奈川県相模原市)から徒歩7分のスペシャルティコーヒー豆専門店「てらす珈琲」。選りすぐりのスペシャルティコーヒーの生豆を丁寧に焙煎し」「代表・焙煎士 妹尾 真弘」、商品ページ説明「神奈川県相模原市の自家焙煎スペシャルティコーヒー専門店「てらす珈琲」」(https://terasucoffee.theshop.jp/about , /law 2026-10-21確認)。特商法に営業時間(平日11:00-20:00、土日祝11:00-19:00、定休日 月・火)と所在地。第三者サイトでは確認できなかった。

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
    "name": "てらす珈琲",
    "url": "https://terasucoffee.theshop.jp/",
    "platform": "BASE",
    "address": "神奈川県相模原市南区相模大野6-17-3 MKステージ1F-2",
    "prefecture": "神奈川県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
    "source_note": "BASE theshop.jp(https://terasucoffee.theshop.jp/)のsitemap.xmlの全商品ページとABOUT・特商法ページを2026-10-21に確認。豆の商品の最終更新は2026-09〜2026-10(sitemap lastmod)。住所は特商法の事業者所在地",
    "last_verified_at": "2026-10-21",
}

BASE_URL = "https://terasucoffee.theshop.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL_SEC = 5.0

# (商品ID, 商品名, 重量(g)(不明はNone), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名・説明文から判定))
ITEMS = [
    ('79003124', '【季節限定】ハロウィンブレンド（ハイロースト）', 100, 'ブレンド', '中浅煎り'),
    ('77990556', '【季節限定】秋ブレンド（フルシティロースト）', 100, 'ブレンド', '中深煎り'),
    ('67037124', '【定番ブレンド】華ブレンド（ハイロースト）', 100, 'ブレンド', '中浅煎り'),
    ('67037289', '【定番ブレンド】和みブレンド（シティロースト）', 100, 'ブレンド', '中煎り'),
    ('67037406', '【定番ブレンド】凛ブレンド（フルシティロースト）', 100, 'ブレンド', '中深煎り'),
    ('67037504', '【定番ブレンド】深みブレンド（フレンチロースト）', 100, 'ブレンド', '深煎り'),
    ('157771262', 'グアテマラ ラ・クプラ農園 ウォッシュド（ミディアムロースト）', 100, None, '浅煎り'),
    ('159028143', 'ケニア カリンドゥンドゥ AA ウォッシュド（ミディアムロースト）', 100, None, '浅煎り'),
    ('66911580', 'エチオピア アリーチャ G1 ウォッシュド（シティロースト）', 100, None, '中煎り'),
    ('138082452', 'エチオピア ケレムウォレガ G1 ナチュラル（シティロースト）', 100, None, '中煎り'),
    ('70496670', 'コスタリカ バラ・ブランカ農園 ホワイトハニー（シティロースト）', 100, None, '中煎り'),
    ('67035726', 'エチオピア アリーチャ G1 ウォッシュド（フルシティロースト）', 100, None, '中深煎り'),
    ('75130046', 'インドネシア マンデリン スマトラタイガー S18 スマトラ式（フレンチロースト）', 100, None, '深煎り'),
    ('150961429', 'グアテマラ デカフェ パカヤリト農園 ウォッシュド（フレンチロースト）', 100, None, '深煎り'),
    ('159218869', 'タンザニア モンデュール農園 AA ウォッシュド（イタリアンロースト）', 100, None, '極深煎り'),
    ('125190121', 'グアテマラ ラ・クプラ農園 ウォッシュド（イタリアンロースト）', 100, None, '極深煎り'),
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
    with open("data_terasucoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_terasucoffee.json に出力しました")


if __name__ == "__main__":
    main()
