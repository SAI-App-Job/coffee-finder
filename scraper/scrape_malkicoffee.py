# -*- coding: utf-8 -*-
"""
scrape_malkicoffee.py

自家焙煎珈琲丸喜(shop.malki-coffee.com、愛知県半田市春日町2-18、自家焙煎豆
のオンライン販売)の商品情報を取得する。EC-CUBE(煎豆屋と同じプラット
フォーム)。

【SSL証明書について】
候補リストの下調べでshop.malki-coffee.comへの接続時にSSL証明書不一致が
指摘されていたが、実データ確認の結果、証明書は"www.shop.malki-coffee.com"
(サブドメインwwwを含む形)に対して発行されており、こちらのホスト名で
アクセスすれば証明書検証は正常に通ることを確認済み(www無しの
shop.malki-coffee.comは証明書のCNが一致せず失敗する)。本スクレイパーは
証明書検証を無効化せず、正しいホスト名(www.shop.malki-coffee.com)を使う。

robots.txt確認済み(2026-09時点): User-agent: *に対し*.csv$のみDisallow
(煎豆屋と同一の記述)。本スクレイパーが使う商品ページは制限対象外。

【商品一覧の取得方法について】
実データ確認済み: カテゴリ「コーヒー豆」(category_id=1)に焙煎豆単品の
全23件がまとまっている(「ストレート」category_id=4・「ブレンド」
category_id=3のサブカテゴリを合算した集合と、水出し珈琲パック等の
その他コーヒーで唯一焙煎豆に該当する商品も含む)。ギフト(category_id=2)・
ドリップパック(category_id=7)・コーヒー器具系(category_id=9〜14)・
珈琲定期便(category_id=15、通常商品と重複するサブスク専用ページ)・
送料無料セット(category_id=16、詰め合わせ)は非対象のため巡回しない。

【非コーヒー豆商品の除外について】
実データ確認済み: category_id=1に含まれる23件のうち「COLD BREW
COFFEE(水出し珈琲パック)」(抽出用パック)・「アイスリキッドコーヒー
「冷珈」　1000ml　無糖」(瓶入り完成品リキッド)・「【送料無料】オリジナル
ブレンド・ドリップパック飲み比べセット(バラ・14個セット)」(詰め合わせ)
の3件が非対象。NON_BEAN_KEYWORDSで除外する。

【重量・価格・在庫の取得について】
実データ確認済み: 各商品ページに埋め込まれたEC-CUBE標準のJS変数
`eccube.classCategories`(classcategory_id1=容量コード→classcategory_id2=
挽き方コードの二段構造)に、組み合わせごとのprice02_inc_tax(税込価格)と
stock_find(在庫有無)が入っている。容量コード→実際のグラム数は同ページの
`<select id="classcategory_id1">`のoption文字列(例:「100g」)から取得する
(コード自体はグローバル共有だが、念のため商品ごとに都度取得する)。
挽き方は名前が「豆」のものを全粒(豆のまま)として優先し、在庫がある
組み合わせの中から最小重量を代表として採用する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "自家焙煎珈琲丸喜",
    "url": "https://www.shop.malki-coffee.com/",
    "platform": "EC-CUBE",
    "address": "愛知県半田市春日町2-18",
    "prefecture": "愛知県",
    "robots_txt_status": "実質許可(2026-09確認。User-agent: *に対し*.csv$のみ"
                          "Disallow。本スクレイパーが使う商品ページは制限対象外)",
}

BASE_URL = "https://www.shop.malki-coffee.com"
BEAN_CATEGORY_ID = 1
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["COLD BREW", "アイスリキッド", "ドリップパック"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
CLASS_CATEGORIES_MARKER = "eccube.classCategories = "


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_product_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/products/list?category_id={BEAN_CATEGORY_ID}")
    pids: set[str] = set()
    for a in soup.select('a[href*="/products/detail/"]'):
        m = re.search(r"/products/detail/(\d+)", a.get("href", ""))
        if m:
            pids.add(m.group(1))
    return [f"{BASE_URL}/products/detail/{pid}" for pid in sorted(pids, key=int)]


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


def extract_weight_code_map(soup: BeautifulSoup) -> dict:
    """classcategory_id1 (容量)セレクトのoption値→グラム数の対応表を作る。"""
    select = soup.find("select", id="classcategory_id1")
    if not select:
        return {}
    weight_map = {}
    for option in select.find_all("option"):
        value = option.get("value")
        m = WEIGHT_PATTERN.search(option.get_text())
        if value and value != "__unselected" and m:
            weight_map[value] = int(m.group(1))
    return weight_map


def pick_canonical_combo(class_categories: dict, weight_map: dict) -> tuple[dict | None, int | None]:
    candidates = []
    for weight_code, grind_options in class_categories.items():
        weight_g = weight_map.get(weight_code)
        if weight_g is None:
            continue
        for grind_code, detail in grind_options.items():
            if grind_code == "#" or not detail.get("product_class_id"):
                continue
            candidates.append((weight_g, detail))
    if not candidates:
        return None, None

    in_stock = [(w, d) for w, d in candidates if d.get("stock_find")]
    pool = in_stock or candidates
    whole_bean = [(w, d) for w, d in pool if d.get("name") == "豆"] or pool
    weight_g, detail = min(whole_bean, key=lambda item: item[0])
    return detail, weight_g


def build_record(soup: BeautifulSoup, html_text: str, product_url: str) -> dict | None:
    title_el = soup.select_one('meta[property="og:title"]')
    title = title_el["content"].strip() if title_el and title_el.get("content") else ""
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)
    class_categories = extract_class_categories(html_text)
    weight_map = extract_weight_code_map(soup)
    detail, weight_g = pick_canonical_combo(class_categories, weight_map)

    price = None
    all_out_of_stock = True
    if detail is not None:
        price_text = (detail.get("price02_inc_tax") or "").replace(",", "")
        price = int(price_text) if price_text.isdigit() else None
        all_out_of_stock = not any(
            d.get("stock_find")
            for grind_options in class_categories.values()
            for code, d in grind_options.items()
            if code != "#"
        )

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
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_product_urls()

    records = []
    flavored_records = []
    for product_url in product_urls:
        try:
            resp = requests.get(product_url, headers=REQUEST_HEADERS, timeout=15)
            resp.raise_for_status()
            html_text = resp.text
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue

        soup = BeautifulSoup(html_text, "html.parser")
        detail = build_record(soup, html_text, product_url)
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
    with open("data_malkicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_malkicoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
