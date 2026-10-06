# -*- coding: utf-8 -*-
"""
scrape_sansankushiro.py

コーヒー豆の店 サンサン(kushirocoffee.wixsite.com/sansan、北海道釧路市芦野3丁目1番13号の
自家焙煎コーヒー豆店)の商品情報を取得する。Wix(静的な価格表)。

【対象商品について】
実データ確認済み(2026-10時点): メニューページ(/blank、「メニュー(PCで参照して下さい)」)に
「ブレンドコーヒー(100g価格)」「ストレートコーヒー(100g価格)」の2列の価格表が
テキストで載っている(商品ページ・カートは無い)。各行は「●銘柄名 \本体価格 \税込価格」の形式で、
全て100g単位の価格。税込価格を採用する。ブレンド12種・ストレート11種の計23商品。
(「注文焙き(500g以上)」「1kgまたは3000円以上で10%OFF」は価格表外の案内のため無視する。)

【商品URL・在庫について】
商品ごとのページが無いため、product_urlはメニューページURL+「#」+商品名(URLエンコード)とする。
価格表のみで在庫表示は無いため、全て「販売中」として扱う(在庫の実態は未確認)。
住所は店舗/営業時間ページ(/sansan)の「店舗所在地 北海道釧路市芦野3丁目1番13号」で確認済み。
"""

import json
import re
import unicodedata
import urllib.parse

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "コーヒー豆の店 サンサン",
    "url": "https://kushirocoffee.wixsite.com/sansan",
    "platform": "Wix",
    "address": "北海道釧路市芦野3丁目1番13号",
    "prefecture": "北海道",
    "robots_txt_status": "許可(2026-10確認。User-agent: *はAllow: /。Disallow: *?lightbox=のみ)",
}

MENU_URL = "https://kushirocoffee.wixsite.com/sansan/blank"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
WEIGHT_G = 100
# 「●銘柄名   \本体価格   \税込価格」。価格記号は半角バックスラッシュ表記
ROW_PATTERN = re.compile(r"●\s*([^\\●]+?)\s*[\\¥￥]\s*(\d[\d,]*)\s*[\\¥￥]\s*(\d[\d,]*)")
# parse_productの辞書に無い銘柄名からの産地補完(ゴロカ=パプアニューギニアの地名、
# エメラルドマウンテン=コロンビア産最高等級の通称)。「グレートマウンテン」は産地不明のためnull
NAME_ORIGIN_OVERRIDES = {"ゴロカ": "パプアニューギニア", "エメラルドマウンテン": "コロンビア"}


def fetch_menu_text() -> str:
    resp = requests.get(MENU_URL, headers=REQUEST_HEADERS, timeout=60)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")
    for t in soup(["script", "style"]):
        t.decompose()
    text = soup.get_text("\n", strip=True)
    return text


def scrape_all_products() -> list[dict]:
    text = fetch_menu_text()
    # 2列組のため、行内の左右の列は「●」の出現順に並ぶ。見出し(ブレンド/ストレート)は
    # 列の位置でしか区別できないため、各行のうち左側=ブレンド、右側=ストレートとする。
    rows = []
    for line in text.split("\n"):
        found = ROW_PATTERN.findall(line)
        if found:
            rows.append(found)

    records = []
    seen = set()
    for found in rows:
        for idx, (name, base_price, tax_price) in enumerate(found):
            name = re.sub(r"\s+", " ", name).strip()
            if not name or name in seen:
                continue
            seen.add(name)
            is_blend_col = (idx == 0 and len(found) == 2) or (len(found) == 1 and "ブレンド" in name)
            records.append((name, int(tax_price.replace(",", "")), is_blend_col))
    return build_records(records)


def build_records(rows: list[tuple[str, int, bool]]) -> list[dict]:
    records = []
    for name, price, is_blend_col in rows:
        norm = unicodedata.normalize("NFKC", name)
        parsed = parse_product(norm)
        is_blend = is_blend_col or "ブレンド" in norm
        if is_blend:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
            parsed["designated_brand"] = None
        else:
            parsed["category"] = "ストレート"
            if not parsed["origin_country"]:
                c = detect_country_name(norm)
                if c:
                    parsed["origin_country"] = c
                    parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, norm)
            if not parsed["origin_country"]:
                for kw, country in NAME_ORIGIN_OVERRIDES.items():
                    if kw in norm:
                        parsed["origin_country"], parsed["origin_source"] = country, "raw_name"
                        break
        roast_hint = norm if re.search(r"ロースト", norm) else None
        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": norm,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": parsed["roast_level"],
            "roast_hint": roast_hint,
            "flavor_notes": None,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": price,
            "weight_g": WEIGHT_G,
            "stock_status": "販売中",
            "out_of_stock": False,
            "product_url": MENU_URL + "#" + urllib.parse.quote(norm),
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_sansankushiro.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_sansankushiro.json に出力しました")


if __name__ == "__main__":
    main()
