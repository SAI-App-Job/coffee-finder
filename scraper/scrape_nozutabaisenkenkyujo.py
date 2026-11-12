# -*- coding: utf-8 -*-
"""
scrape_nozutabaisenkenkyujo.py

野津田焙煎研究所(https://nozutabk.base.shop/、東京都町田市野津田町1371-19)の自家焙煎コーヒー豆の商品情報を取得する。BASE。

【店舗の実在確認(2026-10-25)】
公式ショップ About Us(https://nozutabk.base.shop/about)「所在地 東京都町田市野津田町1371-19」「営業時間 毎週火曜日・木曜日 10:00-13:00」「神奈中バス 岩子山 より徒歩3分」、
同ページ「小さな3キロの焙煎機を購入してみようと決断しました」(自家焙煎)。第三者: coffee-labo.co.jp 町田のコーヒー豆店比較表
(https://coffee-labo.co.jp/recommended-coffee-bean-store-in-machida/)で自家焙煎「○」、アクセス・営業時間がショップ紹介と一致。

【対象商品について】
実データ確認済み(2026-10-25): 商品ページ83件(コーヒー豆・ドリップバッグ・ラテベース・紅茶・器具・アクセサリー素材・セット)のうちコーヒー豆単品。
各銘柄は100g版(接頭語なし。ページ冒頭に「200g購入希望の方はコチラ」と200g版へのリンクあり)と「【200g】」版が別商品のため、最小重量の100g版を代表とする(Nigusse Gemedaのみ「【100g】」表記)。
除外: 【200g】版、ドリップバッグ、LATTE BASE、Cold/Milk Brew、セット・ギフト・おまかせお試し、キャニスター、紅茶、器具、アクセサリー素材。
商品名・重量・焙煎度は商品ページの表記を確認したうえで下のITEMSに明示している。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。

【robots.txtについて】
BASE共通の記述(python-requests/curl等は個別にDisallow: /、User-agent: *では
/cart/・/web_cart/・/shops/・/api/shops/等のみ禁止)。本スクレイパーは識別可能な
独自User-Agentを使用し、取得するのは /items/ の商品ページのみ。取得間隔は5秒。
"""

import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "野津田焙煎研究所",
    "url": "https://nozutabk.base.shop/",
    "platform": "BASE",
    "address": "東京都町田市野津田町1371-19",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-10-25確認。BASE共通の記述でpython-requests/curl等は個別にDisallow、User-agent: * では商品ページ(/items/)は許可。識別可能なUser-Agentを使用)",
    "source_note": "公式ショップ About Us と商品ページ(sitemap.xmlの/items/)を2026-10-25に確認。ブログ最新は2026/03/17。coffee-labo.co.jp町田記事で実店舗・自家焙煎を確認。",
    "last_verified_at": "2026-10-25",
}

BASE_URL = "https://nozutabk.base.shop"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL = 5

# (商品ID, 商品名, 重量(g)またはNone, 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら説明文→商品名の順で判定))
ITEMS = [
    ('113305926', 'Nigusse Gemeda Morke Underscreen Natural', 100, None, None),
    ('87188101', 'Nozuta Blend Deep', 100, 'ブレンド', '深煎り'),
    ('149607307', 'ICE BLEND', 100, 'ブレンド', None),
    ('153816359', 'Condor ”PinkBourbon Washed Las Flores”', 100, None, None),
    ('161862421', 'Finca Milan Toffee', 100, None, None),
    ('153815893', 'Finca Milan Caturra Nitro', 100, None, None),
    ('151357378', 'Finca Milan Culturing NG', 100, None, None),
    ('65686963', 'インドネシア マンデリン ビンタンリマ G1', 100, None, None),
    ('161504014', 'エチオピア グジG-1 アナソラ ナチュラル', 100, None, None),
    ('131644159', 'エチオピア ジマ ゲラ農園 ウォッシュ G1', 100, None, None),
    ('161688760', 'エチオピア ジマG-1 ゲラ農園 アナエロビックナチュラル', 100, None, None),
    ('97159417', 'エチオピア ベンチマジ ゲシャビレッジ チャカ ナチュラル', 100, None, None),
    ('91464669', 'エチオピア ベンチ・マジG-1 ゲシャ・カルマチ農園 カーボニックマセレーション', 100, None, None),
    ('66472708', 'グァテマラ SHB ウエウエテナンゴ 有機栽培', 100, None, None),
    ('75232885', 'グアテマラ オリエンテ ナチュラル', 100, None, None),
    ('143672497', 'グアテマラ コバン チコフ農園 ウォッシュド', 100, None, None),
    ('87988494', 'ケニア カグモイニAA', 100, None, None),
    ('70974667', 'コロンビア エルパライソ ダブルアナエロビックファーメンテーション ライチ', 100, None, None),
    ('118567428', 'タンザニア ンゴロンゴロ エレファント フォレスト ピーベリー ウォッシュ', 100, None, None),
    ('142327320', 'デカフェ エチオピア イルガチェフェ マウンテンウォーター ウォッシュ G2', 100, None, None),
    ('97161290', 'パプアニューギニア シウェット プランテーション マッドマン', 100, None, None),
    ('90779609', 'ブラジル ドルチェ チョコラーダ', 100, None, None),
    ('84366234', 'ブルンジ キビンゴ・ウォッシングステーション', 100, None, None),
    ('72233832', 'ルワンダ ムササWS ブルボン ハニープロセス', 100, None, None),
]

# 産地の上書き(商品ID -> 日本語の国名。None は「商品名と説明で食い違う等で不明」とする)
ORIGIN_OVERRIDES = {'153816359': 'コロンビア', '161862421': 'コロンビア', '153815893': 'コロンビア', '151357378': 'コロンビア', '149607307': None, '113305926': 'エチオピア'}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)")
ROAST_PATTERN = re.compile(r"【焙煎度】\s*([^【\s]+)")


def clean_desc(raw: str) -> str | None:
    import html as _html
    text = _html.unescape(raw)
    text = re.sub(r"\s+", " ", text).strip()
    # 先頭の定型文(ネコポス案内・200g版へのリンク)を取り除く
    text = re.sub(r"^.*?◆200ｇ購入希望の方はコチラ\s*https?://\S*?/(?:items|categories)/\d+", "", text).strip()
    return text[:400] or None


def build_record(item_id, name, weight_g, category_override, roast_level):
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    raw_desc = desc_m.group(1) if desc_m else ""
    desc = clean_desc(raw_desc)
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
            parsed["origin_source"] = "raw_name" if ORIGIN_OVERRIDES[item_id] else None

    if not roast_level:
        import html as _html
        roast_m = ROAST_PATTERN.search(re.sub(r"\s+", "", _html.unescape(raw_desc)))
        roast_level = roast_m.group(1) if roast_m else None
    if not roast_level:
        roast_level = parsed["roast_level"]

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level,
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
    for index, (item_id, name, weight_g, category_override, roast_level) in enumerate(ITEMS):
        if index:
            time.sleep(REQUEST_INTERVAL)
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
    with open("data_nozutabaisenkenkyujo.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_nozutabaisenkenkyujo.json に出力しました")


if __name__ == "__main__":
    main()
