# -*- coding: utf-8 -*-
"""
scrape_anchorcoffee.py

ANCHOR COFFEE(アンカーコーヒー、anchor2fullsail.shop-pro.jp、宮城県気仙沼市館山1-6-31、
マザーポート店併設の焙煎工房)の商品情報を取得する。カラーミーショップ(shop-pro.jp)、EUC-JP。
アンカー/フルセイル/マザーポート共通の通販サイト。

【住所について】
特定商取引法ページ(?mode=sk、運営: 株式会社オノデラコーポレーション)の住所が
「宮城県気仙沼市館山1丁目6番31号」で、マザーポート店(焙煎工房併設)の所在地と一致する
ことを確認(2026-10)。

【対象商品】
実データ確認済み(2026-10): カテゴリ「コーヒー豆」(cbid=1470303)の全9商品を1ページで取得。
うち「お得なコーヒー豆1kg袋」(6,600円)は大容量の選択式のため代表にせず除外し、残り8商品
(ブレンド3種100g、シングル60〜100g、デカフェ100g)を対象とする。ギフトセット、
カップオンコーヒー、スイーツ、グッズのカテゴリは取得しない。
重量は商品名の「60g/80g/100g」表記から取得(全角「ｇ」も可)。価格は税込のsales_price_including_tax。
在庫は商品ページの「カートに入れる」ボタンの有無で判定(stock_numは多くがnull)。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "ANCHOR COFFEE",
    "url": "http://anchor2fullsail.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "宮城県気仙沼市館山1丁目6番31号",
    "prefecture": "宮城県",
    "robots_txt_status": "未確認(shop-pro.jp標準構成)",
}

BASE_URL = "http://anchor2fullsail.shop-pro.jp/"
LIST_URL = BASE_URL + "?mode=cate&cbid=1470303&csid=0&sort=n"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 1

EXCLUDE_KEYWORDS = ["1kg", "セット", "ドリップバッグ", "カップオン"]
COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return BeautifulSoup(resp.text, "html.parser"), resp.text


def scrape_all_products() -> list[dict]:
    soup, _ = fetch_page(LIST_URL)
    items = []
    for li in soup.select("li.productlist_list"):
        a = li.select_one('a[href*="pid="]')
        name_el = li.select_one(".item_name")
        if not a or not name_el:
            continue
        pid = re.search(r"pid=(\d+)", a["href"]).group(1)
        items.append((pid, re.sub(r"\s+", " ", name_el.get_text(" ", strip=True))))

    records = []
    for pid, list_name in items:
        if any(kw in list_name for kw in EXCLUDE_KEYWORDS):
            continue
        time.sleep(CRAWL_DELAY_SECONDS)
        url = f"{BASE_URL}?pid={pid}"
        psoup, text = fetch_page(url)
        m = COLORME_JSON_PATTERN.search(text)
        product = json.loads(m.group(1)).get("product") if m else None
        if not product:
            continue
        title = re.sub(r"\s+", " ", product.get("name") or list_name).strip()
        wm = WEIGHT_PATTERN.search(title)
        weight = int(wm.group(1)) if wm else None
        price = product.get("sales_price_including_tax")
        available = any("カートに入れる" in b.get_text() for b in psoup.find_all(["button", "a", "input"])) \
            or "カートに入れる" in text
        exp = psoup.select_one("div.product_explain") or psoup.select_one("div.product-order-exp")
        desc = re.sub(r"\s+", " ", exp.get_text(" ", strip=True))[:400] if exp else None

        parsed = parse_product(title)
        if "ブレンド" in title or "Blend" in title or "BLEND" in title:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            detected = detect_country_name(title)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, title)
            if not parsed["origin_country"] and desc:
                om = re.search(r"(?:生産地|原産国)\s*[:：]\s*(\S+)", desc)
                detected = detect_country_name(om.group(1)) if om else None
                if detected:
                    parsed["origin_country"] = detected
                    parsed["origin_source"] = "description"

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": parsed["roast_level"],
            "roast_hint": None,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": int(price) if price is not None else None,
            "weight_g": weight,
            "stock_status": "販売中" if available else "完売",
            "out_of_stock": not available,
            "product_url": url,
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_anchorcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_anchorcoffee.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], r["category"], r["origin_country"], r["price"], r["weight_g"], r["stock_status"], (r["flavor_notes"] or "")[:40])


if __name__ == "__main__":
    main()
