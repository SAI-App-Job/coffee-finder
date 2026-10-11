# -*- coding: utf-8 -*-
"""
scrape_akaitsukicoffee.py

赤い月珈琲(オンラインショップ「赤い月珈琲 OFFICIAL SHOP 天草五橋を渡ったら」
amakusaakai.theshop.jp、熊本県天草市東町7-8。運営: 光榮産業株式会社)の商品情報を取得する。
BASE(theshop.jp)。

【店舗発見の経緯】
全国再調査(熊本県)で発見。

【住所について】
特定商取引法の表記(/law)の事業者所在地「〒863-0033 熊本県天草市東町7-8」(営業時間
10:00〜17:00、「赤い月珈琲の営業に準ずる」)。

【自家焙煎の根拠について】
ストア側の商品説明に「自家焙煎」の文言はないが、商品説明に「焙煎は産地の特徴を最大限に
生かした時間と温度管理を徹底しています。直営店では、煎りたての豆の香ばしい香りとともに
珈琲豆が『パチパチッ』と弾ける音もまた、おいしさに拍車をかけています」とあり、ふるさと納税の
返礼品ページ(furunavi.jp 返礼品pid=187034)にも提供事業者・光榮産業株式会社が「コーヒー豆を
ブレンド、焙煎の味わいを決める工程を行っており」(地場産品の理由)と記載されている。
赤い月珈琲が天草で自らブレンド・焙煎を行う店と判断したが、「自家焙煎」という語そのものの
一次確認はできていない(要注意)。

【対象商品について】
実データ確認済み(2026-10時点): 一覧の商品43件のうち、珈琲豆100gのブレンド6種
(新月・満月・三日月・KURO・SHIRO・繭姫カフェインレス)とシングルオリジン11種。
ドリップバッグ、水出し珈琲パック、ギフト・セット(豆2種/3種セット含む)、メモパッド・画集・
絵本・木版画・DVDは除外。価格(product:price:amount、税込)・在庫(item_purchasability)・
説明(og:description)は商品ページから取得する。各商品の内容量は説明の「内容量…珈琲豆100g」。
ブラジル・グアテマラ・コロンビアは焙煎度を選べる(中煎り〜深煎り)ため、焙煎度はnull。
"""

import json
import re

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "赤い月珈琲",
    "url": "https://amakusaakai.theshop.jp/",
    "platform": "BASE",
    "address": "熊本県天草市東町7-8",
    "prefecture": "熊本県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://amakusaakai.theshop.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ("74007578", "【オリジナルブレンド】新月ブレンド 〜ストロング〜", 100, "ブレンド", "深煎り"),
    ("74007545", "【オリジナルブレンド】満月ブレンド 〜マイルド〜", 100, "ブレンド", None),
    ("74007602", "【オリジナルブレンド】三日月ブレンド 〜フルーティー〜", 100, "ブレンド", None),
    ("74007649", "【天草珈琲の器オリジナルブレンド】KURO〜陶器〜ブレンド", 100, "ブレンド", "深煎り"),
    ("74007712", "【天草珈琲の器オリジナルブレンド】SHIRO〜白磁〜ブレンド", 100, "ブレンド", None),
    ("74007738", "【カフェインレスコーヒー】繭姫カフェインレス - エチオピア シダモ G2 ウォッシュド", 100, None, "中深煎り"),
    ("126895546", "【シングルオリジン】ブラジル フクダ イエローブルボン ナチュラル", 100, None, None),
    ("80168298", "【シングルオリジン】グアテマラ フライハーネス SHB ウォッシュド", 100, None, None),
    ("90439396", "【シングルオリジン】ケニア SL28 AA ウォッシュド", 100, None, "中煎り"),
    ("112337608", "【シングルオリジン】エチオピア イルガチェフェ コチャレ G1 ウォッシュド", 100, None, None),
    ("90434069", "【シングルオリジン】エチオピア グジ シャキッソ TadeGG G1 ナチュラル", 100, None, None),
    ("26140330", "【シングルオリジン】コロンビア ビジャ・ファティマ ティピカ フリーウォッシュド", 100, None, None),
    ("90437495", "【シングルオリジン】ドミニカ アルフレド・ディアス プリンセサ ワイニーナチュラル", 100, None, None),
    ("26140451", "【シングルオリジン】インドネシア リントン マンデリン トバコ ウェットハル", 100, None, None),
    ("109407387", "【シングルオリジン】ハイチ フレンチブルー ティピカ ウォッシュド", 100, None, "中煎り"),
    ("145462999", "【シングルオリジン】ウガンダ カウェリエステート ロブスタ ナチュラル", 100, None, None),
    ("155579669", "【シングルオリジン】ウガンダ ダーレー サンユウ ロブスタ イーストファーメンテーションナチュラル", 100, None, None),
]

# coffee_parser.pyの国名辞書で検出できない表記の産地を明示する
ORIGIN_OVERRIDES = {
    "90437495": "ドミニカ共和国",
    "109407387": "ハイチ",
    "145462999": "ウガンダ",
    "155579669": "ウガンダ",
}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id: str, name: str, weight_g: int, category_override: str | None, roast_level: str | None) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    desc = None
    if desc_m:
        import html as _html
        desc = re.sub(r"\s+", " ", _html.unescape(desc_m.group(1))).strip()[:400]
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
    with open("data_akaitsukicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_akaitsukicoffee.json に出力しました")


if __name__ == "__main__":
    main()
