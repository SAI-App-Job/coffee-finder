# -*- coding: utf-8 -*-
"""
scrape_bonafors.py

ボナフォルス(Bonafors、bonafors.jp、〒830-0037 福岡県久留米市諏訪野町
2162 錦芳ビル102号、自家焙煎豆専門店)の商品情報を取得する。EC-CUBE。

【住所について】
特定商取引法ページ(https://bonafors.jp/help/tradelaw)で「〒830-0037
福岡県久留米市諏訪野町2162 錦芳ビル102号」を確認済み(2026-09時点)。

robots.txt確認済み(2026-09時点): 標準的なEC-CUBEのrobots.txtで
/products/(検索・カートAPI等の一部)以外は制限なし。本スクレイパーが
使う一覧・詳細ページ(/products/list, /products/detail/N)は制限対象外。

【対象カテゴリについて】
実データ確認済み(2026-09時点): 「標準焙煎度　中煎」(category_id=7)・
「標準焙煎度　中深煎」(category_id=8)・「標準焙煎度　深煎」
(category_id=9)の3カテゴリに全銘柄が焙煎度別に分類されており(1銘柄
1カテゴリのみに所属、重複なし)、他のカテゴリ(特選ギフトセット・
ドリップバッグ・2/3/4個セット・アイスコーヒー)は非対象。この3カテゴリを
巡回すれば全銘柄を過不足なく取得できる。

【重量・価格の取得について】
実データ確認済み: 商品詳細ページに埋め込まれたEC-CUBE標準のJS変数
`eccube.classCategories`のキー(例:"7"〜"11")自体には重量ラベルが
含まれておらず(nameフィールドが空文字列)、別途ページ内の
`<select id="classcategory_id1">`の`<option value="7">200g</option>`
のような静的HTMLに重量ラベルが対応表として存在する(Albert Coffee
Roasters等と異なるEC-CUBEカスタマイズ)。本スクレイパーはこの対応表を
先に構築してからclassCategoriesの価格・在庫と突き合わせる。

【焙煎度・挽き方について】
実データ確認済み: 挽き方(productoption2、極細/細/中細/中/粗/豆)は
価格に影響しない別売オプションのため無視する。焙煎度はカテゴリ名
(中煎/中深煎/深煎)由来だが商品名自体には含まれないため、roast_hintとして
保持しroast_levelはparse_product()の商品名解析(多くはNoneになる)に
任せる。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "ボナフォルス",
    "url": "https://bonafors.jp/",
    "platform": "EC-CUBE",
    "address": "福岡県久留米市諏訪野町2162 錦芳ビル102号",
    "prefecture": "福岡県",
    "robots_txt_status": "実質許可(2026-09確認。標準的なEC-CUBEのrobots.txtで、"
                          "本スクレイパーが使う一覧・詳細ページは制限対象外)",
}

BASE_URL = "https://bonafors.jp"
BEAN_CATEGORY_IDS = [7, 8, 9]  # 標準焙煎度 中煎/中深煎/深煎(理由はモジュールdocstring参照)
ROAST_HINTS = {7: "中煎", 8: "中深煎", 9: "深煎"}
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
CLASS_CATEGORIES_MARKER = "eccube.classCategories = "


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_product_urls_with_roast() -> list[dict]:
    results = []
    seen_pids: set[str] = set()
    for category_id in BEAN_CATEGORY_IDS:
        soup = fetch_page(f"{BASE_URL}/products/list?category_id={category_id}")
        for a in soup.select('a[href*="/products/detail/"]'):
            m = re.search(r"/products/detail/(\d+)", a.get("href", ""))
            if not m or m.group(1) in seen_pids:
                continue
            seen_pids.add(m.group(1))
            results.append({
                "product_url": f"{BASE_URL}/products/detail/{m.group(1)}",
                "roast_hint": ROAST_HINTS[category_id],
            })
    return results


def extract_class_categories(html_text: str) -> dict:
    idx = html_text.find(CLASS_CATEGORIES_MARKER)
    if idx == -1:
        return {}
    i = idx + len(CLASS_CATEGORIES_MARKER)
    while i < len(html_text) and html_text[i] != "{":
        i += 1
    start = i
    depth = 0
    for i in range(start, len(html_text)):
        if html_text[i] == "{":
            depth += 1
        elif html_text[i] == "}":
            depth -= 1
            if depth == 0:
                i += 1
                break
    try:
        return json.loads(html_text[start:i])
    except json.JSONDecodeError:
        return {}


def extract_weight_map(soup: BeautifulSoup) -> dict[str, int]:
    """理由はモジュールdocstring参照: 重量ラベルはclassCategories JSONではなく
    <select id="classcategory_id1">の<option>に対応表として存在する。"""
    select_el = soup.select_one("select#classcategory_id1")
    weight_map: dict[str, int] = {}
    if not select_el:
        return weight_map
    for option in select_el.select("option"):
        value = option.get("value")
        m = WEIGHT_PATTERN.search(option.get_text())
        if value and m:
            weight_map[value] = int(m.group(1))
    return weight_map


def pick_canonical_leaf(class_categories: dict, weight_map: dict[str, int]) -> tuple[dict | None, int | None]:
    candidates = []
    for key, inner in class_categories.items():
        if key == "__unselected" or not isinstance(inner, dict):
            continue
        detail = inner.get("#")
        if not isinstance(detail, dict) or not detail.get("product_class_id"):
            continue
        weight_g = weight_map.get(key)
        candidates.append((weight_g, detail))

    weighted = [(w, d) for w, d in candidates if w is not None]
    if not weighted:
        return (candidates[0][1], None) if candidates else (None, None)

    in_stock = [(w, d) for w, d in weighted if d.get("stock_find")]
    pool = in_stock or weighted
    weight_g, detail = min(pool, key=lambda item: item[0])
    return detail, weight_g


def build_record(item: dict) -> dict | None:
    resp = requests.get(item["product_url"], headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    html_text = resp.text
    soup = BeautifulSoup(html_text, "html.parser")

    title_el = soup.select_one("h2.ec-headingTitle")
    title = title_el.get_text(strip=True) if title_el else ""
    if not title:
        return None

    parsed = parse_product(title)
    class_categories = extract_class_categories(html_text)
    weight_map = extract_weight_map(soup)
    detail, weight_g = pick_canonical_leaf(class_categories, weight_map)

    price = None
    if detail is not None:
        price_text = (detail.get("price02_inc_tax") or "").replace(",", "")
        price = int(price_text) if price_text.isdigit() else None

    all_out_of_stock = bool(class_categories) and not any(
        (inner.get("#") or {}).get("stock_find")
        for key, inner in class_categories.items()
        if key != "__unselected" and isinstance(inner, dict)
    )

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": item["product_url"],
        }

    stock_status = detect_stock_status(title, all_out_of_stock)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": item["roast_hint"],
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["product_url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    items = fetch_product_urls_with_roast()

    records = []
    flavored_records = []
    for item in items:
        try:
            detail = build_record(item)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['product_url']} ({e})")
            continue
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


if __name__ == "__main__":
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_bonafors.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_bonafors.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
