# -*- coding: utf-8 -*-
"""
scrape_satocoffeebeans.py

さとう珈琲豆直売(SATO COFFEE ROASTERS、https://satocoffeebeans.ocnk.net/、岩手県宮古市向町5-1)の商品情報を取得する。おちゃのこネット(Ocnk)。

【対象商品について】
実データ確認済み(2026-11時点): 焙煎度別カテゴリ(product-list/8 浅煎り・9 中煎り・10 中深煎り・11 深煎り・12 より深煎り・13 カフェインレス)と
今月のシングル(23)の12商品。全て200g入りの1重量のみ(商品説明に「-200ｇ」)。豆のまま/挽くを選べる。
コーヒーバッグ・シロップ・ギフト・器具・グッズ・生豆水洗い・冊子等は対象外。
商品名は「キャッチコピー【焙煎度】名前」形式のため、【】の後ろを銘柄名とする。
産地は商品説明に明示されているものだけを採用する(ブレンドは産地なし)。商品説明が「ブレンド」と明記する銘柄はブレンド扱い。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "さとう珈琲豆直売",
    "url": "https://satocoffeebeans.ocnk.net/",
    "platform": "おちゃのこネット",
    "address": "岩手県宮古市向町5-1",
    "prefecture": "岩手県",
    "robots_txt_status": "実質許可(2026-11-03確認。robots.txtはGPTBot・Bytespider等の特定クローラのみ全面禁止で、それ以外は制限なし。識別可能なUser-Agentを使用)",
    "source_note": "販売先 https://satocoffeebeans.ocnk.net/ の焙煎度別カテゴリ(product-list/8〜13・23)と各商品ページ、店紹介(product/20)を2026-11-03に確認。住所はフッター・特商法表示。"
                   "店紹介に「さとう衣料店の駐車場をつぶし小屋を建て自家焙煎コーヒー店をはじめました」「フジローヤルの3キロ焙煎機」とあり、実店舗(焙煎小屋・売場)あり。商品説明の一部に古い発送案内(8月20日以降)が残る。",
    "last_verified_at": "2026-11-03",
}

BASE_URL = "https://satocoffeebeans.ocnk.net"
CATEGORIES = ["23", "8", "9", "10", "11", "12", "13"]
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 2
ROAST_PATTERN = re.compile(r"(中深煎り|中浅煎り|浅煎り|中煎り|深煎り)")
BRACKET = re.compile(r"【([^】]*)】\s*")
# 商品説明に産地が明示されている単一産地の銘柄(pid -> 国名)
ORIGIN_OVERRIDE = {
    "186": "コスタリカ",
    "150": "パプアニューギニア",
    "149": "タンザニア",
    "179": "ケニア",
}


def fetch_html(url: str) -> str:
    time.sleep(REQUEST_INTERVAL)
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def list_items() -> list[dict]:
    items: dict[str, dict] = {}
    for cat in CATEGORIES:
        soup = BeautifulSoup(fetch_html(f"{BASE_URL}/product-list/{cat}"), "html.parser")
        for cell in soup.select("li.list_item_cell"):
            a = cell.select_one("a.list_item_link")
            name_el = cell.select_one(".goods_name")
            if not (a and name_el):
                continue
            m = re.search(r"/product/(\d+)", a["href"])
            if not m or m.group(1) in items:
                continue
            price_el = cell.select_one(".selling_price .figure")
            pm = re.search(r"([\d,]+)", price_el.get_text()) if price_el else None
            items[m.group(1)] = {
                "pid": m.group(1),
                "title": re.sub(r"\s+", " ", unicodedata.normalize("NFKC", name_el.get_text(" ", strip=True))).strip(),
                "price": int(pm.group(1).replace(",", "")) if pm else None,
                "sold_out": "list_item_soldout" in cell.get("class", []),
            }
    return list(items.values())


def fetch_detail(pid: str) -> tuple[str | None, bool]:
    html_text = fetch_html(f"{BASE_URL}/product/{pid}")
    soup = BeautifulSoup(html_text, "html.parser")
    el = soup.select_one("div.item_desc_text")
    text = el.get_text("\n", strip=True) if el else None
    return text, "カートに入れる" in html_text


def main():
    records = []
    for item in list_items():
        if item["price"] is None:
            continue
        title = item["title"]
        bm = BRACKET.search(title)
        name = title[bm.end():].strip() if bm else title
        text, purchasable = fetch_detail(item["pid"])
        lines = [l for l in (text or "").split("\n") if l.strip() and not l.startswith("＊") and not l.startswith("■次回")]
        head = lines[0] if lines else ""
        is_decaf = "カフェインレス" in title or "デカフェ" in title
        is_blend = "ブレンド" in head or ("ブレンド" in name and not is_decaf)
        if is_decaf:
            name = "デカフェ ウォータープロセス"
        parsed = parse_product(name)
        if is_blend:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            parsed["category"] = "デカフェ" if is_decaf else "ストレート"
            if item["pid"] in ORIGIN_OVERRIDE:
                parsed["origin_country"] = ORIGIN_OVERRIDE[item["pid"]]
                parsed["origin_source"] = "description"
            parsed = apply_category_hint_fallback(parsed, name)
        rm = ROAST_PATTERN.search(title) or ROAST_PATTERN.search(head)
        roast = rm.group(1) if rm else None
        desc = re.sub(r"\s+", " ", " ".join(lines[1:]))[:400] or None
        weight = 200  # 商品説明の「-200ｇ」/「200g」
        sold_out = item["sold_out"] or not purchasable
        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": roast,
            "roast_hint": roast,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": item["price"],
            "weight_g": weight,
            "stock_status": "完売" if sold_out else "販売中",
            "out_of_stock": sold_out,
            "product_url": f"{BASE_URL}/product/{item['pid']}",
        })

    output = {"shop": SHOP_INFO, "products": records}
    with open("data_satocoffeebeans.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_satocoffeebeans.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], r["category"], r["origin_country"], r["processing_method"], r["roast_level"], r["price"], r["weight_g"], r["stock_status"])


if __name__ == "__main__":
    main()
