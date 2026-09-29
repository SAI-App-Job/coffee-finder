# -*- coding: utf-8 -*-
"""
scrape_tonbi.py

tonbi coffee(tonbi-coffee.shop-pro.jp、群馬県高崎市菅谷町531-10、
2006年開業・2026年で20周年)の商品情報を取得する。カラーミーショップ
(shop-pro.jp、レガシーなEUC-JPエンコーディング)。DEAN&DELUCAへの卸実績
あり(tonbi-coffee.comのNews欄で確認)。

【店舗発見の経緯】
全国再調査(群馬県)でサブエージェント調査から発見。

【対象商品について】
実データ確認済み(2026-09時点): 「コーヒー豆―ブレンド」(cbid=210592、
11件)・「コーヒー豆―シングルオリジン」(cbid=210593、12件)・
「カフェインレス・コーヒー」(cbid=2143405、1件)の3カテゴリ計24件の
うち、複数銘柄を少量ずつ詰め合わせたセット商品2件(「定番ブレンド
100ｇ×4種セット」「おすすめシングルオリジン100ｇ×3種セット」)を
除いた、ブレンド10・ストレート11・カフェインレス1の計22商品を対象と
する。同一農園(サンタカタリーナ農園・ロス クレストネス)でも焙煎度
違いの商品は独立した商品として販売継続中のため両方収録する。

【ページ構造について】
実データ確認済み: charset=euc-jpのレガシーページのため、requests取得時
に`r.encoding = "euc-jp"`を明示する必要がある(デフォルトのutf-8や
apparent_encodingでは文字化けする)。商品名・説明・価格はいずれも
標準的なog:title/og:description/product:price:amountメタタグから
取得できる。
"""

import json
import re

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "tonbi coffee",
    "url": "https://tonbi-coffee.com/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "群馬県高崎市菅谷町531-10",
    "prefecture": "群馬県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://tonbi-coffee.shop-pro.jp"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}

# セット商品2件(170519081, 170517177)は除外済み
ITEM_IDS = [
    "11258216", "15270006", "4342031", "4342060", "4342077", "4342094",
    "4342106", "4342123", "5903498", "9607909",
    "141663832", "143821287", "148571729", "173761545", "186871828",
    "188668626", "193280271", "4342211", "4415675", "71890720", "87799094",
    "191611779",
]

TITLE_PATTERN = re.compile(r'<meta property="og:title" content="([^"]*)"')
DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'<meta property="product:price:amount" content="(\d+)"')
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def build_record(item_id: str) -> dict | None:
    resp = requests.get(f"{BASE_URL}/?pid={item_id}", headers=REQUEST_HEADERS, timeout=20)
    resp.encoding = "euc-jp"
    html_text = resp.text

    title_m = TITLE_PATTERN.search(html_text)
    if not title_m:
        return None
    title = title_m.group(1).split(" - tonbi coffee")[0].strip()
    title = re.sub(r"\s+", " ", title)

    desc_m = DESC_PATTERN.search(html_text)
    desc = desc_m.group(1).strip() if desc_m else None

    price_m = PRICE_PATTERN.search(html_text)
    price = int(price_m.group(1)) if price_m else None

    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None

    parsed = parse_product(title)
    if parsed["category"] != "ブレンド":
        detected = detect_country_name(title) or (detect_country_name(desc) if desc else None)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name" if detect_country_name(title) else "product_description"
        parsed = apply_category_hint_fallback(parsed, desc or "")

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
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": "販売中",
        "out_of_stock": False,
        "product_url": f"{BASE_URL}/?pid={item_id}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item_id in ITEM_IDS:
        try:
            detail = build_record(item_id)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={item_id} ({e})")
            continue
        if detail is None:
            continue
        records.append(detail)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_tonbi.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_tonbi.json に出力しました")


if __name__ == "__main__":
    main()
