# -*- coding: utf-8 -*-
"""
scrape_cafesakuya.py

自家焙煎珈琲 cafe SAKUYA(https://cafesakuya.base.shop/、秋田県鹿角市花輪字八正寺19-1)の商品情報を取得する。BASE。

【店舗について】
aboutに「店主一人で、お客様お一人おひとりのために丁寧に焙煎する、小さな自家焙煎珈琲店」「住所:秋田県鹿角市花輪字八正寺19-1(鹿角市文化の杜交流館 コモッセ近く) Tel 0186-27-9106 10:30〜18:30 水・木定休」「当店のメインは珈琲豆の焙煎・販売」と記載。
【オーダー焙煎方式】商品の大半は「生豆200g」の価格を表示し、焙煎度・挽き目を購入時に選ぶ(「焙煎後は15〜20%程度軽くなります」)。
そのため生豆銘柄(25件)は商品ページの表記どおり weight=200、価格は生豆200g基準として登録し、説明文の先頭に注記を付けた。焙煎豆として販売されるサクヤブレンド・イワナガブレンドⅡ(焙煎豆200g)は注記なし。
焙煎度は購入時に選択するため、生豆銘柄の焙煎度はnull。除外: AIブレンド・カスタムブレンド(客の希望で都度作る一点物。ドリップバッグ加工や粉指定のものを含む)、オリジナルブレンドセット、おまかせドリップバッグ20個セット。

【robots.txtについて】
2026-11-03確認: User-agent: * は Allow: / で、Disallow は /cart/ /web_cart/ /shops/ 等のみ。
python-requests/curl 等は個別に Disallow: / 指定のため、本スクレイパーは識別可能な
独自User-Agent(CoffeeFinderBot)を使用し、リクエスト間隔は5秒以上とする。

【対象商品の選定について】
実データ確認済み(2026-11-03): 下のITEMSは、サイトマップの全商品ページから
豆(シングルオリジン・ブレンド・デカフェ)のみを選んだもの。AIブレンド・カスタムブレンド(都度作成の一点物)・ブレンドセット・ドリップバッグセットは除外。生豆銘柄は『生豆200g基準の価格』のまま登録(オーダー焙煎方式)。
商品名・重量・焙煎度は商品ページの表記を確認したうえでITEMSに明示している。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。
"""

import html
import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "自家焙煎珈琲 cafe SAKUYA",
    "url": "https://cafesakuya.base.shop/",
    "platform": "BASE",
    "address": "秋田県鹿角市花輪字八正寺19-1",
    "prefecture": "秋田県",
    "robots_txt_status": "実質許可(2026-11-03確認。User-agent: * は Allow: / で /cart/ 等のみ禁止。python-requests/curl等は個別にDisallow: /指定のため識別可能なUser-Agentを使用、間隔5秒以上)",
    "source_note": "BASEショップ(https://cafesakuya.base.shop/)のabout・サイトマップ・各商品ページを2026-11-03に確認。住所はabout「秋田県鹿角市花輪字八正寺19-1」。価格は多くが『生豆200g』基準のオーダー焙煎(焙煎後は15〜20%軽くなる)で、weight=200は生豆基準。サクヤブレンド・イワナガブレンドⅡのみ焙煎豆200g。サイトマップ最終更新2026-10-27",
    "last_verified_at": "2026-11-03",
}

BASE_URL = "https://cafesakuya.base.shop"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL = 5.2  # BASEは5秒以上
DESC_PREFIX = "【オーダー焙煎・価格は生豆200g基準(焙煎後は15〜20%軽くなる。焙煎度・挽き目は購入時に選択)】"  # 説明文の先頭に付ける注記(該当商品IDのみ)
DESC_PREFIX_IDS = ['111005733', '114347030', '115603582', '123912566', '133314847', '133315060', '144587416', '144587447', '144591241', '155830272', '155830294', '155830307', '66598033', '66621984', '66631642', '66631668', '66631776', '66631792', '66708226', '74854746', '78085655', '82096744', '84229300', '84229374', '85066666']

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定), 産地の上書き(Noneなら自動))
ITEMS = [
    ('66631580', 'サクヤブレンド', 200, 'ブレンド', '中煎り', None),
    ('66631604', 'イワナガブレンドⅡ', 200, 'ブレンド', '中深煎り', None),
    ('111005733', 'ホンジュラス ラス・ウバス農園', 200, None, None, None),
    ('114347030', 'コスタリカ ラ・リア ピエサン2000 カトゥアイ WH', 200, None, None, None),
    ('115603582', 'エチオピア ベンチ・マジG-1 ゲシャ・カルマチ農園', 200, None, None, None),
    ('123912566', 'ブラジル ダテーラ農園 Full Bloom', 200, None, None, None),
    ('133314847', 'パプアニューギニア トロピカルマウンテン', 200, None, None, None),
    ('133315060', 'コスタリカ セントタラス SHB ガンボア農園', 200, None, None, None),
    ('144587416', 'インドネシア スラウェシ島 トラジャ', 200, None, None, None),
    ('144587447', 'タンザニア サウステラ AA', 200, None, None, None),
    ('144591241', 'ペルー マチュピチュ', 200, None, None, None),
    ('155830272', 'ケニア AA', 200, None, None, None),
    ('155830294', 'コロンビア トリマ・オーガニック decafe', 200, None, None, None),
    ('155830307', 'ブラジル フルッタメルカドン decafe', 200, None, None, None),
    ('66598033', 'インドネシア アチェ アルールバダ', 200, None, None, None),
    ('66621984', 'グアテマラ ゴールデンパレンシア リオ・コロラド農園', 200, None, None, None),
    ('66631642', 'エチオピア モカ イルガチェフェ G-1 ベレカ', 200, None, None, None),
    ('66631668', 'ケニア マサイ AA', 200, None, None, None),
    ('66631776', 'コロンビア スイートベリー スプレモ', 200, None, None, None),
    ('66631792', 'インドネシア マンデリン G-1 ミトラ', 200, None, None, None),
    ('66708226', 'グアテマラ オリエンテ ナチュラル', 200, None, None, None),
    ('74854746', 'イエメン アラビアンセレクション', 200, None, None, None),
    ('78085655', 'ジャマイカ ブルーマウンテンNo.1', 200, None, None, None),
    ('82096744', 'コロンビア エメラルドマウンテン', 200, None, None, None),
    ('84229300', 'ブラジル 樹上完熟・晩秋摘み', 200, None, None, None),
    ('84229374', 'ブラジル 試験栽培品種・イバイリ', 200, None, None, None),
    ('85066666', 'ペルー クルス・デル・ノルテ農協', 200, None, None, None),
]

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id, name, weight_g, category_override, roast_level, origin_override):
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    if resp.status_code != 200:
        print(f"[warn] 取得失敗(回避せずスキップ): item_id={item_id} status={resp.status_code}")
        return None
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    desc = re.sub(r"\s+", " ", html.unescape(desc_m.group(1))).strip()[:400] if desc_m else None
    if item_id in DESC_PREFIX_IDS:
        desc = (DESC_PREFIX + (desc or "")).strip()
    price_m = PRICE_PATTERN.search(html_text)
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    # unpurchasable=全バリエーション購入不可(品切れ)。partially_purchasable=一部のみ不可なので販売中扱い
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
        if origin_override:
            parsed["origin_country"] = origin_override
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


def scrape_all_products():
    records = []
    for i, (item_id, name, weight_g, category_override, roast_level, origin_override) in enumerate(ITEMS):
        if i:
            time.sleep(REQUEST_INTERVAL)
        try:
            record = build_record(item_id, name, weight_g, category_override, roast_level, origin_override)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_cafesakuya.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_cafesakuya.json に出力しました")


if __name__ == "__main__":
    main()
