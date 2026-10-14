# -*- coding: utf-8 -*-
"""
scrape_coffeeclubmarugame.py

珈琲倶楽部(丸亀、0024coffee.com、香川県丸亀市今津町259-10)の商品情報を取得する。EC-CUBE 3系。
喫茶店併設の自家焙煎店(店長・煎り人による注文ごとの焙煎)。

【店名・slug】
東京都東大和市の「珈琲倶楽部」(scrape_coffeeclub.py)が既に登録済みで、統合時に店名で照合すると
衝突するため、店名を「珈琲倶楽部 丸亀」とし、slugは coffeeclubmarugame とする。

【住所】
実データ確認済み(2026-10-15): 特定商取引法表記(/help/tradelaw)・珈琲倶楽部について(/help/about)とも
「〒763-0051 香川県丸亀市今津町259-10」で一致。

【対象商品】
実データ確認済み: 全商品一覧(/products/list、77件)から、ドリップバッグ7・ダッチコーヒー(水出し、
ボトル品)9・オフィス業務用2kg(500g×4)1を除いた焙煎豆60件を収録する(ブレンド・ストレート・デカフェ)。
同一銘柄の焙煎度違い(【さんみ】浅煎り/【まいるど】中煎り/【ほろにが】中深煎り/【にがにが】深煎り、
サイトの焙煎段階表による)は別商品ページ(別ID)として並ぶため、別商品として全て収録する。
各商品は100g〜400gの重量選択式で、一覧の表示価格(100g～)=最小重量100gの価格を採用する。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import apply_category_hint_fallback, parse_product

SHOP_INFO = {
    "name": "珈琲倶楽部 丸亀",
    "url": "https://www.0024coffee.com/",
    "platform": "EC-CUBE(独自サイト)",
    "address": "香川県丸亀市今津町259-10",
    "prefecture": "香川県",
    "robots_txt_status": "許可(2026-10確認。Disallow: /*.csv$ のみ)",
}

BASE_URL = "https://www.0024coffee.com"
LIST_URL = BASE_URL + "/products/list?disp_number=50&pageno={page}"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 1.5

# (キーワード, 除外理由)
EXCLUDE_RULES = [
    ("ドリップバッグ", "ドリップバッグ"),
    ("ダッチコーヒー", "水出し(ダッチ)コーヒーのボトル品"),
    ("オフィス", "事業者向け大容量(業務用2kg)"),
]
ROAST_BY_TASTE = {"さんみ": "浅煎り", "まいるど": "中煎り", "ほろにが": "中深煎り", "にがにが": "深煎り"}
ORIGIN_OVERRIDES = {
    "グァテマラ": "グアテマラ",
    "エチオピアモカ": "エチオピア",
    "イエメンモカ": "イエメン",
    "ハワイ コナ": "アメリカ(ハワイ)",
    "ジャマイカ ブルーマウンテン": "ジャマイカ",
}
BLEND_NAMES = ("みちのくブレンド", "昭和の珈琲", "おまかせブレンド", "ブルーマウンテン ブレンド")


def fetch(url: str) -> BeautifulSoup:
    for attempt in range(5):
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
        if resp.status_code in (429, 502, 503, 504) and attempt < 4:
            time.sleep(5 * (attempt + 1))
            continue
        resp.raise_for_status()
        break
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def list_items() -> list[dict]:
    items, seen = [], set()
    for page in range(1, 6):
        soup = fetch(LIST_URL.format(page=page))
        time.sleep(CRAWL_DELAY_SECONDS)
        found = 0
        for it in soup.select("div.product_item"):
            a = it.select_one("a[href*='/products/detail/']")
            name_el = it.select_one(".item_name")
            if not a or not name_el:
                continue
            href = a["href"]
            if href in seen:
                continue
            seen.add(href)
            found += 1
            price_text = it.select_one(".item_price").get_text(" ", strip=True)
            w = re.search(r"(\d+)\s*g", price_text)
            p = re.search(r"¥\s*([\d,]+)", price_text)
            comment = it.select_one(".item_comment")
            items.append({
                "title": name_el.get_text(strip=True),
                "product_url": href,
                "weight_g": int(w.group(1)) if w else None,
                "price": int(p.group(1).replace(",", "")) if p else None,
                "comment": comment.get_text(strip=True) if comment else None,
            })
        if found == 0:
            break
    return items


def detail(url: str) -> dict:
    soup = fetch(url)
    box = soup.select_one("#detail_wrap")
    for t in box(["script", "style"]):
        t.decompose()
    text = box.get_text("\n", strip=True)
    head = text.split("１：まず")[0]
    lines = []
    for ln in head.split("\n"):
        ln = ln.strip()
        if ln and ln not in lines:
            lines.append(ln)
    # 先頭行は商品名
    desc = " ".join(lines[1:]) if len(lines) > 1 else None
    sold_out = bool(re.search(r"売り切れ|SOLD ?OUT|在庫切れ|品切れ", text)) or "カートに入れる" not in text
    return {"desc": desc, "sold_out": sold_out}


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    records, excluded = [], []
    for item in list_items():
        title = unicodedata.normalize("NFKC", item["title"])
        reason = next((r for kw, r in EXCLUDE_RULES if kw in title), None)
        if reason:
            excluded.append({"raw_name": item["title"], "product_url": item["product_url"], "reason": reason})
            continue
        d = detail(item["product_url"])
        time.sleep(CRAWL_DELAY_SECONDS)
        name = re.sub(r"\s+", " ", title).strip()
        taste = re.search(r"【(さんみ|まいるど|ほろにが|にがにが)】", name)
        roast_hint = ROAST_BY_TASTE.get(taste.group(1)) if taste else None
        is_blend = any(name.startswith(b) for b in BLEND_NAMES)
        is_decaf = name.startswith("デカフェ")
        parsed = parse_product(name)
        if is_blend:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            if not parsed["origin_country"]:
                for kw, country in ORIGIN_OVERRIDES.items():
                    if name.startswith(kw):
                        parsed["origin_country"] = country
                        parsed["origin_source"] = "raw_name"
                        break
            parsed = apply_category_hint_fallback(parsed, None)
        sold = d["sold_out"]
        stock_status = "一時的に品切れ" if sold else "販売中"
        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": "デカフェ" if is_decaf else parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": parsed["roast_level"],
            "roast_hint": roast_hint,
            "flavor_notes": d["desc"] or item["comment"],
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": item["price"],
            "weight_g": item["weight_g"],
            "stock_status": stock_status,
            "out_of_stock": sold,
            "product_url": item["product_url"],
        })
    return records, excluded


if __name__ == "__main__":
    records, excluded = scrape_all_products()
    with open("data_coffeeclubmarugame.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records, "excluded_products": excluded},
                  f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeeclubmarugame.json に出力しました(除外{len(excluded)}件)")
