# -*- coding: utf-8 -*-
"""
scrape_mantencoffee.py

満天珈琲(www.manten-coffee.jp、三重県四日市市北浜町1-5、株式会社アシスト
運営、直火式焙煎の自家焙煎豆のオンライン販売)の商品情報を取得する。

【調査時の重要な訂正】当初の候補リストでは「オンラインショップ無し、
手動入力(manual)対象」とされていたが、実際にはmanten-coffee.jp/shop.html
(www.へ301リダイレクト)経由でカテゴリ2「コーヒー豆」に24件の商品が
陳列された正規のオンラインショップが存在することを実データで確認した
(2026-09)。そのため手動入力ではなく通常のスクレイパーとして実装する。

【プラットフォームについて】
実データ確認済み: ブーランジェリー エ カフェ リエゾン(scrape_liaison.py)
と全く同じ、ベンダー名不明の中小事業者向けASPカート(CSSが
`ssl.xaas3.jp`から配信され、追跡スクリプトのドメイン識別子は
`s2611883`という固有店舗コード。店舗ごとにコードが違うのみでHTML構造・
CSSクラス名は共通のテンプレート)。商品名はul.spec > li.name > 、
価格はli.sales_price、在庫はli.stock1のテキストから取得する
(scrape_liaison.pyと同じ抽出ロジックを再利用)。

robots.txt確認済み(2026-09時点): `Disallow: /default/error/`
`Disallow: /preview/` のみ。本スクレイパーが使うcategory/itemページは
制限対象外。

【商品一覧の取得方法について】
実データ確認済み: category/2/(「コーヒー豆」カテゴリ)に24件。他の
カテゴリ(1:空、3:コーヒー飲料、4:コーヒー器具、5:その他、6:ギフト・
セット、7,8:空)は豆単品を含まないため対象外(ギフト・セットカテゴリの
中身も確認したが単品コーヒー豆とは別の詰め合わせ商品のみだった)。

【重量違いの重複について】
実データ確認済み: 主力8ブレンド(ティアラ・ヴァーゴ・マイルド・
モーニング・満天の星・リーブラ・ジェミニ・アリーズ)とブラジル
トミオフクダ・カロシトラジャが200g(【メール便対応】表記付き、
ジェミニのみ150g表記)/500gの2サイズで個別商品登録されている。
商品名末尾の重量および「【メール便対応】」の付記を除いた基準名で
グルーピングし、最小重量を代表として採用する(亀山珈琲焙煎所と同じ
方式)。エメラルドマウンテンは500gのみの単独登録(200g相当の登録が
見当たらない)。

【非コーヒー豆商品の除外について】
実データ確認済み(コーヒー豆カテゴリ内24件): 「【7種から2種選べる】...
飲み比べ...」「【5種から2種選べる】...」「【4種から2種選べる】...」の
3件は、購入者が選ぶ組み合わせ次第で中身が変わる詰め合わせのため
NON_BEAN_KEYWORDSの「選べる」で除外する。残り21件、重量違いの重複統合後は
10銘柄(ブレンド8種+ブラジルトミオフクダ+カロシトラジャ)
+エメラルドマウンテン(500gのみ)=11銘柄を対象とする。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "満天珈琲",
    "url": "https://www.manten-coffee.jp/",
    "platform": "不明(独自/中小事業者向けASPカート、xaas3.jp。リエゾンと同一プラットフォーム)",
    "address": "三重県四日市市北浜町1-5",
    "prefecture": "三重県",
    "robots_txt_status": "実質許可(2026-09確認。/default/error/と/preview/のみ"
                          "Disallow、本スクレイパーが使うcategory/itemページは"
                          "制限対象外)",
}

BASE_URL = "https://www.manten-coffee.jp"
BEAN_CATEGORY_PATH = "category/2/"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["選べる"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
MAIL_BIN_PATTERN = re.compile(r"[　\s]*【メール便対応】")
PRICE_PATTERN = re.compile(r"(\d[\d,]*)\s*円")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_product_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/{BEAN_CATEGORY_PATH}")
    urls: set[str] = set()
    for a in soup.select(f'a[href^="{BASE_URL}/item/"]'):
        href = a.get("href", "")
        if re.match(rf"^{re.escape(BASE_URL)}/item/[A-Za-z0-9-]+/$", href):
            urls.add(href)
    return sorted(urls)


def extract_title(soup: BeautifulSoup) -> str:
    # 商品名はul.spec > li.name > p.data > span.data にある(リエゾンと同一構造)。
    title_el = soup.select_one("li.name span.data")
    return title_el.get_text(strip=True) if title_el else ""


def extract_price(soup: BeautifulSoup) -> int | None:
    price_el = soup.select_one("li.sales_price span.data")
    if not price_el:
        return None
    m = PRICE_PATTERN.search(price_el.get_text())
    return int(m.group(1).replace(",", "")) if m else None


def fetch_all_items() -> list[dict]:
    items = []
    for product_url in fetch_product_urls():
        try:
            soup = fetch_page(product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        title = extract_title(soup)
        if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
            continue
        items.append({"title": title, "price": extract_price(soup), "url": product_url, "soup": soup})
    return items


def pick_canonical_items(items: list[dict]) -> list[dict]:
    by_base_name: dict[str, dict] = {}
    for item in items:
        base_name = MAIL_BIN_PATTERN.sub("", item["title"])
        base_name = WEIGHT_PATTERN.sub("", base_name).strip()
        weight_m = WEIGHT_PATTERN.search(item["title"])
        weight_key = int(weight_m.group(1)) if weight_m else float("inf")
        existing = by_base_name.get(base_name)
        existing_weight_m = WEIGHT_PATTERN.search(existing["title"]) if existing else None
        existing_weight = int(existing_weight_m.group(1)) if existing_weight_m else float("inf")
        if existing is None or weight_key < existing_weight:
            by_base_name[base_name] = item
    return list(by_base_name.values())


def build_record(item: dict) -> dict | None:
    title = item["title"]
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": item["price"],
            "product_url": item["url"],
        }

    stock_el = item["soup"].select_one("li.stock1 p.data")
    stock_text = stock_el.get_text(strip=True) if stock_el else ""
    structural_out_of_stock = bool(stock_text) and "在庫あり" not in stock_text
    stock_status = detect_stock_status(title, structural_out_of_stock)
    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None

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
        "price": item["price"],
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    all_items = fetch_all_items()
    canonical_items = pick_canonical_items(all_items)
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for item in canonical_items:
        prev = previous.get(item["url"])
        if is_unchanged(prev, raw_name=item["title"]):
            records.append(prev)
            continue

        detail = build_record(item)
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


if __name__ == "__main__":
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_mantencoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mantencoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
