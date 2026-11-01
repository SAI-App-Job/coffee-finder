# -*- coding: utf-8 -*-
"""
scrape_yatabecoffee.py

ヤタベコーヒー(https://www.yatabecoffee.com/、茨城県つくば市谷田部2417-45)の商品情報を取得する。BASE(独自ドメイン)。

【店舗発見の経緯】
全国再調査(茨城県・栃木県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10-26時点): 豆(100g/200gが別ページ)のうち100gページを代表として16商品を対象とする。ドリップパック・水出しパック・ギフト・フィルターは除外。ウイスキー風味のBonBonClassico(ボンボンクラシコ)は風味付けコーヒーの可能性があるため除外。焙煎度は商品ページに記載が無いためNone。
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している。
価格・在庫(item_purchasability と「豆のまま」バリエーションの在庫表示)・説明(og:description)は
商品ページから取得する。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用し、リクエスト間隔を5秒以上空ける。
"""

import html
import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "ヤタベコーヒー",
    "url": "https://www.yatabecoffee.com/",
    "platform": "BASE(独自ドメイン)",
    "address": "茨城県つくば市谷田部2417-45",
    "prefecture": "茨城県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
    "source_note": "公式サイト(https://www.yatabecoffee.com/ 、BASE独自ドメイン)の商品ページ(/items/<ID>)・/about・/law を2026-10-26に確認。住所と営業時間(火曜定休)は特定商取引法表記。ブログ最新は2026-09-30。100gを代表とし、在庫は「豆のまま」バリエーションの表示による。",
    "last_verified_at": "2026-10-26",
}

BASE_URL = "https://www.yatabecoffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL_SEC = 5

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('17109662', 'ブラジル フルッタメルカドン', 100, None, None),
    ('17117122', 'インドネシア マンデリン ビンタンリマ', 100, None, None),
    ('17119822', 'コロンビア スウィートベリーSUP', 100, None, None),
    ('18061134', 'エチオピア イリガチャフG1フローラル（ナチュラル）', 100, None, None),
    ('19081089', 'ルワンダ スカイヒル', 100, None, None),
    ('19081259', 'パプアニューギニア ハイランドスウィート', 100, None, ""),
    ('21688339', 'グァテマラ オリエンテナチュラル', 100, None, None),
    ('23074392', 'エチオピア ゲイシャJasmine G1', 100, None, None),
    ('26408412', 'グァテマラ ゴールデンパレンシア SHB', 100, None, None),
    ('35861014', 'エスプレッソマシーン用ブレンド', 100, 'ブレンド', None),
    ('50435495', 'コスタリカ ブラックハニー', 100, None, None),
    ('58670906', 'ブラジル キャラメラード', 100, None, None),
    ('86909765', 'インドネシア カモジャン', 100, None, None),
    ('91931739', 'エチオピア カフェインレス', 100, None, None),
    ('9642889', 'YATABE COFFEEマイルドブレンド', 100, 'ブレンド', None),
    ('9642991', 'ブラジル サントアントニオ プレミアムショコラNo.2', 100, None, None),
]

# coffee_parser.pyの国名辞書で検出できない表記の産地を明示する
ORIGIN_OVERRIDES = {}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
VARIATION_LIST_PATTERN = re.compile(r'<ul class="cot-itemOrder-variationList">(.*?)</ul>', re.S)
VARIATION_ITEM_PATTERN = re.compile(r'<li class="cot-itemOrder-variationLI">(.*?)</li>', re.S)
VARIATION_NAME_PATTERN = re.compile(r'variationName"[^>]*>([^<]*)<')
VARIATION_STOCK_PATTERN = re.compile(r'variationStock"[^>]*>([^<]*)<')


def is_sold_out(html_text: str) -> bool:
    """「豆のまま」バリエーションの在庫表示を優先し、無ければ商品全体の購入可否で判定する。"""
    ul = VARIATION_LIST_PATTERN.search(html_text)
    if ul:
        for li in VARIATION_ITEM_PATTERN.findall(ul.group(1)):
            n = VARIATION_NAME_PATTERN.search(li)
            s = VARIATION_STOCK_PATTERN.search(li)
            if n and s and "豆のまま" in html.unescape(n.group(1)):
                return "在庫なし" in s.group(1)
    m = PURCHASABILITY_PATTERN.search(html_text)
    return bool(m) and m.group(1) == "unpurchasable"


def build_record(item_id: str, name: str, weight_g: int, category_override, roast_level):
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    desc = re.sub(r"\s+", " ", html.unescape(desc_m.group(1))).strip()[:400] if desc_m else None
    price_m = PRICE_PATTERN.search(html_text)
    sold_out = is_sold_out(html_text)

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
        # 焙煎度の記載が無い商品は""を渡して商品名からの自動判定(「ハイランド」を「ハイロースト」と誤検出する)を無効化する
        "roast_level": (roast_level or None) if roast_level is not None else parsed["roast_level"],
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
    for n, (item_id, name, weight_g, category_override, roast_level) in enumerate(ITEMS):
        if n:
            time.sleep(REQUEST_INTERVAL_SEC)
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
    with open("data_yatabecoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_yatabecoffee.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], r["category"], r["origin_country"], r["roast_level"], r["price"], r["weight_g"], r["stock_status"])


if __name__ == "__main__":
    main()
