# -*- coding: utf-8 -*-
"""
scrape_cafelutra.py

Cafe Lutra(カフェ・ルトラ、cafe-lutra.com、千葉県市川市大野町4-3154-22、深煎りの
自家焙煎珈琲専門店)の商品情報を取得する。公式サイトはWordPress製。

【自家焙煎・営業状況の確認(2026-10)】
・公式サイトのトップに2026-10-02付の「１０月の営業」等の最近の投稿があり営業中。
・オンラインショップ(cafe-lutra.shop-pro.jp)は「2025年11月3日にて閉店」とあるが、
  同店の特商法ページに「基本的に毎週火曜日に焙煎しており」とあり自家焙煎を確認。
  通信販売は問い合わせフォーム経由で継続(cafe-lutra.com/mail-order/)。

【対象商品について】
ショップ(カラーミー)は閉店済みのため使わず、公式サイトの現行の価格表
https://cafe-lutra.com/bean/ (「店内で挽き売りしております(通信販売も行っております)。
値段は100gの値段(税込)です」)の表を対象とする。
  ・ブレンドコーヒー(12種。「アイスコーヒー」を含む)→ category ブレンド
  ・ストレートコーヒー(約30種)
  ・カフェインレスコーヒー(コロンビア・スプレモ)
  ・ピーベリー(事前注文制。要注文の3種)
  ・https://cafe-lutra.com/usual-blendub/ の「Usual Blend(UB)」100g 500円(ブレンド)
ドリップバッグ・水出しコーヒーバッグ・手拭い・喫茶メニューは対象外。
全て100gの価格のため重量は100g。★(常に在庫あり)・△(在庫不定、要問い合わせ)は
完売を意味しないため全て「販売中」とし、flavor_notesに在庫表記を残す。
商品URLは価格表が1ページのため「#商品名」のフラグメントで一意化する。
商品名から産地が判別できない銘柄はORIGIN_OVERRIDESで補う
(モカ系=エチオピア産の地域/ステーション名、ジャバ・ロブスタ=インドネシア)。
"""

import json
import re
import unicodedata
import urllib.parse

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "Cafe Lutra",
    "url": "https://cafe-lutra.com/",
    "platform": "独自サイト(WordPress・店頭価格表)",
    "address": "千葉県市川市大野町4丁目3154-22",
    "prefecture": "千葉県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://cafe-lutra.com"
BEAN_URL = f"{BASE_URL}/bean/"
UB_URL = f"{BASE_URL}/usual-blendub/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# 銘柄名から国名が判別できないもの(エチオピア産のモカ系は地域・ステーション名による)
ORIGIN_OVERRIDES = {
    "エル・サルバドル": "エルサルバドル",
    "ジャバ・ロブスタ": "インドネシア",
    "モカ・レケンプティ": "エチオピア",
    "モカ・イルガチェフェ": "エチオピア",
    "モカ・グジ": "エチオピア",
    "モカ・ボンベ": "エチオピア",
    "モカ・シャキッソ": "エチオピア",
}

SECTION_CATEGORY = {
    "ブレンドコーヒー": "ブレンド",
    "ストレートコーヒー": "ストレート",
    "カフェインレスコーヒー": "ストレート",
}

PRICE_PATTERN = re.compile(r"([\d,]+)\s*円")
STOCK_NOTE = {"★": "在庫:常時あり", "△": "在庫:不定(要問い合わせ)"}


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def make_record(raw_name: str, category: str, price: int, product_url: str, note: str | None) -> dict:
    parsed = parse_product(raw_name)
    if category == "ブレンド":
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["processing_method"] = None  # 「スマトラカワウソ」等の銘柄名由来の誤検出を避ける
    else:
        parsed["category"] = "ストレート"
        override = next((c for k, c in ORIGIN_OVERRIDES.items() if k in raw_name), None)
        detected = override or detect_country_name(raw_name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, raw_name)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": raw_name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": note,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": 100,
        "stock_status": "販売中",
        "out_of_stock": False,
        "product_url": product_url,
    }


def scrape_price_list() -> list[dict]:
    soup = BeautifulSoup(fetch(BEAN_URL), "html.parser")
    records = []
    for fig in soup.select("figure.wp-block-table"):
        # 表の直前の見出し段落(ブレンドコーヒー/ストレートコーヒー/…)
        heading_el = fig.find_previous_sibling("p")
        heading = unicodedata.normalize("NFKC", heading_el.get_text(strip=True)) if heading_el else ""
        for tr in fig.select("tr"):
            tds = tr.find_all("td")
            if len(tds) < 3:
                continue
            marker = tds[0].get_text(strip=True)
            name = re.sub(r"\s+", "", unicodedata.normalize("NFKC", tds[1].get_text("", strip=True)))
            price_text = unicodedata.normalize("NFKC", tds[2].get_text(strip=True))
            price_m = PRICE_PATTERN.search(price_text)
            if not name or not price_m:
                continue
            price = int(price_m.group(1).replace(",", ""))
            notes = [STOCK_NOTE[marker]] if marker in STOCK_NOTE else []

            if heading.startswith("ピーベリー"):
                category = "ストレート"
                name = f"{name} ピーベリー"
                notes.append("要事前注文")
            elif heading.startswith("カフェインレス"):
                category = "ストレート"
                name = f"{name} カフェインレス"
            else:
                category = SECTION_CATEGORY.get(heading)
                if category is None:
                    continue
            records.append(make_record(
                name, category, price,
                f"{BEAN_URL}#{urllib.parse.quote(name)}",
                " / ".join(notes) or None,
            ))
    return records


def scrape_usual_blend() -> list[dict]:
    text = unicodedata.normalize("NFKC", BeautifulSoup(fetch(UB_URL), "html.parser").get_text("\n", strip=True))
    m = re.search(r"100\s*g\s*([\d,]+)\s*円", text)
    if not m:
        return []
    return [make_record("Usual Blend(UB)", "ブレンド", int(m.group(1).replace(",", "")), UB_URL,
                        "選別ではじかれた豆を焙煎したサービスコーヒー用の普段使いブレンド(不揃い・味は均一でない)")]


def scrape_all_products() -> list[dict]:
    return scrape_price_list() + scrape_usual_blend()


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_cafelutra.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_cafelutra.json に出力しました")


if __name__ == "__main__":
    main()
