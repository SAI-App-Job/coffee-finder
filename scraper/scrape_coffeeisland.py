# -*- coding: utf-8 -*-
"""
scrape_coffeeisland.py

珈琲島 鶴岡店(https://coffeeisland.thebase.in/、〒997-0010 山形県鶴岡市余慶町1-2 こぴあ内、
特定商取引法に基づく表記で確認)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(山形県)の新規発掘。

【対象商品について】
実データ確認済み(2026-10-13時点): sitemap.xmlの商品は全56件。コーヒー豆は14銘柄が
【100g】【250g】【500g】の重量別に別商品として登録されている(月替わりブレンド「月のしずく」、
季節の深煎り「秋煎り ルワンダ」、シングルオリジン7種、定番ブレンド2種、深煎りブレンド2種、
カフェインレス1種)。最小重量の【100g】を代表として採用する。
除外: 250g/500g(同銘柄の別重量)、カップインコーヒー(港町ブレンド・城下町ブレンドの
ドリップ式個包装)、ミズダシコーヒー(水出しパック)、保存缶、かりんとう、アバカ
フィルター、クレバーコーヒードリッパー。
商品名・焙煎度は商品ページの表記(商品説明冒頭の【中深煎り】等)を確認したうえで下のITEMSに
明示している。価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。
「クラシックロースト」は商品説明に「使用する豆は代わることがあります」とあり単一産地に固定
されないため、産地は付けずブレンド扱いとする。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import json
import re

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "珈琲島",
    "url": "https://coffeeisland.thebase.in/",
    "platform": "BASE",
    "address": "山形県鶴岡市余慶町1-2 こぴあ内",
    "prefecture": "山形県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://coffeeisland.thebase.in"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ("67430337", "月のしずく(10月限定ブレンド)", 100, "ブレンド", "中深煎り"),
    ("43640688", "ニカラグア ラス・マリアス", 100, None, "浅煎り"),
    ("79440875", "秋煎り ルワンダ", 100, None, "中深煎り"),
    ("64879347", "エチオピア チェルチェレ", 100, None, "中浅煎り"),
    ("105309756", "ペルー ラ・ルクマ", 100, None, "中浅煎り"),
    ("2509385", "メキシコ カフェインレス", 100, "デカフェ", "中煎り"),
    ("2429923", "コロンビア ロスナランホ", 100, None, "中煎り"),
    ("93340045", "グアテマラ オーロラ", 100, None, "中煎り"),
    ("80644614", "マンデリン ポルンアルフィナー", 100, None, "中深煎り"),
    ("2429969", "ブラジル カクェンジ", 100, None, "中深煎り"),
    ("142673597", "クラシックロースト", 100, "ブレンド", "深煎り"),
    ("86424111", "深緋(深煎りブレンド)", 100, "ブレンド", "深煎り"),
    ("2429979", "庄内の空ブレンド", 100, "ブレンド", "中浅煎り"),
    ("2429972", "城下町ブレンド", 100, "ブレンド", "中深煎り"),
]

# coffee_parser.pyの国名辞書で検出できない表記の産地を明示する
ORIGIN_OVERRIDES = {
    "80644614": "インドネシア",  # マンデリン(スマトラ島北部、商品説明で確認)
    "2509385": "メキシコ",
}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
GRIND_NOTE_PATTERN = re.compile(r"※【粉・中挽き】.*$")


def clean_description(text: str) -> str | None:
    text = re.sub(r"\s+", " ", text).strip()
    text = GRIND_NOTE_PATTERN.sub("", text).strip()
    return text[:400] or None


def build_record(item_id: str, name: str, weight_g: int, category_override: str | None, roast_level: str | None) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    html_text = resp.text

    import html as _html
    desc_m = DESC_PATTERN.search(html_text)
    desc = clean_description(_html.unescape(desc_m.group(1))) if desc_m else None
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
        if category_override:
            parsed["category"] = category_override
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
    with open("data_coffeeisland.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeeisland.json に出力しました")


if __name__ == "__main__":
    main()
