# -*- coding: utf-8 -*-
"""
scrape_chitosecoffee.py

金澤ちとせ珈琲(chitose-coffee.com、石川県金沢市長坂台1-41〈長坂台店。ほか香林坊店・カフェ コンチェルト〉、
運営 有限会社バンボウ)のネットショップ(www.chitose-shop.com、おちゃのこネット〈Ocnk〉)の
商品情報を取得する。

【店舗発見の経緯】
全国再調査(石川県)の新規発掘で発見。

【robots.txtについて】
実データ確認済み(2026-10-12): robots.txtはGPTBot等の特定AIクローラのみDisallow。
User-agent: *への制限は無く実質許可。識別可能な独自User-Agentを使用する。

【対象商品について】
実データ確認済み(2026-10-12時点): 「オリジナルブレンドコーヒー豆」(product-list/2、6件)と
「産地別コーヒー豆」(product-list/3、7件〈デカフェ1件を含む〉)の計13件。
カップ・ドリッパー・リキッドアイス・ドリップカフェ・ギフト・チョコレートは対象外。
各商品は「１パック当たりの量: 100g〜500g」のプルダウンで量を選ぶ形式で、表示価格は
最小の100g分(価格は「オプションにより価格が変わる場合もあります」とあるが、一覧・詳細の
表示価格を100gの価格として採用する)。
価格は一覧に「780円(税別)(税込:842円)」と両方が表示されるため、他店との整合のため
税込(842円)を採用する。ブレンドの焙煎度は所属カテゴリ(中煎りブレンド/深煎りブレンド/
浅煎りブレンド)から取る。産地別の焙煎度は商品ページに記載が無いためnull。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, normalize_processing_method,
)

SHOP_INFO = {
    "name": "金澤ちとせ珈琲",
    "url": "https://www.chitose-shop.com/",
    "platform": "おちゃのこネット",
    "address": "石川県金沢市長坂台1-41(長坂台店)",
    "prefecture": "石川県",
    "robots_txt_status": "実質許可(2026-10-12確認。GPTBot等の特定クローラのみDisallow、User-agent: *への制限なし)",
}

BASE_URL = "https://www.chitose-shop.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CATEGORIES = [("2", "blend"), ("3", "single")]
ROAST_CATEGORIES = {"16": "中煎り", "17": "深煎り", "18": "浅煎り"}  # ブレンドの焙煎度カテゴリ
BASE_WEIGHT_G = 100
SOLD_OUT_PATTERN = re.compile(r"売り切れ|売切れ|SOLD\s*OUT|在庫切れ|品切れ", re.IGNORECASE)


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def parse_cells(html_text: str) -> list[dict]:
    out = []
    for cell in BeautifulSoup(html_text, "html.parser").select("li.list_item_cell"):
        a = cell.select_one("a[href*='/product/']")
        name_el = cell.select_one(".goods_name")
        m = re.search(r"/product/(\d+)", a["href"]) if a else None
        if not (m and name_el):
            continue
        price_el = cell.select_one(".tax_incl_price .figure")
        pm = re.search(r"([\d,]+)", price_el.get_text()) if price_el else None
        out.append({
            "pid": m.group(1),
            "name": unicodedata.normalize("NFKC", re.sub(r"\s+", " ", name_el.get_text(" ", strip=True))).strip(),
            "price": int(pm.group(1).replace(",", "")) if pm else None,
            "sold_out": "list_item_soldout" in cell.get("class", []),
        })
    return out


def list_items() -> list[dict]:
    items: dict[str, dict] = {}
    for cat_id, group in CATEGORIES:
        for it in parse_cells(fetch_html(f"{BASE_URL}/product-list/{cat_id}")):
            if it["pid"] not in items:
                items[it["pid"]] = dict(it, group=group, roast=None)
    for cat_id, roast in ROAST_CATEGORIES.items():
        for it in parse_cells(fetch_html(f"{BASE_URL}/product-list/{cat_id}")):
            if it["pid"] in items:
                items[it["pid"]]["roast"] = roast
    return list(items.values())


def fetch_detail(pid: str) -> tuple[str | None, str | None, bool]:
    soup = BeautifulSoup(fetch_html(f"{BASE_URL}/product/{pid}"), "html.parser")
    el = soup.select_one("div.item_desc_text")
    text = el.get_text("\n", strip=True) if el else ""
    stock = soup.select_one(".stock_status, .item_stock, .stock")
    sold_out = bool(stock and SOLD_OUT_PATTERN.search(stock.get_text()))
    return (text or None), (re.sub(r"\s+", " ", text)[:400] or None), sold_out


def scrape_all_products() -> list[dict]:
    records = []
    for it in list_items():
        if it["price"] is None:
            continue
        full_desc, desc, detail_sold_out = fetch_detail(it["pid"])
        name = it["name"]
        parsed = parse_product(name)
        if it["group"] == "blend" or "ブレンド" in name:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
            parsed["designated_brand"] = None
        else:
            parsed["category"] = "ストレート"
            if not parsed["origin_country"]:
                c = detect_country_name(name)
                if c:
                    parsed["origin_country"] = c
                    parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, name)
        if not parsed["processing_method"] and full_desc:
            m = re.search(r"・精製方法\s+(.+)", full_desc)
            parsed["processing_method"] = normalize_processing_method(m.group(1).strip()) if m else None
        farm = None
        if full_desc:
            bits = []
            for key in ("産地", "農園", "品種"):
                m = re.search(rf"・{key}\s+(.+)", full_desc)
                if m:
                    bits.append(f"{key}: {m.group(1).strip()}")
            farm = "、".join(bits) or None
        sold_out = it["sold_out"] or detail_sold_out
        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": it["roast"] or parsed["roast_level"],
            "roast_hint": it["roast"],
            "flavor_notes": desc,
            "farm_note": farm,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": it["price"],
            "weight_g": BASE_WEIGHT_G,
            "stock_status": "完売" if sold_out else "販売中",
            "out_of_stock": sold_out,
            "product_url": f"{BASE_URL}/product/{it['pid']}",
        })
        time.sleep(0.3)
    return records


def main():
    records = scrape_all_products()
    with open("data_chitosecoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_chitosecoffee.json に出力しました")


if __name__ == "__main__":
    main()
