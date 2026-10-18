# -*- coding: utf-8 -*-
"""
scrape_matsuocoffee.py

松尾コーヒー(松尾コーヒー株式会社、https://www.matsuo-coffee.co.jp/、長崎県長崎市木場町1302、
おちゃのこネット(Ocnk))の商品情報を取得する。

【住所について】
特定商取引法表示(/info)の販売主「松尾コーヒー株式会社 長崎県長崎市木場町１３０２番地」を採用する
(焙煎所=販売者住所と判断)。小売の「松尾珈琲店」は長崎市万才町1-5(外部掲載情報)だが、
公式サイト内に店舗案内ページは無く、特商法の住所を店の所在地とする。

【対象商品について】
実データ確認済み(2026-10時点): 商品カテゴリのうちコーヒー豆のカテゴリ4つを巡回する。
  - /product-list/3  長崎自家焙煎珈琲(14件)
  - /product-list/24 松尾 スペシャルティコーヒー(4件)
  - /product-list/8  長崎龍馬珈琲(1件)
  - /product-list/16 長崎出島阿蘭陀珈琲(2件中、豆は1件)
除外: ドリップバッグ(長崎出島阿蘭陀珈琲 ドリップバッグ4袋入り)。ギフト・ドリップバッグ・水出し・
器具・お年賀・チョコ(ビーンズしょくらあと)のカテゴリは最初から巡回しない。
全商品が200g単一規格(バリエーションは「豆or粉」「挽き方」のみで重量違いは無い)。
在庫は、カート追加ボタン(cart_add_btn)が無い場合を品切れとして扱う。
説明は詳細ページの div.detail_desc_box から取得する。

robots.txt確認済み(2026-10時点): GPTBot/Bytespider/TikTokSpider/meta-externalagentのみ
個別にDisallow: /、それ以外は制限なし。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, detect_stock_status

SHOP_INFO = {
    "name": "松尾コーヒー",
    "url": "https://www.matsuo-coffee.co.jp/",
    "platform": "おちゃのこネット(Ocnk)",
    "address": "長崎県長崎市木場町1302",
    "prefecture": "長崎県",
    "robots_txt_status": "実質許可(2026-10確認。GPTBot等AI系ボットのみ個別にDisallow: /、"
                          "それ以外は制限なし)",
}

BASE_URL = "https://www.matsuo-coffee.co.jp"
CATEGORY_IDS = [3, 24, 8, 16]
CRAWL_DELAY_SECONDS = 3
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

NON_BEAN_KEYWORDS = ["ドリップバッグ", "ギフト", "セット", "詰合せ", "詰め合わせ", "水出し"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇGＧ]")
SKU_PATTERN = re.compile(r"\s*[\[［][^\]］]*[\]］]")
# 商品名・説明の確認結果による分類/産地/焙煎度の明示(商品ID -> 上書き内容)。
# 商品名だけでは単一産地かブレンドか判別できないものは、説明文の記述(「ブレンドしました」
# 「原産国 ブラジル」等)で判断した。説明に産地・ブレンドの記述が無い商品は
# 店の商品名の位置付け(ブランド名のミックス)からブレンドとした(要確認として報告)。
OVERRIDES: dict[str, dict] = {
    "266": {"category": "ブレンド"},
    "267": {"category": "ブレンド"},
    "270": {"category": "ブレンド"},
    "261": {"category": "デカフェ", "origin": "コロンビア"},
    "210": {"category": "ストレート", "origin": "ブラジル"},
    "177": {"category": "ブレンド"},
    "271": {"category": "ブレンド", "roast": "フレンチロースト"},
    "21": {"category": "ブレンド"},
    "62": {"category": "ブレンド", "roast": "中深煎り"},
    "144": {"category": "ブレンド", "roast": "極深煎り"},
    "74": {"category": "ブレンド", "roast": "極深煎り"},
    "64": {"category": "ブレンド", "roast": "深煎り"},
    "76": {"category": "ブレンド", "roast": "極深煎り"},
    "30": {"roast": "中深煎り"},
    "60": {"origin": "エルサルバドル"},
    "198": {"category": "ブレンド"},
    "208": {"category": "ストレート", "origin": "インドネシア"},
}

_last_request = [0.0]


def fetch_page(url: str) -> BeautifulSoup:
    wait = CRAWL_DELAY_SECONDS - (time.time() - _last_request[0])
    if wait > 0:
        time.sleep(wait)
    delay = 30
    for _ in range(4):
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
        _last_request[0] = time.time()
        if resp.status_code == 429:
            print(f"[warn] 429: {delay}秒待機して再試行 {url}")
            time.sleep(delay)
            delay += 30
            continue
        resp.raise_for_status()
        resp.encoding = "utf-8"
        return BeautifulSoup(resp.text, "html.parser")
    raise requests.RequestException(f"429が解消しない: {url}")


def clean_name(raw: str) -> tuple[str, int | None]:
    """一覧のタイトルからSKU・重量表記を除去し、(商品名, 重量g)を返す。"""
    name = SKU_PATTERN.sub("", raw)
    name = re.sub(r"【新発売】", "", name)
    m = WEIGHT_PATTERN.search(name)
    weight = int(m.group(1)) if m else None
    if m:
        name = name[: m.start()] + " " + name[m.end():]
    name = re.sub(r"\s+", " ", name.replace("　", " ")).strip()
    return name, weight


def fetch_listing() -> list[dict]:
    items: dict[str, dict] = {}
    for cid in CATEGORY_IDS:
        soup = fetch_page(f"{BASE_URL}/product-list/{cid}")
        for h2 in soup.select("table.list_item_table h2"):
            a = h2.find("a")
            if not a:
                continue
            m = re.search(r"/product/(\d+)", a.get("href", ""))
            if not m or m.group(1) in items:
                continue
            title = a.get_text(" ", strip=True)
            price_el = h2.find_next(class_="pricech")
            price = None
            if price_el:
                pm = re.search(r"([\d,]+)", price_el.get_text())
                price = int(pm.group(1).replace(",", "")) if pm else None
            items[m.group(1)] = {"id": m.group(1), "title": title, "price": price, "category_id": cid}
    return list(items.values())


def build_record(item: dict) -> dict | None:
    title = item["title"]
    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None
    name, weight_g = clean_name(title)
    url = f"{BASE_URL}/product/{item['id']}"
    soup = fetch_page(url)

    desc_el = soup.select_one("div.detail_desc_box")
    desc = re.sub(r"\s+", " ", desc_el.get_text(" ", strip=True)).strip() if desc_el else None
    structural_out_of_stock = soup.select_one('input[name="cart_add_btn"]') is None
    stock_status = detect_stock_status(name, structural_out_of_stock)

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if parsed["category"] != "ブレンド":
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
    ov = OVERRIDES.get(item["id"], {})
    if "category" in ov:
        parsed["category"] = ov["category"]
        if ov["category"] == "ブレンド":
            parsed["origin_country"] = None
            parsed["origin_source"] = None
    if "origin" in ov:
        parsed["origin_country"] = ov["origin"]
        parsed["origin_source"] = "description"
    roast_level = ov.get("roast") or parsed["roast_level"]

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in fetch_listing():
        try:
            record = build_record(item)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['id']} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_matsuocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_matsuocoffee.json に出力しました")


if __name__ == "__main__":
    main()
