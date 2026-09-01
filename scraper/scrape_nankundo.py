# -*- coding: utf-8 -*-
"""
scrape_nankundo.py

南薫堂珈琲(shop.nankundo-coffee.com、東京都世田谷区世田谷)の商品情報を取得する。
BASE製だが、FINETIME COFFEE ROASTERS(scrape_finetime.py)とはテーマが異なり
(c-item__title/c-item__price系のクラス名、JSON-LDは無し)、item-option
セレクター(g数選択)を持つ新しいBASEテーマを使っている。

robots.txt確認済み(2026-08時点): FINETIME COFFEE ROASTERSと同一の記述
(curl/python-requests等の一般的なHTTPクライアントは個別にDisallow: /指定が
あるが、User-agent: *ルールでは/cart/・/shops/・違反報告ページ以外はAllow: /)。
本スクレイパーは商品詳細ページ(/items/)とカテゴリ一覧ページ(/categories/)
のみを使用し、いずれもDisallow対象に含まれない。

【対象カテゴリについて】
サイトのカテゴリは「焙煎度別(フレンチ/フルシティ相当/シティ/ハイロースト)」
「形態別(ブレンド/ストレート/ドリップバッグ/数量限定/ピーベリー)」の2系統
あるが、実データ調査の結果、「ブレンドコーヒー」(cid=5911145)と
「ストレートコーヒー」(cid=5911147)の2カテゴリの和集合(16件)が、他の
全カテゴリ(焙煎度別4カテゴリの和集合、ドリップバッグ・数量限定・ピーベリー)
の商品と完全に一致することを確認した(diffで差分ゼロ)。そのためこの2
カテゴリのみをクロール対象とする。

【非コーヒー豆商品の除外について】
実データ確認済み: 上記16件のうち「水出しコーヒーパック（30g×3個入）」(液体の
水出しコーヒー、豆の形態ではない)と「5袋入/10袋入ドリップバッグコーヒー」
(ドリップバッグ、豆や粉での量り売りではない)の3件は、コーヒー豆そのものとは
異なる形態の商品。PHILOCOFFEA(コールドブリューバッグ)・FINETIME(ドリップ
バッグカテゴリ全体)と同じ考え方でタイトルキーワードにより除外する。

【商品名から産地・焙煎度を判定する】
実データ確認済み: 商品ページに構造化データ(JSON-LD等)や「原産国：」のような
ラベル付き説明欄は無く、商品説明はマーケティング文のみ(■シゲ店長のひとこと
等の非構造化テキスト)。産地・焙煎度は商品名自体から判定する他ない。商品名は
「[産地/銘柄] [焙煎度8段階表記]｜[粗い焙煎度]」という形式(例:「ブラジル
フレンチロースト｜深煎り」)で一貫しており、coffee_parser.parse_product()の
国名・ROAST_KEYWORDS判定がそのまま機能する(ブレンド銘柄名はいずれも
「ブレンド」を含むか、8段階表記の部分文字列と衝突する語を含まないことを
実データで確認済みなので、CafeCafaのような偶然の一致対策は不要)。「｜」区切り
より後ろの粗い表記(深煎り/中深煎り等)はroast_hintとして保持する。

【価格・重量について】
実データ確認済み: 商品ページ上部に表示される単一の価格(div.c-item__price--
single)と、g数選択セレクターの選択肢(例:「100g」(価格表示なし)「200g
¥960」)を比較したところ、表示価格は常に「200g」の選択肢と完全に一致する
(3商品でこの対応を確認済み。おそらく200gがデフォルト選択されているため)。
「100g」側は価格が選択後にJSで計算される仕組みのため、静的HTMLからは
取得できない。重量は、表示価格と一致する金額を持つg数オプションが見つかった
場合のみそのg数を採用し(架空の対応付けを避けるため)、見つからなければ
weight_gはnullのままにする。

【在庫状態について】
実データ確認済み: 売り切れ商品にはp.c-item__priceStatusという要素が
「SOLD OUT」というテキストで存在する(在庫がある商品には要素自体が存在しない)。
これを構造的な品切れシグナルとして使う。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "南薫堂珈琲",
    "url": "https://shop.nankundo-coffee.com/",
    "platform": "BASE",
    "address": "東京都世田谷区世田谷2-6-4　グリーンアネックス102",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-08確認。FINETIME COFFEE ROASTERSと同一の記述。"
                          "/cart/・/shops/・違反報告ページ以外はUser-agent: *でAllow。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://shop.nankundo-coffee.com"
CRAWL_DELAY_SECONDS = 2
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 理由はモジュールdocstring参照(この2カテゴリの和集合が全商品をカバー)
LIST_CATEGORIES = ["5911145", "5911147"]  # ブレンドコーヒー、ストレートコーヒー

# 理由はモジュールdocstring参照(コーヒー豆そのものと形態が異なる商品)
NON_BEAN_KEYWORDS = ["水出しコーヒーパック", "ドリップバッグコーヒー"]

WEIGHT_OPTION_PATTERN = re.compile(r"^(\d+)\s*[gｇ]\s*(?:¥\s*([\d,]+))?")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def split_title_roast_hint(raw_title: str) -> tuple[str, str | None]:
    if "｜" in raw_title:
        main, hint = raw_title.split("｜", 1)
        return main.strip(), hint.strip()
    return raw_title.strip(), None


def extract_price_and_weight(soup: BeautifulSoup) -> tuple[int | None, int | None]:
    """理由はモジュールdocstring参照(単一表示価格と一致するg数オプションの
    重量だけを採用し、確証の無い対応付けはしない)。"""
    price_el = soup.select_one("div.c-item__price--single p")
    price = None
    if price_el:
        m = re.search(r"([\d,]+)", price_el.get_text())
        if m:
            price = int(m.group(1).replace(",", ""))

    weight_g = None
    if price is not None:
        for option in soup.select("select.itemOption__select option[value]"):
            m = WEIGHT_OPTION_PATTERN.match(option.get_text(strip=True))
            if m and m.group(2) and int(m.group(2).replace(",", "")) == price:
                weight_g = int(m.group(1))
                break

    return price, weight_g


def build_record(product_url: str, raw_title: str, price: int | None, weight_g: int | None,
                  structural_out_of_stock: bool) -> dict:
    main_title, roast_hint = split_title_roast_hint(raw_title)
    parsed = parse_product(main_title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": raw_title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": product_url,
        }

    parsed = apply_category_hint_fallback(parsed, None)
    stock_status = detect_stock_status(raw_title, structural_out_of_stock)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": raw_title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": roast_hint,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def parse_product_detail(url: str) -> dict:
    soup = fetch_page(url)
    title_el = soup.select_one("h1.p-item__title")
    if not title_el:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": "",
            "non_bean": True,
            "product_url": url,
        }

    price, weight_g = extract_price_and_weight(soup)
    status_el = soup.select_one("p.c-item__priceStatus")
    structural_out_of_stock = bool(status_el and "SOLD OUT" in status_el.get_text())

    return build_record(url, title_el.get_text(strip=True), price, weight_g, structural_out_of_stock)


def scrape_category_list_page(cid: str) -> list[dict]:
    soup = fetch_page(f"{BASE_URL}/categories/{cid}")
    results = []
    for link_el in soup.select('a.c-item[href*="/items/"]'):
        title_el = link_el.select_one(".c-item__title")
        if not title_el:
            continue
        raw_name = title_el.get_text(strip=True)
        if any(kw in raw_name for kw in NON_BEAN_KEYWORDS):
            continue
        href = link_el.get("href", "")
        product_url = href if href.startswith("http") else f"{BASE_URL}{href}"
        results.append({"raw_name": raw_name, "product_url": product_url})
    return results


def scrape_all_products() -> tuple[list[dict], list[dict], list[dict]]:
    items_by_url: dict[str, dict] = {}
    for cid in LIST_CATEGORIES:
        for item in scrape_category_list_page(cid):
            items_by_url.setdefault(item["product_url"], item)
        time.sleep(CRAWL_DELAY_SECONDS)

    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    non_bean_records = []
    for product_url, item in items_by_url.items():
        prev = previous.get(product_url)
        if is_unchanged(prev, raw_name=item["raw_name"]):
            records.append(prev)
            continue

        try:
            detail = parse_product_detail(product_url)
            if detail.get("non_bean"):
                non_bean_records.append(detail)
            elif detail.get("is_flavored"):
                flavored_records.append(detail)
            else:
                records.append(detail)
            time.sleep(CRAWL_DELAY_SECONDS)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")

    return records, flavored_records, non_bean_records


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        result = parse_product_detail(sys.argv[1])
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        records, flavored_records, non_bean_records = scrape_all_products()
        output = {
            "shop": SHOP_INFO,
            "products": records,
            "flavored_products_excluded": flavored_records,
            "non_bean_products_excluded": non_bean_records,
        }
        with open("data_nankundo.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_nankundo.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件、"
              f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
