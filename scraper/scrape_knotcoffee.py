# -*- coding: utf-8 -*-
"""
scrape_knotcoffee.py

Knot COFFEE(ノットコーヒー、knot-coffee.shop-pro.jp、公式 knot-coffee.com、
茨城県守谷市百合ケ丘2-2767-1 ポルン101)の商品情報を取得する。カラーミーショップ。

【文字コード】EUC-JP(実データ確認済み)。
robots.txt確認済み(2026-10時点): User-agent: * は /secure/ と /cart/ のみ制限。

【商品一覧】コーヒー豆カテゴリ(cbid=2748797)の一覧1ページ(19件)から ?pid=N を集める。
同一銘柄が 100g/200g/250g/500g/1kg で別商品登録されているため、
重量・送料注記を除いた基準名でグルーピングし、最小重量を代表にする
(実データ: SAI/YUI/デカフェ/ボリビア/山百合は250g、ルワンダ/ケニア/エチオピアは100g)。
ドリップバッグ・アイスコーヒーバッグ・ギフトセット等は別カテゴリのため対象外。
【価格】product:price:amount(税込、内税表示)。商品名に《送料\200・クリックポスト対応》の注記がある。
【在庫】inventory_control が none のため構造化された在庫情報は無い。ページ内の
「SOLD OUT/売り切れ/品切れ」表記で判定する(取得時点では全件販売中)。
"""

import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "Knot COFFEE",
    "url": "https://knot-coffee.shop-pro.jp/",
    "platform": "カラーミーショップ",
    "address": "茨城県守谷市百合ケ丘2-2767-1 ポルン101",
    "prefecture": "茨城県",
    "robots_txt_status": "実質許可(2026-10確認。User-agent: * は /secure/ と /cart/ のみ制限)",
}

BASE_URL = "https://knot-coffee.shop-pro.jp"
BEAN_CATEGORY_URL = BASE_URL + "/?mode=cate&cbid=2748797&csid=0"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["ドリップバッグ", "ドリップバック", "ギフト", "セット", "タンブラー", "フィルター"]
WEIGHT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|g)", re.I)
SHIPPING_PATTERN = re.compile(r"《[^》]*》")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return BeautifulSoup(resp.text, "html.parser")


def fetch_product_urls() -> list[str]:
    soup = fetch_page(BEAN_CATEGORY_URL)
    urls = []
    for it in soup.select("div.item_box"):
        a = it.select_one(".item_name a[href]")
        if not a:
            continue
        m = re.search(r"pid=(\d+)", a["href"])
        if m:
            u = f"{BASE_URL}/?pid={m.group(1)}"
            if u not in urls:
                urls.append(u)
    return urls


def to_grams(title: str) -> int | None:
    m = WEIGHT_PATTERN.search(title)
    if not m:
        return None
    v = float(m.group(1))
    return int(round(v * 1000)) if m.group(2).lower() == "kg" else int(v)


def base_name(title: str) -> str:
    n = WEIGHT_PATTERN.sub("", title)
    return re.sub(r"\s+", " ", n).strip()


def extract_fields(soup: BeautifulSoup) -> dict | None:
    og = soup.select_one('meta[property="og:title"]')
    if not og or not og.get("content"):
        return None
    raw = og["content"].split(" - ")[0]
    title = unicodedata.normalize("NFKC", SHIPPING_PATTERN.sub("", raw))
    title = re.sub(r"\s+", " ", title.replace("\\200", "")).strip()
    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None
    text = soup.get_text("\n", strip=True)
    roast = None
    flavor = None
    origin_line = None
    for line in text.split("\n"):
        line = unicodedata.normalize("NFKC", line).strip()
        m = re.match(r"焙煎度[\s:]+(.+)", line)
        if m and not roast:
            roast = m.group(1).strip()
        m = re.match(r"フレーバー[\s:]+(.+)", line)
        if m and not flavor:
            flavor = m.group(1).strip()
        m = re.match(r"産地[\s:]+(.+)", line)
        if m and not origin_line:
            origin_line = m.group(1).strip()
    if not roast:
        rm = re.search(r"(中浅煎り|中深煎り|浅煎り|深煎り|中煎り)", title)
        roast = rm.group(1) if rm else None
    sold_out = bool(re.search(r"SOLD\s*OUT|売り切れ|品切れ|在庫切れ", text))
    return {"title": title, "price": price, "weight": to_grams(title),
            "roast": roast, "flavor": flavor, "sold_out": sold_out}


def pick_canonical_items(items: list[dict]) -> list[dict]:
    by_name: dict[str, dict] = {}
    for item in items:
        k = base_name(item["title"])
        ex = by_name.get(k)
        w = item["weight"] or float("inf")
        if ex is None or w < (ex["weight"] or float("inf")):
            by_name[k] = item
    return list(by_name.values())


def build_record(item: dict) -> dict:
    raw_name = item["title"]
    parsed = parse_product(raw_name + (" " + item["roast"] if item["roast"] and item["roast"] not in raw_name else ""))
    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"], "raw_name": raw_name,
            "category": "フレーバー", "is_flavored": True,
            "flavor_name": parsed["flavor_name"], "price": item["price"],
            "product_url": item["url"],
        }
    stock_status = "品切れ" if item["sold_out"] else detect_stock_status(raw_name)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": raw_name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": item["roast"],
        "flavor_notes": item["flavor"],
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": item["weight"],
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    all_items = []
    for url in fetch_product_urls():
        try:
            f = extract_fields(fetch_page(url))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {url} ({e})")
            continue
        if not f or any(kw in f["title"] for kw in NON_BEAN_KEYWORDS):
            continue
        f["url"] = url
        all_items.append(f)

    previous = load_previous_products(SHOP_INFO["name"])
    records, flavored = [], []
    for item in pick_canonical_items(all_items):
        prev = previous.get(item["url"])
        if is_unchanged(prev, raw_name=item["title"]):
            records.append(prev)
            continue
        d = build_record(item)
        (flavored if d.get("is_flavored") else records).append(d)
    return records, flavored


if __name__ == "__main__":
    import json

    records, flavored = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records,
              "flavored_products_excluded": flavored}
    with open("data_knotcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_knotcoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored)}件は別枠に分離)")
