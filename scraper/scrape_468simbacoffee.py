# -*- coding: utf-8 -*-
"""
scrape_468simbacoffee.py

468 SiMBA Coffee(468シンバコーヒー。ストア https://468simbacoffee.shop-pro.jp/ 、公式 https://468simba.jp/、
佐賀県佐賀市多布施1丁目2-13、カラーミーショップ/shop-pro.jp)の商品情報を取得する。

【住所】
特定商取引法ページ(/?mode=sk)の「佐賀県佐賀市多布施１丁目２−１３」(〒840-0842)。

【対象商品について】
実データ確認済み(2026-10時点): 商品は「銘柄×200g」「銘柄×100g」が別商品として並び(全24件)、
9銘柄(ガテマラSHB、コロンビア スプレモ、ブラジル サントスNo2、ケニアAA、エチオピア モカ ナチュラル、
インド モンスーン、オリジナルブレンド、深煎りブレンド、Sweetブレンド)が対象。
各銘柄は最小重量の100g商品を代表とする。「お得な3種セット」6件は除外。
価格は店舗が表示する税込価格(option_price_including_tax、コーヒー豆は軽減税率8%)を採用する。
一覧は検索(?mode=srh&cid=&keyword=)の2ページ(12件/ページ)に収まる。
焙煎度は商品名の「＜中深煎り×…＞」から取得する。

robots.txt確認済み(2026-10時点): 他のshop-pro.jp系店舗と同一の記述(/secure/と/cart/のみ制限)。
"""

import json
import re
import time
from urllib.parse import quote

import requests

REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, detect_stock_status

SHOP_INFO = {
    "name": "468 SiMBA Coffee",
    "url": "https://468simbacoffee.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "佐賀県佐賀市多布施1丁目2-13",
    "prefecture": "佐賀県",
    "robots_txt_status": "許可(2026-10確認。User-agent: *は/secure/と/cart/のみ制限)",
}

BASE_URL = "https://468simbacoffee.shop-pro.jp/"
LIST_URL = BASE_URL + "?mode=srh&cid=&keyword=&page={page}"
CRAWL_DELAY_SECONDS = 3

NON_BEAN_KEYWORDS = ["セット"]
COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*\});", re.DOTALL)
WEIGHT_IN_NAME = re.compile(r"(\d+)\s*[gｇ]\s*$")
ROAST_IN_NAME = re.compile(r"＜\s*(浅煎り|中浅煎り|中煎り|中深煎り|深煎り)")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return BeautifulSoup(resp.text, "html.parser")


def list_items() -> list[dict]:
    items, seen = [], set()
    for page in range(1, 10):
        soup = fetch_page(LIST_URL.format(page=page))
        n = 0
        for a in soup.select('a[href*="pid="]'):
            text = a.get_text(strip=True)
            m = re.search(r"pid=(\d+)", a.get("href", ""))
            if not text or not m or m.group(1) in seen:
                continue
            seen.add(m.group(1))
            items.append({"raw_name": text, "pid": m.group(1)})
            n += 1
        time.sleep(CRAWL_DELAY_SECONDS)
        if n == 0:
            break
    return items


def colorme_product(soup: BeautifulSoup) -> dict | None:
    for script in soup.find_all("script"):
        m = COLORME_JSON_PATTERN.search(script.string or script.get_text() or "")
        if m:
            try:
                return json.loads(m.group(1)).get("product")
            except json.JSONDecodeError:
                return None
    return None


def flavor_notes(soup: BeautifulSoup) -> str | None:
    meta = soup.find("meta", property="og:description")
    text = re.sub(r"\s+", " ", meta.get("content", "")).strip() if meta else ""
    return text or None


def scrape_all_products() -> list[dict]:
    items = list_items()
    # 銘柄(重量部分を除いた名前)ごとに最小重量の商品を代表にする
    best = {}
    for it in items:
        name = it["raw_name"]
        if any(kw in name for kw in NON_BEAN_KEYWORDS):
            continue
        m = WEIGHT_IN_NAME.search(name)
        if not m:
            continue
        key = name[:m.start()].strip()
        w = int(m.group(1))
        if key not in best or w < best[key][0]:
            best[key] = (w, it)

    records = []
    for key, (w, it) in best.items():
        url = f"{BASE_URL}?pid={it['pid']}"
        soup = fetch_page(url)
        time.sleep(CRAWL_DELAY_SECONDS)
        p = colorme_product(soup)
        if not p:
            continue
        title = (p.get("name") or it["raw_name"]).strip()
        brand = re.sub(r"＜.*?＞", "", key).strip()
        variants = p.get("variants") or []
        price = variants[0]["option_price_including_tax"] if variants else p.get("sales_price_including_tax")
        rm = ROAST_IN_NAME.search(title)
        roast = rm.group(1) if rm else None

        parsed = parse_product(brand)
        if "ブレンド" in brand:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            detected = detect_country_name(brand)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, brand)
        stock_status = detect_stock_status(title)
        if "SOLD OUT" in soup.get_text().upper():
            stock_status = "一時的に品切れ"

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": brand,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": roast or parsed["roast_level"],
            "roast_hint": None,
            "flavor_notes": flavor_notes(soup),
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": price,
            "weight_g": w,
            "stock_status": stock_status,
            "out_of_stock": stock_status != "販売中",
            "product_url": url,
        })
    return records


if __name__ == "__main__":
    records = scrape_all_products()
    with open("data_468simbacoffee.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_468simbacoffee.json に出力しました")
    for r in records:
        print(r["raw_name"], r["category"], r["origin_country"], r["roast_level"], r["price"], r["weight_g"], r["stock_status"])
