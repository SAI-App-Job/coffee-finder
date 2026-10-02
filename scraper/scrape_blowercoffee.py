# -*- coding: utf-8 -*-
"""
scrape_blowercoffee.py

BLOWER COFFEE ROASTERY(千葉県館山市宮城78-3、blowercoffee.com。敷地内の焙煎所で自家焙煎、
ブラウニー・玄米珈琲・アンティークミルも扱う店舗は1店のみ)の商品情報を取得する。
Digital Stage系のCMSで作られた静的サイトで、トップページの「NET SHOPPING 〜産地・銘柄指定買い〜」
に銘柄指定の豆が並ぶ(ショッピングカートは別ページ)。トップページの最終更新は2026-09-25。

【対象商品について】
実データ確認済み(2026-10時点): 産地・銘柄指定買いの5銘柄(インド モンスーン、インドネシア マンデリン、
ブラジル 山口農園 ナチュラル、エチオピア イルガチェフェ ナチュラル、グアテマラ ウォッシュト)を対象とする。
「珈琲定期便」「豆まとめ買い」「お任せ3種/5種セット」「ブラウニー詰め合わせ」「リキッドコーヒー」
「玄米珈琲」「アンティークミル」は豆単品ではないため除外。

【価格・重量について】
各銘柄は「円(税込)/100g」と「円(税込)/200g」の2サイズ併記で、最小サイズの100g価格を採用する。
価格は生豆の仕入値により予告なく変更されるとの注記あり。HTML上で数字が途中で分断される表記
(例「80 0」「1,5 00」)があるため、数字間の空白を除去してから解析する。
焙煎度は銘柄ごとに「ハイ〜フレンチ」の中から最適に設定する旨の説明のみで個別の指定が無いため
roast_levelはNone。在庫表示は無いため全て販売中扱い。商品ごとのURLが無いためトップページURLに
銘柄名のフラグメントを付けて一意にする。
"""

import json
import re
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "BLOWER COFFEE ROASTERY",
    "url": "https://blowercoffee.com/",
    "platform": "独自CMS(Digital Stage系)+ショッピングカート",
    "address": "千葉県館山市宮城78-3",
    "prefecture": "千葉県",
    "robots_txt_status": "未確認",
}

PAGE_URL = "https://blowercoffee.com/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

ITEM_PATTERN = re.compile(
    r"(\S+)\s+(.+?)\s+([\d,]+)円（税込）／100g\s+([\d,]+)円（税込）／200g"
)


def scrape_all_products() -> list[dict]:
    resp = requests.get(PAGE_URL, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")
    for t in soup(["script", "style"]):
        t.decompose()
    text = soup.get_text(" ", strip=True)
    text = re.sub(r"(?<=[\d,])\s+(?=[\d,])", "", text)
    text = re.sub(r"(?<=\d)\s+円", "円", text)

    start = text.find("予めご了承ください")
    end = text.find("リキッドコーヒー", start)
    segment = text[start + len("予めご了承ください"):end if end > 0 else None]

    records = []
    for m in ITEM_PATTERN.finditer(segment):
        country_word, item_name = m.group(1), re.sub(r"[\s　]+", " ", m.group(2)).strip()
        name = f"{country_word} {item_name}"
        price = int(m.group(3).replace(",", ""))

        parsed = parse_product(name)
        parsed["category"] = "ストレート"
        if not parsed["origin_country"]:
            c = detect_country_name(country_word)
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": None,
            "roast_hint": None,
            "flavor_notes": None,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": price,
            "weight_g": 100,
            "stock_status": "販売中",
            "out_of_stock": False,
            "product_url": f"{PAGE_URL}#{quote(name)}",  # 商品個別URLが無いため、商品IDを一意にするフラグメントを付ける
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_blowercoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_blowercoffee.json に出力しました")


if __name__ == "__main__":
    main()
