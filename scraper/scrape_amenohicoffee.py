# -*- coding: utf-8 -*-
"""
scrape_amenohicoffee.py

雨の日の珈琲(amenohi-coffee.jp、千葉県柏市あけぼの4-4-2 ライネスハイム柏107、柏駅徒歩6分、
店主 久保田プルート、熱風式焙煎機による深煎り中心の自家焙煎豆売所)の商品情報を取得する。
ショップサーブ(ShopServe、UTF-8)。

【店舗発見の経緯】
千葉県の自家焙煎店調査(ショップサーブ系)で発見。

【対象商品について】
実データ確認済み(2026-10時点): 「自家焙煎豆一覧」(/SHOP/105461/list.html)は
全33件が1ページに収まり、すべてコーヒー豆(ストレート・オリジナルブレンド)。
うち「50グラム×3種 エチオピア グジ Sookoo 3種お試しセット 合計150グラム」(複数銘柄の
セット)を除く32件(ストレート28・ブレンド4)を収録する。
同一銘柄の複数サイズ展開は無く、1商品1サイズ(200グラム、希少ロットは100グラム)。
重量は商品名の「200グラム」「100グラム」から取り、名前の前後の重量表記は除去する。
価格は税込。在庫は一覧の「在庫 N個」から判定し、0個または「在庫切れ/売り切れ」表記なら
完売とする(2026-10時点は全件在庫あり)。
一覧の説明文(div.expl)をflavor_notesとする(詳細ページは説明が一覧と同内容のため未取得)。
銘柄名の「タイ フアチャン」は国名「タイ」が辞書に無い(部分文字列の誤爆回避のため)ので
ORIGIN_OVERRIDESで補う。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "雨の日の珈琲",
    "url": "https://amenohi-coffee.jp/",
    "platform": "ショップサーブ",
    "address": "千葉県柏市あけぼの4-4-2 ライネスハイム柏107",
    "prefecture": "千葉県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://amenohi-coffee.jp"
LIST_URL = f"{BASE_URL}/SHOP/105461/list.html"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_KEYWORDS = ("セット", "ギフト", "ドリップ", "リキッド", "おまかせ")
MAX_PAGES = 10

# 商品名の先頭語から国名を補う(辞書は「タイ」を誤爆防止のため含まない)
ORIGIN_OVERRIDES = {
    "タイ ": "タイ",
}

PRICE_PATTERN = re.compile(r"([\d,]+)\s*円")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*グラム")
ROAST_PATTERN = re.compile(r"(ライト|シナモン|ミディアム|ハイ|フルシティ|シティ|フレンチ|イタリアン)ー?ロースト")
STOCK_PATTERN = re.compile(r"在庫\s*(\d+)\s*個")


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def list_items() -> list[dict]:
    items, seen = [], set()
    for page in range(1, MAX_PAGES + 1):
        url = LIST_URL if page == 1 else LIST_URL.replace("list.html", f"list{page}.html")
        soup = BeautifulSoup(fetch(url), "html.parser")
        new = 0
        for card in soup.select("div.layout1"):
            a = card.select_one("h2.goods a")
            if not a:
                continue
            href = a.get("href", "")
            if href in seen:
                continue
            seen.add(href)
            new += 1
            price_el = card.select_one("div.price")
            price_m = PRICE_PATTERN.search(price_el.get_text()) if price_el else None
            expl = card.select_one("div.expl")
            card_text = card.get_text(" ", strip=True)
            stock_m = STOCK_PATTERN.search(card_text)
            sold_out = ("在庫切れ" in card_text or "売り切れ" in card_text
                        or (stock_m is not None and int(stock_m.group(1)) == 0))
            items.append({
                "title": re.sub(r"\s+", " ", a.get_text(strip=True)).strip(),
                "path": href,
                "price": int(price_m.group(1).replace(",", "")) if price_m else None,
                "desc": re.sub(r"\s+", " ", expl.get_text(" ", strip=True)).strip() if expl else None,
                "sold_out": sold_out,
            })
        if new == 0:
            break
    return items


def build_record(item: dict) -> dict | None:
    title = item["title"]
    if any(kw in title for kw in EXCLUDE_KEYWORDS):
        return None
    norm = unicodedata.normalize("NFKC", title)
    weight_m = WEIGHT_PATTERN.search(norm)
    weight_g = int(weight_m.group(1)) if weight_m else None

    # 先頭「100グラム 」・末尾「200グラム」「（200グラム）」の重量表記を除去
    name = norm
    name = re.sub(r"^\d+\s*グラム\s*", "", name)
    name = re.sub(r"[（(]\s*\d+\s*グラム\s*[）)]\s*$", "", name)
    name = re.sub(r"\s*\d+\s*グラム\s*$", "", name)
    name = re.sub(r"\s+", " ", name).strip()

    parsed = parse_product(name)
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        override = next((c for k, c in ORIGIN_OVERRIDES.items() if name.startswith(k)), None)
        detected = override or detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        # 「ハイブリッドウォッシュ」の「ハイ」等への誤爆を避け、「○○ロースト」明示表記のみ採用
        "roast_level": (ROAST_PATTERN.search(name).group(1) + "ロースト") if ROAST_PATTERN.search(name) else None,
        "roast_hint": None,
        "flavor_notes": item["desc"],
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": weight_g,
        "stock_status": "完売" if item["sold_out"] else "販売中",
        "out_of_stock": item["sold_out"],
        "product_url": f"{BASE_URL}{item['path']}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in list_items():
        record = build_record(item)
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_amenohicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_amenohicoffee.json に出力しました")


if __name__ == "__main__":
    main()
