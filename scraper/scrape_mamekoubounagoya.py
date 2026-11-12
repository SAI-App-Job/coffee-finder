# -*- coding: utf-8 -*-
"""
scrape_mamekoubounagoya.py

豆珈房(スペシャルティコーヒー豆珈房、https://www.mamekoubou.gr.jp/、愛知県名古屋市北区金城4-17-20
イオラニガーデン3-1F)の商品情報を取得する。おちゃのこネット(Ocnk)。
(scrape_mamekoubou.py は岩手県花巻市の別店「豆工房タカハシ」のため、slugを分けた。)

【店舗発見の経緯】
愛知県の未登録店発掘(disc3)で発見。「自家焙煎のコーヒー豆専門店」(https://www.mamekoubou.gr.jp/page/11)、
「13.5坪の小さなお店」で喫茶スペースなし(https://www.mamekoubou.gr.jp/page/12)。

【対象商品について】
実データ確認済み(2026-10時点): 商品一覧「シングルオリジン 全商品」(/product-list/10、45件)と
「ブレンド 全商品」(/product-list/8、11件)を対象とする。同一銘柄が100g/250g/500gの別商品として
並ぶため、銘柄名((NNNg)を除いた商品名)でグルーピングし、最小重量を代表とする
(シングルは全銘柄100g、ブレンドは250gが最小。ハロウィンブレンドのみ100g)。
セット・ギフト・ドリップ等を含む商品は除外。重量・焙煎度は詳細ページの「商品詳細」表
(内容量・焙煎度合)、産地は同表の原材料名(生豆生産国名)から取得する。価格は税込価格。
在庫は詳細ページのカートボタン(cart_add_btn)の有無で判定する。

【robots.txtについて】
GPTBot/Bytespider/TikTokSpider/meta-externalagentのみDisallow: /、それ以外は制限なし(2026-10確認)。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "豆珈房",
    "url": "https://www.mamekoubou.gr.jp/",
    "platform": "おちゃのこネット(Ocnk)",
    "address": "愛知県名古屋市北区金城4-17-20 イオラニガーデン3-1F",
    "prefecture": "愛知県",
    "robots_txt_status": "実質許可(2026-10確認。GPTBot等AI系ボットのみ個別にDisallow: /、それ以外は制限なし)",
    "source_note": "商品一覧(/product-list/10, /product-list/8)と各商品ページを2026-10-21に確認。住所は特商法表示(/info)、自家焙煎・実店舗は /page/11(自家焙煎のコーヒー豆専門店)・/page/12(13.5坪の小さなお店)。What's Newに2026-06-27の価格改定",
    "last_verified_at": "2026-10-21",
}

BASE_URL = "https://www.mamekoubou.gr.jp"
LIST_CATEGORIES = [10, 8]  # 10=シングルオリジン全商品, 8=ブレンド全商品
BLEND_CATEGORY = 8
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
CRAWL_DELAY_SECONDS = 2
NON_BEAN_KEYWORDS = ["セット", "ギフト", "ドリップ", "ディップ"]
WEIGHT_IN_NAME = re.compile(r"[（(]\s*(\d+)\s*[gｇ]\s*[)）]")


def fetch(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def list_items() -> list[dict]:
    items = []
    for cat in LIST_CATEGORIES:
        page = 1
        while True:
            url = f"{BASE_URL}/product-list/{cat}" + (f"?page={page}" if page > 1 else "")
            soup = fetch(url)
            for cell in soup.select("li.list_item_cell"):
                name_el = cell.select_one("p.item_name .goods_name")
                link = cell.select_one("a[href*='/product/']")
                price_el = cell.select_one("p.tax_incl_price .figure")
                if not (name_el and link and price_el):
                    continue
                name = unicodedata.normalize("NFKC", name_el.get_text(strip=True))
                m = WEIGHT_IN_NAME.search(name)
                if not m or any(kw in name for kw in NON_BEAN_KEYWORDS):
                    continue
                items.append({
                    "cat": cat,
                    "base_name": re.sub(r"\s+", " ", WEIGHT_IN_NAME.sub("", name)).strip(),
                    "weight": int(m.group(1)),
                    "price": int(re.sub(r"[^\d]", "", unicodedata.normalize("NFKC", price_el.get_text()))),
                    "url": link["href"],
                })
            if not soup.select_one("a.to_next_page"):
                break
            page += 1
            time.sleep(CRAWL_DELAY_SECONDS)
        time.sleep(CRAWL_DELAY_SECONDS)
    return items


def pick_canonical(items: list[dict]) -> list[dict]:
    best: dict[str, dict] = {}
    for it in items:
        ex = best.get(it["base_name"])
        if ex is None or it["weight"] < ex["weight"]:
            best[it["base_name"]] = it
    return list(best.values())


def detail_fields(url: str) -> dict:
    soup = fetch(url)
    spec = {}
    for tr in soup.select("table.data_table tr"):
        th, td = tr.find("th"), tr.find("td")
        if th and td:
            spec[th.get_text(strip=True)] = td.get_text(" ", strip=True)
    desc_el = soup.select_one("div.item_desc_text")
    desc = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", desc_el.get_text(" ", strip=True))) if desc_el else ""
    origin = None
    m = re.search(r"生豆生産国名\s*[:：]\s*([^)）]+)", spec.get("原材料名", ""))
    if m:
        origin = m.group(1).strip()
    return {
        "roast": spec.get("焙煎度合") or None,
        "desc": desc[:400] or None,
        "origin_raw": origin,
        "in_stock": soup.select_one('input[name="cart_add_btn"]') is not None,
    }


def build_record(it: dict) -> dict:
    d = detail_fields(it["url"])
    name = it["base_name"]
    parsed = parse_product(name)
    is_blend = it["cat"] == BLEND_CATEGORY or parsed["category"] == "ブレンド"
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
    roast = (d["roast"] or parsed["roast_level"])
    if roast:
        roast = roast.replace("｜", "・")
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast,
        "roast_hint": None,
        "flavor_notes": d["desc"],
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": it["price"],
        "weight_g": it["weight"],
        "stock_status": "販売中" if d["in_stock"] else "完売",
        "out_of_stock": not d["in_stock"],
        "product_url": it["url"],
    }


def scrape_all_products() -> list[dict]:
    records = []
    for it in pick_canonical(list_items()):
        time.sleep(CRAWL_DELAY_SECONDS)
        try:
            records.append(build_record(it))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {it['url']} ({e})")
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_mamekoubounagoya.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mamekoubounagoya.json に出力しました")


if __name__ == "__main__":
    main()
