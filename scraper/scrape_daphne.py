# -*- coding: utf-8 -*-
"""
scrape_daphne.py

Daphne(ダフニ、東京都港区田町、コーヒー豆専門店の老舗)の商品情報を取得する。
実店舗サイト(www.daphne-coffee.jp)自体はWordPress情報サイトで、実際の
オンラインショップは別ドメイン(shop.daphne-coffee.jp、EC-CUBE)で行われて
いる「情報サイトと通販サイトが別ドメイン」パターン(たまじ珈琲等と同様)。
びーんず亭と同じEC-CUBEだが、テーマが異なる(ec-shelfGrid/ec-productRole系の
EC-CUBE標準テーマ)。

robots.txt確認済み(2026-09時点): shop.daphne-coffee.jp側はUser-agent: *に
対し/*.csv$のみDisallow(それ以外は無制限)。

【対象カテゴリについて】
実データ確認済み: 「ブレンドコーヒー」(7、3件)・「ストレートコーヒー
（中煎り）」(8、4件)・「ストレートコーヒー（深煎り）」(9、3件)・
「季節限定品（10月～5月末　冬季）」(10、2件)の4カテゴリ(計12件)が
コーヒー豆単品を指す。「新入荷」(2)はこの4カテゴリの完全な和集合
(重複ビュー)であることをproduct_id突き合わせで確認済みのため対象外とする。

【重量バリエーション(classCategories)について】
実データ確認済み: 1商品につき「100g/200g/300g/400g/500g」×「豆/粉」×
「自宅用/贈答用」の20通りの組み合わせがselect要素で選べる(価格は自宅用・
贈答用で同額)。商品詳細ページに埋め込まれたJS変数`eccube.classCategories`
に全組み合わせの価格・在庫情報が構造化JSONとして入っているため、これを
正規表現で抜き出してパースする。select#classcategory_id1のoption要素
(value=classcategory_id1・テキスト="100g 豆"等)から重量とタイプ(豆/粉)の
対応表を作り、「豆」タイプの中から最小重量のものを代表バリアントとして
採用する(「自宅用」side、classCategories側のnameが"自宅用"のエントリ)。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "Daphne",
    "url": "https://shop.daphne-coffee.jp/",
    "platform": "EC-CUBE",
    "address": "東京都港区芝5-10-11",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-09確認。User-agent: *に対し/*.csv$のみDisallow)",
}

BASE_URL = "https://shop.daphne-coffee.jp"
# 理由はモジュールdocstring参照
LIST_CATEGORIES = {
    "7": "ブレンドコーヒー",
    "8": "ストレートコーヒー(中煎り)",
    "9": "ストレートコーヒー(深煎り)",
    "10": "季節限定品",
}
CRAWL_DELAY_SECONDS = 1
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

CLASS_CATEGORIES_PATTERN = re.compile(r"eccube\.classCategories\s*=\s*(\{.*?\});", re.DOTALL)
OPTION_PATTERN = re.compile(r'<option value="(\d+)">(\d+)g\s*(豆|粉)</option>')


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def parse_weight_options(html: str) -> dict[str, tuple[int, str]]:
    """理由はモジュールdocstring参照(classcategory_id1 -> (重量g, 豆/粉))。"""
    options: dict[str, tuple[int, str]] = {}
    for cid1, weight, kind in OPTION_PATTERN.findall(html):
        options[cid1] = (int(weight), kind)
    return options


def pick_canonical_variant(html: str) -> tuple[int | None, int | None, bool]:
    """理由はモジュールdocstring参照。「豆」タイプの中から最小重量、
    「自宅用」側の価格・在庫を採用する。戻り値は(weight_g, price, in_stock)。"""
    weight_options = parse_weight_options(html)
    m = CLASS_CATEGORIES_PATTERN.search(html)
    if not m or not weight_options:
        return None, None, True

    try:
        class_categories = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None, None, True

    bean_options = sorted(
        ((cid1, weight) for cid1, (weight, kind) in weight_options.items() if kind == "豆"),
        key=lambda x: x[1],
    )
    for cid1, weight in bean_options:
        sub = class_categories.get(cid1)
        if not sub:
            continue
        for entry in sub.values():
            if entry.get("name") == "自宅用":
                price_raw = entry.get("price02_inc_tax")
                price = int(price_raw.replace(",", "")) if price_raw else None
                in_stock = bool(entry.get("stock_find"))
                return weight, price, in_stock
    return None, None, True


def build_record(product_url: str, title: str, description: str, html: str,
                  category_hint: str) -> dict:
    parsed = parse_product(title)
    weight_g, price, in_stock = pick_canonical_variant(html)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": product_url,
        }

    # 理由はモジュールdocstring参照。「アポロン（ビター）」等ブレンド
    # コーヒーカテゴリの商品名に「ブレンド」の語が含まれず、parse_product()
    # の商品名解析だけではブレンド判定できないことを実データ確認済み。
    # カテゴリが判明している場合はそちらを優先する。
    if category_hint == "ブレンドコーヒー":
        parsed["category"] = "ブレンド"
    parsed = apply_category_hint_fallback(parsed, category_hint)
    stock_status = detect_stock_status(title, not in_stock)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "category_hint": category_hint,
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def parse_product_detail(url: str, category_hint: str = "") -> dict:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    title_el = soup.select_one("title")
    title = (title_el.get_text(strip=True).split("/")[-1].strip()
              if title_el else "")
    if not title:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": "",
            "non_bean": True,
            "product_url": url,
        }

    desc_el = soup.select_one('meta[property="og:description"]')
    description = desc_el.get("content", "") if desc_el else ""

    return build_record(url, title, description, html, category_hint)


def scrape_category_list(cid: str) -> list[dict]:
    soup = fetch_page(f"{BASE_URL}/products/list?category_id={cid}")
    results = []
    for link_el in soup.select('a[href*="/products/detail/"]'):
        href = link_el.get("href", "")
        img_el = link_el.select_one("img[alt]")
        title = img_el.get("alt", "").strip() if img_el else ""
        if not title:
            continue
        results.append({"raw_name": title, "product_url": href})
    return results


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    items_by_url: dict[str, dict] = {}
    for cid, category_hint in LIST_CATEGORIES.items():
        for item in scrape_category_list(cid):
            items_by_url.setdefault(item["product_url"], {**item, "category_hint": category_hint})
        time.sleep(CRAWL_DELAY_SECONDS)

    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for product_url, item in items_by_url.items():
        prev = previous.get(product_url)
        if is_unchanged(prev, raw_name=item["raw_name"]):
            records.append(prev)
            continue

        try:
            detail = parse_product_detail(product_url, item["category_hint"])
            if detail.get("is_flavored"):
                flavored_records.append(detail)
            elif not detail.get("non_bean"):
                records.append(detail)
            time.sleep(CRAWL_DELAY_SECONDS)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")

    return records, flavored_records


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        result = parse_product_detail(sys.argv[1])
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        records, flavored_records = scrape_all_products()
        output = {
            "shop": SHOP_INFO,
            "products": records,
            "flavored_products_excluded": flavored_records,
        }
        with open("data_daphne.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_daphne.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
