# -*- coding: utf-8 -*-
"""
scrape_arabicacoffee.py

アラビカコーヒー(arabicacoffee.co.jp、静岡県沼津市を拠点に沼津・富士・
御殿場・三島の4直営店+本社卸部/焙煎工場を展開、焙煎は本社工場で集中して
行っているため対象、実データ確認済み)の商品情報を取得する。
WordPress + Welcart(ウェルカート、フォレスト自家焙煎コーヒー豆店
(scrape_forest.py)と同じプラットフォーム)。

robots.txt確認済み(2026-09時点): /wp-admin/等の管理系パスのみDisallow、
それ以外は制限なし。

【生豆(未焙煎)商品の除外について】
実データ確認済み: このショップは「希少な生豆、コーヒーマイスターが
焙煎した煎り豆」の両方を販売しており(トップページの説明文より)、
一覧ページの<article>タグに付与されたWordPressカテゴリclass
(category-green_coffee_beans)で生豆商品(商品名にも「（生豆）」
サフィックスが付く)を判別できる。本アプリは焙煎済み豆を対象とする
ため、生豆(未焙煎)商品は除外する。

【ドリップバッグ/ギフト詰め合わせの除外について】
実データ確認済み: 同じ商品名(例:「アラビカロイヤルブレンド」)が
実際の焙煎豆版(category-blend、200g/500g/1kg展開)と、ドリップバッグ
版(category-dripon、12g×5パック/12g×10パック展開)の両方で別記事
として存在するため、商品名だけでは区別できない。一覧ページの
category-driponクラスで判別して除外する。

【重量バリエーションについて】
実データ確認済み: 商品詳細ページのdiv.net-weight内に<dl><dt>重量</dt>
<dd><span>価格</span></dd></dl>が重量の小さい順に複数並ぶ(200g→500g→
1kgなど。業務用ブレンドのみ500g→1kg→2kg)。dl.item-sku(挽き方等を選ぶ
フォーム側)のデフォルト選択(option value="0")も常に最小重量と対応して
いるため、net-weight内の最初のdl(価格を含むもの)を代表として採用する。

【おすすめの焙煎度について】
実データ確認済み: div.roast div.BaisenCommentsに「シティーロースト」等の
おすすめ焙煎度が記載されている(商品ごとに固定、または複数併記の場合も
ある)。商品名に無い場合が多いため、raw_nameに追記してcoffee_parserの
焙煎度キーワード判定に使えるようにする。
"""

import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "アラビカコーヒー",
    "url": "https://www.arabicacoffee.co.jp/",
    "platform": "WordPress + Welcart",
    "address": "静岡県駿東郡長泉町南一色186-8(本社卸部/焙煎工場。直営店は沼津・富士・御殿場・三島の4店舗)",
    "prefecture": "静岡県",
    "robots_txt_status": "実質許可(2026-09確認。/wp-admin/等の管理系パスのみDisallow、"
                          "それ以外は制限なし)",
}

BASE_URL = "https://www.arabicacoffee.co.jp"
LIST_URL_FIRST = f"{BASE_URL}/category/item/"
LIST_URL_PAGE = f"{BASE_URL}/category/item/page/{{page}}/"
CRAWL_DELAY_SECONDS = 1.0
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 理由はモジュールdocstring参照(生豆・ドリップバッグ/ギフトの除外)
NON_BEAN_CATEGORY_CLASSES = {"category-green_coffee_beans", "category-dripon"}
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def fetch_soup(url: str) -> BeautifulSoup:
    return BeautifulSoup(fetch_html(url), "html.parser")


def collect_list_items() -> list[dict]:
    """一覧ページ(全ページ)を巡回し、生豆/ドリップバッグ・ギフトを除いた
    {name, url} のリストを返す(article id基準で重複排除)。"""
    items_by_id: dict[str, dict] = {}
    page = 1
    while True:
        url = LIST_URL_FIRST if page == 1 else LIST_URL_PAGE.format(page=page)
        try:
            soup = fetch_soup(url)
        except requests.RequestException as e:
            print(f"[warn] 一覧ページ取得失敗: {url} ({e})")
            break

        articles = soup.select("article[id^='post-']")
        if not articles:
            break

        for article in articles:
            post_id = article.get("id", "")
            classes = set(article.get("class", []))
            if classes & NON_BEAN_CATEGORY_CLASSES:
                continue
            name_el = article.select_one("div.itemname a")
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            product_url = name_el.get("href", "")
            if not name or not product_url:
                continue
            items_by_id[post_id] = {"raw_name": name, "product_url": product_url}

        page += 1
        time.sleep(CRAWL_DELAY_SECONDS)

    return list(items_by_id.values())


def build_record(product_url: str, title: str, roast_text: str | None, price: int | None,
                  weight_g: int | None, stock_text: str | None) -> dict:
    raw_name = f"{title} {roast_text}".strip() if roast_text else title
    parsed = parse_product(raw_name)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": raw_name,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": product_url,
        }

    structural_out_of_stock = bool(stock_text) and "在庫有り" not in stock_text
    stock_status = detect_stock_status(raw_name, structural_out_of_stock)

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
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def parse_product_detail(url: str) -> dict:
    soup = fetch_soup(url)

    title_el = soup.select_one("h1.item_page_title")
    title = title_el.get_text(strip=True) if title_el else ""

    roast_el = soup.select_one("div.roast div.BaisenComments")
    roast_text = roast_el.get_text(strip=True) if roast_el else None

    price = None
    weight_g = None
    net_weight = soup.select_one("div.net-weight")
    if net_weight:
        for dl in net_weight.select("dl"):
            dt = dl.select_one("dt")
            dd = dl.select_one("dd")
            if not dt or not dd:
                continue
            price_m = re.search(r"[\d,]+", dd.get_text())
            if not price_m:
                continue  # ヘッダ行(内容量/金額)をスキップ
            weight_m = WEIGHT_PATTERN.search(dt.get_text())
            price = int(price_m.group(0).replace(",", ""))
            weight_g = int(weight_m.group(1)) if weight_m else None
            break  # 最小重量(最初のdl)を代表として採用

    stock_el = soup.select_one("div.zaiko_status span.ss_stockstatus")
    stock_text = stock_el.get_text(strip=True) if stock_el else None

    return build_record(url, title, roast_text, price, weight_g, stock_text)


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    list_items = collect_list_items()
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for item in list_items:
        prev = previous.get(item["product_url"])
        if is_unchanged(prev, raw_name=item["raw_name"]):
            records.append(prev)
            continue

        try:
            detail = parse_product_detail(item["product_url"])
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['product_url']} ({e})")
            continue

        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)
        time.sleep(CRAWL_DELAY_SECONDS)

    return records, flavored_records


if __name__ == "__main__":
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_arabicacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_arabicacoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
