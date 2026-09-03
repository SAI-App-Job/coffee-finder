# -*- coding: utf-8 -*-
"""
scrape_aozora.py

青空豆店(aozoramame10.thebase.in、東京都杉並区永福)の商品情報を取得する。
BASE(thebase.in)製、chouette torréfacteur laboratoire(scrape_chouette.py)と
同じ「Relation」系の素のHTMLテーマ(JSON-LD無し)だが、chouetteと異なり
商品詳細ページの説明文冒頭に【生産国】【精製方法】【焙煎度合】という
ラベル付き構造化データを持つ(実データ確認済み、2026-09時点)。

robots.txt確認済み(2026-09時点): NAGI COFFEE・chouette等と同一の記述
(curl/python-requests/aiohttp等の一般的なHTTPクライアントは個別に
Disallow: /指定があるが、User-agent: *ルールでは/cart/・/web_cart/・
/shops/・/api/shops/・違反報告ページ以外はAllow: /)。本スクレイパーが
使用する商品詳細ページ(/items/)・カテゴリ一覧ページ(/categories/)は
いずれもDisallow対象に含まれない。

【対象カテゴリについて】
「ブレンドコーヒー」(1372924)・「シングルコーヒー」(1372965)・「デカフェ」
(1373042)の3カテゴリを対象とする。実データ確認済み(2026-09時点、
sitemap.xmlの全26件との突き合わせで検証済み): シングルコーヒー12件+
デカフェ1件+ブレンドコーヒー0件(現時点で在庫商品なし)=13件が実際の
特定の一豆を指す商品。残り13件は「青空豆便(頒布会)」(定期便、9件、
おまかせ焙煎含む)・「ギフトボックス」(2件)・「アイスコーヒーリキッド」
(2件、液体商品)で、いずれも上記3カテゴリの外にあり自然に除外される。
「フレンチロースト」等の焙煎度別カテゴリは上記3カテゴリの商品を焙煎度で
再分類した重複ビュー(かつ定期便商品も含んでしまう)であることを確認済み
のため、クロール対象にしない。

【商品詳細ページの説明文(【ラベル】値形式)について】
実データ確認済み(13件全件): div#item_detail内の<p>先頭に
【生産国】インドネシア共和国<br />【精製方法】スマトラ式<br />
【焙煎度合】フレンチロースト(深煎り)<br /><br />という3行の
「【ラベル】値」形式の行が並び、空行を挟んで自由記述のマーケティング文
(産地の説明・ギフト案内等)が続く。ラベル自体はシンプルな単一値
(WOODBERRY COFFEEのような複数行にわたる値や英語併記は無い)ため、
汎用的な1行パーサーで十分。

【焙煎度について】
実データ確認済み: 商品名自体に【焙煎度合】と同じ表記(例:「フレンチロースト
(深煎り)」)が含まれており、coffee_parser.parse_product()の商品名解析
だけでroast_levelが正しく判定できる。念のため説明文の【焙煎度合】欄も
参考情報として取得するが、判定には商品名解析の結果をそのまま使う。

【在庫状態について】
実データ確認済み: chouetteと同じ<div id="stockStatus" class="stockStatus
hasStock">構造(在庫があるとhasStockクラスが付与される)。売り切れの実例は
確認できなかったため、hasStockクラスが無い場合を構造的な品切れシグナルと
して扱う設計としている(chouetteと同じ方針)。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, normalize_processing_method, detect_stock_status, detect_country_name
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "青空豆店",
    "url": "https://aozoramame10.thebase.in/",
    "platform": "BASE",
    "address": "東京都杉並区永福4-10-4",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-09確認。NAGI COFFEE・chouette等と同一の記述。"
                          "/cart/・/web_cart/・/shops/・/api/shops/・違反報告ページ以外はUser-agent: *でAllow。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://aozoramame10.thebase.in"
CRAWL_DELAY_SECONDS = 2
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 理由はモジュールdocstring参照(特定の一豆を指す商品のみを持つ3カテゴリ)
LIST_CATEGORIES = {
    "1372924": "ブレンドコーヒー",
    "1372965": "シングルコーヒー",
    "1373042": "デカフェ",
}

DETAIL_LABEL_PATTERN = re.compile(r"^【(.+?)】\s*(.*)$")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def parse_weight(title: str) -> int | None:
    text = unicodedata.normalize("NFKC", title or "")
    m = WEIGHT_PATTERN.search(text)
    return int(m.group(1)) if m else None


def parse_detail_fields(soup: BeautifulSoup) -> dict:
    """div#item_detail内の【ラベル】値行を抽出する。理由はモジュールdocstring参照。"""
    detail_el = soup.select_one("div#item_detail")
    if not detail_el:
        return {}
    p_el = detail_el.select_one("p")
    if not p_el:
        return {}
    for br in p_el.find_all("br"):
        br.replace_with("\n")

    fields: dict[str, str] = {}
    for line in p_el.get_text().split("\n"):
        line = line.strip()
        if not line:
            continue
        m = DETAIL_LABEL_PATTERN.match(line)
        if m:
            fields[m.group(1).strip()] = m.group(2).strip()
    return fields


def build_record(soup: BeautifulSoup, product_url: str, fallback_title: str, price: int | None,
                  category_hint: str) -> dict:
    title_el = soup.select_one("header.itemTitle h1")
    title = title_el.get_text(strip=True) if title_el else fallback_title

    stock_el = soup.select_one("div.stockStatus")
    structural_out_of_stock = bool(stock_el) and "hasStock" not in (stock_el.get("class") or [])

    parsed = parse_product(title)

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

    fields = parse_detail_fields(soup)

    if fields.get("生産国") and not parsed["origin_country"]:
        country = detect_country_name(fields["生産国"])
        if country:
            parsed["origin_country"] = country
            parsed["origin_source"] = "product_description"

    if fields.get("精製方法"):
        parsed["processing_method"] = normalize_processing_method(fields["精製方法"])

    parsed = apply_category_hint_fallback(parsed, category_hint)
    stock_status = detect_stock_status(title, structural_out_of_stock)

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
        "weight_g": parse_weight(title),
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_category_list(cid: str) -> list[dict]:
    soup = fetch_page(f"{BASE_URL}/categories/{cid}")
    results = []
    seen_urls = set()
    for box in soup.select("div.item-box"):
        link_el = box.select_one('a[href*="/items/"]')
        title_el = box.select_one("div.item-title")
        if not link_el or not title_el:
            continue
        href = link_el.get("href", "")
        product_url = href if href.startswith("http") else f"{BASE_URL}{href}"
        if product_url in seen_urls:
            continue
        seen_urls.add(product_url)

        price = None
        price_el = box.select_one("span.item-price")
        if price_el:
            m = re.search(r"([\d,]+)", price_el.get_text())
            if m:
                price = int(m.group(1).replace(",", ""))

        results.append({"raw_name": title_el.get_text(strip=True), "product_url": product_url, "price": price})
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
        if is_unchanged(prev, raw_name=item["raw_name"], price=item["price"]):
            records.append(prev)
            continue

        try:
            soup = fetch_page(product_url)
            detail = build_record(soup, product_url, item["raw_name"], item["price"], item["category_hint"])
            if detail.get("is_flavored"):
                flavored_records.append(detail)
            else:
                records.append(detail)
            time.sleep(CRAWL_DELAY_SECONDS)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")

    return records, flavored_records


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        url = sys.argv[1]
        result = build_record(fetch_page(url), url, "", None, "")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        records, flavored_records = scrape_all_products()
        output = {
            "shop": SHOP_INFO,
            "products": records,
            "flavored_products_excluded": flavored_records,
        }
        with open("data_aozora.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_aozora.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
