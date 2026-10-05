# -*- coding: utf-8 -*-
"""
scrape_iecafe.py

いえカフェ(coffee-iecafe.com、福岡県遠賀郡水巻町吉田南1-10-3の珈琲豆販売専門店)の商品情報を取得する。
WordPress(独自テーマ)で、商品は1ページ(/item/)に全件が並び、購入は /order/ のフォーム。

【対象商品について】
実データ確認済み(2026-10時点): /item/ の h4.style4a(商品名)+ table.coffee_item(原産国・ロースト・
酸味↔︎苦味・100g価格)で21商品(スタンダード9・プレミアム/スペシャルティ・オリジナル(ブレンド)・
その他(デカフェ、コピ・ルアック))。次は対象外: 「ドリップバッグコーヒー(要予約)」(DB春風等の5Pセット)、
いえカフェ ギフト(電話/メール注文)。

【重量・価格・在庫】
テーブルの列見出しが「100g価格」であり、全商品の価格は100gあたりの税込価格(重量100gを確認済み)。
在庫は商品ブロック内の「SOLD OUT」表記の有無(現在コピ・ルアックのみ品切れ)。
商品ごとの個別URLは無く商品一覧ページのみのため、product_urlは「/item/#<商品名>」のアンカー付きURLで
商品ごとに一意にする。
ローストは「ミディアム」「シティ」「フルシティ」「フレンチ」「ハイ」「イタリアン」(「～系」付きを含む)
の表記で、coffee_parserのROAST_KEYWORDSで標準表記へ変換して保持する。
ブレンドは原産国欄が「オリジナル」「プレミアム」の商品(オリジナル珈琲4種・ブルー・マウンテンNo1ブレンド)。
"""

import json
import re
import unicodedata
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, ROAST_KEYWORDS,
)

SHOP_INFO = {
    "name": "いえカフェ",
    "url": "https://coffee-iecafe.com/",
    "platform": "WordPress",
    "address": "福岡県遠賀郡水巻町吉田南1-10-3",
    "prefecture": "福岡県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://coffee-iecafe.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BLEND_ORIGIN_LABELS = ("オリジナル", "プレミアム")
UNIT_WEIGHT_G = 100


def normalize_roast(raw: str) -> str | None:
    key = re.sub(r"系$", "", unicodedata.normalize("NFKC", raw).strip())
    return ROAST_KEYWORDS.get(key)


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/item/", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")

    records = []
    for h4 in soup.select("h4.style4a"):
        row = h4.find_next_sibling("div", class_="post_row")
        table = row.select_one("table.coffee_item") if row else None
        if not table:
            continue  # ドリップバッグ(価格のみの5Pセット)等
        cells = [td.get_text(strip=True) for td in table.select("tbody tr td")]
        if len(cells) < 4:
            continue
        origin_raw, roast_raw, _taste, price_raw = cells[:4]
        title = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", h4.get_text(strip=True))).strip()
        pm = re.search(r"[\d,]+", price_raw)
        if not pm:
            continue
        price = int(pm.group(0).replace(",", ""))

        block_text = row.get_text(" ", strip=True)
        out_of_stock = bool(re.search(r"SOLD\s*OUT", block_text, re.I))
        # SOLD OUTはテーブル直後の別要素の場合があるため、次の見出しまでの兄弟要素も見る
        for sib in row.find_next_siblings():
            if sib.name in ("h3", "h4"):
                break
            if re.search(r"SOLD\s*OUT", sib.get_text(" ", strip=True), re.I):
                out_of_stock = True

        well = row.select_one("p.well")
        desc = well.get_text(" ", strip=True) if well else ""
        desc = re.sub(r"^【特徴】\s*", "", desc)
        flavor_notes = re.sub(r"\s+", " ", desc)[:400] or None

        origin_label = unicodedata.normalize("NFKC", origin_raw).strip()
        is_blend = origin_label in BLEND_ORIGIN_LABELS
        parsed = parse_product(title)
        if is_blend:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
            parsed["designated_brand"] = None
            parsed["processing_method"] = None
        else:
            parsed["category"] = "ストレート"
            if not parsed["origin_country"]:
                c = detect_country_name(origin_label)
                if c:
                    parsed["origin_country"] = c
                    parsed["origin_source"] = "description"
                elif origin_label:
                    # 原産国欄の表記をそのまま採用(キューバ等、辞書にない産地国)
                    parsed["origin_country"] = origin_label
                    parsed["origin_source"] = "description"
            parsed = apply_category_hint_fallback(parsed, title)

        roast_level = normalize_roast(roast_raw)
        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": roast_level,
            "roast_hint": unicodedata.normalize("NFKC", roast_raw).strip() or None,
            "flavor_notes": flavor_notes,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": price,
            "weight_g": UNIT_WEIGHT_G,
            "stock_status": "完売" if out_of_stock else "販売中",
            "out_of_stock": out_of_stock,
            "product_url": f"{BASE_URL}/item/#{quote(title)}",
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_iecafe.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_iecafe.json に出力しました")


if __name__ == "__main__":
    main()
