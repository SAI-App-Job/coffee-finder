# -*- coding: utf-8 -*-
"""
scrape_coffeeandtea.py

珈琲＆紅茶館(coffeeandtea.shop-pro.jp、奈良県奈良市西木辻町126の実店舗
〈焙煎工房珈琲&紅茶館〉、オンラインショップの特定商取引法表記上の運営
拠点は京都府京田辺市東西神谷60-21〈有限会社珈琲＆紅茶館〉。実店舗は
奈良市と京田辺市の2拠点体制で、いずれも同一ブランド。自家焙煎豆の
オンライン販売)の商品情報を取得する。カラーミーショップ(shop-pro.jp)。

注記: この店舗は「フラッシュロースト」と呼ぶ、注文後に短時間で焙煎する
方式を採っており、一般的な「あらかじめ焙煎済みの豆を在庫する」方式とは
異なるが、自家焙煎(自社で焙煎工程を行う)であることに変わりはないため
対象に含める。

robots.txt確認済み(2026-09時点): User-agent: *に対し/secure/・/cart/のみ
Disallow。AhrefsBot等一部SEO系ボットを個別にDisallow: /、それ以外は
制限なし。

【商品一覧の取得方法について】
実データ確認済み: sitemap.xmlには紅茶(カテゴリcbid=1774422/1774424/
1774425/1774426、計154件)を含む全520件のpid URLが列挙されており、
商品名だけでは紅茶と判別しづらい項目もある(例:紅茶カテゴリの「ケニア
30g」)。このため全件を巡回する方式ではなく、店舗自身が付与した
コーヒー豆カテゴリ5つ(北中米/南米/ブレンド/アフリカ/アジア・オセアニア、
CATEGORY_LABELS参照)のカテゴリ一覧ページのみを対象にホワイトリスト
方式で巡回する。各カテゴリ一覧ページ(div.item_list、1ページ12件)には
商品名・価格が直接掲載されているため、商品詳細ページへの個別アクセスは
不要(全449件×個別リクエストを避けられる)。

なお、過去の調査(2026-09初回パス)ではカテゴリ北中米〜アフリカの4カテゴリ
のみを2ページ目までしか巡回しておらず(全114/71/78/90件のところ数十件
しか取得できておらず)、かつカテゴリページ下部の「おすすめ商品」サイド
バー(li要素、item_list divとは無関係)のリンクを誤って商品一覧に混入
させていた。本実装はdiv.item_listのみを対象とし、各カテゴリを
pagenavi_topの表示件数がなくなるまで(空ページが返るまで)巡回すること
でこの不具合を修正している。

【重量違いの重複について】
実データ確認済み: 全77銘柄が「生豆時100g」等、生豆換算の重量表記で
100g/200g/300g/400g/500g/1000gの最大6サイズを持つ(一部は100g/200gの
みなど銘柄により異なる)。商品名から「生豆時」表記と重量を除いた基準名で
グルーピングし、最小重量を代表として採用する。

【全角/半角の表記ゆれによる誤重複について】
実データ確認済み: 「モカコチャレナチュラルG-1」の100g商品のみ末尾の
数字が全角「１」で登録されており(他の200g/300g/400g/500g/1000gは
半角「1」)、単純な文字列一致では別銘柄として扱われてしまう(実際は
同一銘柄の入力ミス)。基準名の比較にunicodedata.normalize("NFKC", ...)
を適用し、全角/半角の違いを吸収したうえでグルーピングする。

【アイスコーヒー用ブレンドについて】
実データ確認済み: 「当店自慢のアイスコーヒー」はブレンドカテゴリに
分類されており、他のストレート/ブレンド豆と同じく100g〜1000gの生豆換算
重量表記・価格体系(864円〜4752円)を持つ(液体のボトル販売ではなく、
アイスコーヒー向けに焙煎された豆売り商品)。対象に含める。

【非コーヒー豆商品について】
実データ確認済み: 対象とした5カテゴリ内には非コーヒー豆商品(ドリップ
バッグ・ギフトセット等)は存在しなかった。紅茶関連4カテゴリは巡回対象に
含めていないため、除外用のNON_BEAN_KEYWORDSは不要。
"""

import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "珈琲＆紅茶館",
    "url": "http://coffeetea.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "奈良県奈良市西木辻町126",
    "prefecture": "奈良県",
    "robots_txt_status": "実質許可(2026-09確認。/secure/・/cart/のみDisallow。"
                          "AhrefsBot等一部SEO系ボットのみDisallow: /で本スクレイパーは"
                          "該当しない)",
}

BASE_URL = "http://coffeeandtea.shop-pro.jp/"
CRAWL_DELAY_SECONDS = 0.5
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 理由はモジュールdocstring参照。紅茶系4カテゴリ(紅茶/フレーバーティー/
# ハーブティー/紅茶ティーパック)は対象外
CATEGORY_LABELS = {
    1774417: "北中米",
    1774418: "南米",
    1774419: "ブレンド",
    1774420: "アフリカ",
    1774421: "アジア・オセアニア",
}

WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
PRICE_PATTERN = re.compile(r"[\d,]+")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-jp"  # 実データ確認済み(Content-Type: text/html; charset=EUC-JP)
    return BeautifulSoup(resp.text, "html.parser")


def scrape_category_page(cbid: int, page: int) -> list[dict]:
    url = f"{BASE_URL}?mode=cate&cbid={cbid}&csid=0"
    if page > 1:
        url += f"&page={page}"
    soup = fetch_page(url)

    results = []
    for item_div in soup.select("div.item_list"):
        link_el = item_div.select_one("span.name a")
        price_el = item_div.select_one("span.price_all")
        if not link_el:
            continue
        href = link_el.get("href", "")
        m = re.search(r"pid=(\d+)", href)
        if not m:
            continue
        pid = m.group(1)
        title = link_el.get_text(strip=True)
        price = None
        if price_el:
            price_m = PRICE_PATTERN.search(price_el.get_text())
            if price_m:
                price = int(price_m.group(0).replace(",", ""))
        results.append({
            "pid": pid,
            "title": title,
            "price": price,
            "url": f"{BASE_URL}?pid={pid}",
        })
    return results


def fetch_all_category_items() -> dict[str, dict]:
    items_by_pid: dict[str, dict] = {}
    for cbid in CATEGORY_LABELS:
        page = 1
        while True:
            page_items = scrape_category_page(cbid, page)
            if not page_items:
                break
            for item in page_items:
                items_by_pid.setdefault(item["pid"], item)
            page += 1
            time.sleep(CRAWL_DELAY_SECONDS)
    return items_by_pid


def normalize_base_name(title: str) -> str:
    """理由はモジュールdocstring参照(全角/半角表記ゆれの吸収)。"""
    base = title.replace("生豆時", "")
    base = WEIGHT_PATTERN.sub("", base).strip()
    return unicodedata.normalize("NFKC", base)


def pick_canonical_items(items: list[dict]) -> list[dict]:
    by_base_name: dict[str, dict] = {}
    for item in items:
        base_name = normalize_base_name(item["title"])
        weight_m = WEIGHT_PATTERN.search(item["title"])
        weight_key = int(weight_m.group(1)) if weight_m else float("inf")
        existing = by_base_name.get(base_name)
        existing_weight_m = WEIGHT_PATTERN.search(existing["title"]) if existing else None
        existing_weight = int(existing_weight_m.group(1)) if existing_weight_m else float("inf")
        if existing is None or weight_key < existing_weight:
            by_base_name[base_name] = item
    return list(by_base_name.values())


def build_record(item: dict) -> dict | None:
    title = item["title"].replace("生豆時", "").strip()
    title = re.sub(r"\s+", " ", title)
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

    stock_status = detect_stock_status(title)
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
    items_by_pid = fetch_all_category_items()
    canonical_items = pick_canonical_items(list(items_by_pid.values()))

    records = []
    flavored_records = []
    for item in canonical_items:
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
    with open("data_coffeeandtea.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeeandtea.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
