# -*- coding: utf-8 -*-
"""
scrape_iwashitacoffee.py

岩下珈琲(iwashita-coffee.com、熊本県菊池郡菊陽町光の森7-52-3)の商品情報を取得する。
インドネシア産コーヒー専門(無農薬コーヒー)の自家焙煎店。EC-CUBE系の独自カート
(/products/list.php、/products/detail.php?product_id=N)。

【店舗発見の経緯】
全国再調査(熊本県)の新規発掘。

【対象商品について】
実データ確認済み(2026-10時点): カテゴリ「コーヒー豆」(category_id=1)全15件
(1ページ)すべてを対象とする。ドリップパック(category_id=2)、ドリップパックセット(4)、
ギフト商品(3)は対象外。インドネシア産に特化しており、産地の国名は商品名に無いが、
各商品ページの「コーヒー豆の産地」(スマトラ島・スラウェシ島・ジャワ島・バリ島・
アチェ州・パプア州等)の記述からインドネシアとする。ブレンド3件(光の森ブレンド、
ネシアン・ブレンド、アイスコーヒーブレンド)は産地None。

【重量・価格・在庫】
一覧の「200g - 販売価格」(一部は100g)の税込価格をそのまま採用する(200gからの購入)。
販売停止中の「天空の豆」「ザ・ワメナ」は価格が0円表示のため価格None。
在庫は一覧の「只今入荷待ち」ラベル(p-common-label)で判定し、入荷待ちは「完売」として扱う。
焙煎度は購入時に選択するオプション(浅煎り/中煎り/深煎り)で、選択肢が1つの商品のみ
その焙煎度を採用し、複数の商品はNone(roast_hintに選択肢を残す)。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product

SHOP_INFO = {
    "name": "岩下珈琲",
    "url": "https://iwashita-coffee.com/",
    "platform": "EC-CUBE系独自カート",
    "address": "熊本県菊池郡菊陽町光の森7-52-3",
    "prefecture": "熊本県",
    "tel": "096-284-1713",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://iwashita-coffee.com"
LIST_URL = f"{BASE_URL}/products/list.php?category_id=1"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BLEND_KEYWORDS = ("ブレンド",)


def fetch(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    return BeautifulSoup(resp.content.decode("utf-8", errors="replace"), "html.parser")


def parse_list() -> list[dict]:
    soup = fetch(LIST_URL)
    items = []
    for li in soup.select("li.p-section-productList__item"):
        a = li.select_one("a.p-section-productList__link")
        name_el = li.select_one(".p-section-productList__name")
        if not a or not name_el:
            continue
        m = re.search(r"product_id=(\d+)", a["href"])
        if not m:
            continue
        price_el = li.select_one("p.p-section-productList__price span.price span[id^=price02_default]")
        price = None
        if price_el:
            pm = re.search(r"([\d,]+)", price_el.get_text())
            if pm:
                price = int(pm.group(1).replace(",", "")) or None
        wm = re.search(r"(\d+)\s*g", li.select_one("p.p-section-productList__price").get_text()) if li.select_one("p.p-section-productList__price") else None
        label = li.select_one(".p-common-label")
        items.append({
            "id": m.group(1),
            "name": name_el.get_text(strip=True),
            "roasts": [t.get_text(strip=True) for t in li.select(".c-cat-tag")],
            "desc": (li.select_one(".p-section-productList__text").get_text(strip=True)
                     if li.select_one(".p-section-productList__text") else None),
            "price": price,
            "weight_g": int(wm.group(1)) if wm else None,
            "sold_out": bool(label and "入荷待ち" in label.get_text()),
        })
    return items


def fetch_origin_text(pid: str) -> str | None:
    text = fetch(f"{BASE_URL}/products/detail.php?product_id={pid}").get_text("\n", strip=True)
    start = text.find("Producing Area")
    end = text.find("クレジットカード決済", start)
    if start < 0:
        return None
    body = re.sub(r"\s+", " ", text[start + len("Producing Area"):end]).strip()
    return body or None


def build_record(item: dict) -> dict:
    name = item["name"]
    parsed = parse_product(name)
    is_blend = any(kw in name for kw in BLEND_KEYWORDS)
    farm_note = fetch_origin_text(item["id"])
    if is_blend:
        category, origin, origin_source = "ブレンド", None, None
    else:
        category, origin, origin_source = "ストレート", "インドネシア", "description"
    roasts = item["roasts"]
    sold_out = item["sold_out"]
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": category,
        "origin_country": origin,
        "origin_source": origin_source,
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roasts[0] if len(roasts) == 1 else None,
        "roast_hint": "/".join(roasts) if len(roasts) > 1 else None,
        "flavor_notes": item["desc"],
        "farm_note": farm_note,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": item["weight_g"],
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/products/detail.php?product_id={item['id']}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in parse_list():
        if item["price"] is None:
            continue  # 価格0円表示(問い合わせ品)は価格不明のため収録しない
        try:
            records.append(build_record(item))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: product_id={item['id']} ({e})")
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_iwashitacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_iwashitacoffee.json に出力しました")


if __name__ == "__main__":
    main()
