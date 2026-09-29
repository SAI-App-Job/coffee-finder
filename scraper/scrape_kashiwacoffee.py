# -*- coding: utf-8 -*-
"""
scrape_kashiwacoffee.py

珈茶話 -kashiwa- Cafe & Coffee Roastery(KASHIWA COFFEE ROASTERY、
kashiwa25.base.ec、栃木県日光市今市1147。1982年創業、店内に焙煎コーナー・
豆売りブースを併設する自家焙煎専門店)の商品情報を取得する。
BASE(base.ecドメイン)。

【店舗発見の経緯】
全国再調査(栃木県)でサブエージェント調査から発見。

【対象商品について】
実データ確認済み(2026-09時点): 商品一覧全21件のうち、複数銘柄から
2種選べるお得なセット(1kg特価セット・150gお試しセット、いずれも
「下記の中からお好きなコーヒーを2種お選びください」形式の複数銘柄
セット)・ドリップバッグ2種を除いた、単品販売の豆17銘柄(150g、
ブレンド9・ストレート8)を対象とする。日光ブレンドのみ中煎り・深煎りの
2焙煎度が別商品として並売されている。

【商品説明の構造について】
実データ確認済み: og:descriptionが簡潔なコピー文に続き「焙煎：X
酸味★苦味★甘味★コク★香り★」という星評価ラベルを持つ(星評価の項目名は
固定順序: 酸味/苦味/甘味/コク/香り)。焙煎ラベルが無い商品(ブラジル等)は
タイトルの[中煎り]等の角括弧表記を焙煎ヒントとして使う。星評価以降の
「[豆の挽き方について]」という定型注意書きは除去する。
"""

import html
import json
import re

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "珈茶話 -kashiwa- Cafe & Coffee Roastery",
    "url": "https://kashiwa.cc/",
    "platform": "BASE(base.ec)",
    "address": "栃木県日光市今市1147",
    "prefecture": "栃木県",
    "robots_txt_status": "未確認(BASE標準構成)",
}

BASE_URL = "https://kashiwa25.base.ec"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}

ITEM_IDS = [
    "36930628",  # カシワブレンド [中煎り]
    "36933611",  # ロッソブレンド(エスプレッソ推奨) [深煎り]
    "36933843",  # ダークブレンド(アイスコーヒー推奨) [極深煎り]
    "38741706",  # ブラジル [中煎り]
    "38743068",  # コロンビア [中煎り]
    "38743125",  # グァテマラ [中煎り]
    "38743166",  # エチオピア [中浅煎り]
    "38743315",  # デカフェ カフェインレス [中煎り]
    "38743438",  # インドネシア [中深煎り]
    "38743520",  # タンザニア [中煎り]
    "46628438",  # サワーブレンド [中浅煎り]
    "46628962",  # リッチブレンド [中深煎り]
    "46629232",  # ヒールブレンド [中浅煎り]
    "66307519",  # ケニア [中煎り]
    "67295138",  # 日光ブレンド [中煎り]
    "67295175",  # 日光ブレンド [深煎り]
    "72427285",  # ビターブレンド [中深煎り]
]

TITLE_PATTERN = re.compile(r"<title>([^<|]+?)\s*\|\s*")
DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
ROAST_BRACKET_PATTERN = re.compile(r"[［\[]\s*([^］\]]+?)\s*[］\]]")
STAR_LABEL_PATTERN = re.compile(r"(酸[\s　]*味|苦[\s　]*味|甘[\s　]*味|コ[\s　]*ク|香[\s　]*り)[\s　]*[：]?[\s　]*([★☆]+)")
ROAST_LABEL_PATTERN = re.compile(r"焙煎[：:]\s*([^\s酸苦甘コ香]+)")


def build_record(item_id: str) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=20)
    resp.encoding = "utf-8"
    html_text = resp.text

    title_m = TITLE_PATTERN.search(html_text)
    if not title_m:
        return None
    title = re.sub(r"\s+", " ", title_m.group(1).strip()).strip()

    desc_m = DESC_PATTERN.search(html_text)
    desc = html.unescape(desc_m.group(1).strip()) if desc_m else ""

    bracket_m = ROAST_BRACKET_PATTERN.search(title)
    roast_label_m = ROAST_LABEL_PATTERN.search(desc)
    roast_hint = (roast_label_m.group(1) if roast_label_m else None) or (bracket_m.group(1) if bracket_m else None)

    flavor_text = STAR_LABEL_PATTERN.split(desc)[0]
    flavor_text = re.sub(r"焙煎[：:]\s*\S+", "", flavor_text)
    flavor_text = re.sub(r"\[豆の挽き方について\].*$", "", flavor_text, flags=re.DOTALL)
    flavor_text = flavor_text.strip() or None

    price_m = PRICE_PATTERN.search(html_text)
    price = int(price_m.group(1)) if price_m else None
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    sold_out = bool(purchasability_m) and purchasability_m.group(1) != "purchasable"
    stock_status = "完売" if sold_out else "販売中"

    clean_title = ROAST_BRACKET_PATTERN.sub("", title).strip()
    parsed = parse_product(clean_title)
    url = f"{BASE_URL}/items/{item_id}"

    if parsed["category"] != "ブレンド":
        detected = detect_country_name(clean_title)
        if detected:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, clean_title)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": roast_hint,
        "flavor_notes": flavor_text,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": 150,
        "stock_status": stock_status,
        "out_of_stock": sold_out,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item_id in ITEM_IDS:
        try:
            detail = build_record(item_id)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        if detail is None:
            continue
        records.append(detail)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_kashiwacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kashiwacoffee.json に出力しました")


if __name__ == "__main__":
    main()
