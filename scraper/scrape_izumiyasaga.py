# -*- coding: utf-8 -*-
"""
scrape_izumiyasaga.py

いづみや珈琲(いづみやコーヒーロースターズ株式会社、https://www.izumiyacoffee.com/、
佐賀県佐賀市兵庫南1丁目8-13、カラーミーショップ/shop-pro.jp)の商品情報を取得する。
(宮城県のいずみや珈琲豆店 = scrape_izumiyacoffee.py とは別の店。slugにsagaを付けて区別)

【住所】
特定商取引法ページ(/?mode=sk)の「〒849-0918 佐賀県佐賀市兵庫南1丁目8-13」。
店舗情報ページ(/?mode=f4)には本店1店のみ記載(久保泉の2号店はサイト上で確認できず)。

【対象商品について】
実データ確認済み(2026-10時点): カテゴリー「コーヒー豆」(?mode=cate&cbid=351300)の18件のうち、
水出しアイスコーヒーのパック2件(セット/パック商品)を除く16件(単一銘柄・ブレンド・デカフェ)。
全商品が「100gあたり」の価格で、重量・挽き目・焙煎度はバリエーション(ロースト度×挽き方)で選ぶ。
バリエーション違いは同一商品として1件にまとめ、100g・税込価格を採用する。
焙煎度は「いづみやに任せる」が既定の商品はNone、「中煎りのみ/深煎りのみの取り扱い」の商品は
その焙煎度を採用する。在庫表示は無く、全て販売中として扱う。

robots.txt確認済み(2026-10時点): 他のshop-pro.jp系店舗と同一の記述(/secure/と/cart/のみ制限)。
"""

import json
import re
import time

import requests

REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, detect_stock_status

SHOP_INFO = {
    "name": "いづみや珈琲",
    "url": "https://www.izumiyacoffee.com/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "佐賀県佐賀市兵庫南1丁目8-13",
    "prefecture": "佐賀県",
    "robots_txt_status": "許可(2026-10確認。User-agent: *は/secure/と/cart/のみ制限)",
}

BASE_URL = "https://www.izumiyacoffee.com/"
CATEGORY_URL = BASE_URL + "?mode=cate&cbid=351300&csid=0&page={page}"
CRAWL_DELAY_SECONDS = 3

NON_BEAN_KEYWORDS = ["水出し", "パック", "セット", "詰合せ", "ドリップカフェ", "リキッド", "ベース"]
COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*\});", re.DOTALL)
ROAST_ONLY_PATTERN = re.compile(r"(浅煎り|中浅煎り|中煎り|中深煎り|深煎り)のみ")
# 商品名からは産地が判別できない銘柄の補完(商品説明で確認済み)
ORIGIN_OVERRIDES = {
    "キリマンジャロ": "タンザニア",  # 説明文「タンザニアAAが本名」
    "モカ　イルガチャフィー": "エチオピア",
    "モカ　シダモ": "エチオピア",
    "モカ　マタリ": "イエメン",  # 説明文「イエメン原産」
}


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return BeautifulSoup(resp.text, "html.parser")


def list_items() -> list[dict]:
    items, seen = [], set()
    for page in range(1, 10):
        soup = fetch_page(CATEGORY_URL.format(page=page))
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


def feature_text(soup: BeautifulSoup) -> str | None:
    text = soup.get_text("\n", strip=True)
    i = text.find("商品の特徴")
    j = text.find("ツイート", i)
    if i < 0 or j < 0:
        return None
    body = re.sub(r"\s+", " ", text[i + len("商品の特徴"):j].replace("\n", " ")).strip()
    return body or None


def scrape_all_products() -> list[dict]:
    records = []
    for it in list_items():
        name = it["raw_name"]
        if any(kw in name for kw in NON_BEAN_KEYWORDS):
            continue
        url = f"{BASE_URL}?pid={it['pid']}"
        soup = fetch_page(url)
        time.sleep(CRAWL_DELAY_SECONDS)
        p = colorme_product(soup)
        if not p:
            continue
        variants = p.get("variants") or []
        # 100g・税込の最安バリエーション(ロースト度・挽き目違いは同一商品)
        price = min(v["option_price_including_tax"] for v in variants) if variants else p["sales_price_including_tax"]

        roast = None
        if variants:
            m = ROAST_ONLY_PATTERN.search(variants[0].get("option1_value") or "")
            if m:
                roast = m.group(1)

        parsed = parse_product(name)
        if "ブレンド" in name:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            if name in ORIGIN_OVERRIDES:
                parsed["origin_country"] = ORIGIN_OVERRIDES[name]
                parsed["origin_source"] = "description"
            else:
                detected = detect_country_name(name)
                if detected and not parsed["origin_country"]:
                    parsed["origin_country"] = detected
                    parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, name)
        if "アイスコーヒー" in name and "ブレンド" not in name:
            parsed["category"] = "ブレンド"  # オリジナルアイスコーヒー = 深煎りの自家ブレンド(産地記載なし)
            parsed["origin_country"] = None
            parsed["origin_source"] = None

        stock_status = detect_stock_status(name)
        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": roast or parsed["roast_level"],
            "roast_hint": None,
            "flavor_notes": feature_text(soup),
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": price,
            "weight_g": 100,
            "stock_status": stock_status,
            "out_of_stock": stock_status != "販売中",
            "product_url": url,
        })
    return records


if __name__ == "__main__":
    records = scrape_all_products()
    with open("data_izumiyasaga.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_izumiyasaga.json に出力しました")
    for r in records:
        print(r["raw_name"], r["category"], r["origin_country"], r["roast_level"], r["price"], r["weight_g"], r["stock_status"])
