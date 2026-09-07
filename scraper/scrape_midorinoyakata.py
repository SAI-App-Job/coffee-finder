# -*- coding: utf-8 -*-
"""
scrape_midorinoyakata.py

自家焙煎珈琲豆の店「緑の館」(運営: 株式会社グリーンハウスコーヒー、
midorinoyakata.ocnk.net、岐阜県下呂市萩原町花池123番地、自家焙煎豆の
オンライン販売)の商品情報を取得する。おちゃのこネット(Ocnk)。

【住所について】
候補リストでは第三者情報源(複数)による「岐阜県下呂市萩原町花池125-1」
という住所が示されていたが、Ocnk店舗トップページからリンクされている
運営会社の別サイト(www.midorinoyakata.com)の特定商取引法ページ
(signage/index.html)で「店舗所在地: 岐阜県下呂市萩原町花池123番地」と
明記されているのを確認したため、一次情報源であるこちらを採用する。

robots.txt確認済み(2026-09時点): User-agent: *には制限なし
(GPTBot/Bytespider/TikTokSpider/meta-externalagentのみDisallow: /)。
本スクレイパーは該当しない。

【対象カテゴリの絞り込みについて】
実データ確認済み: 商品カテゴリ一覧は15種類あるが、単一銘柄のコーヒー豆
販売はブレンド(product-list/2)・ロイヤルブレンドコーヒー(product-list/3)・
スペシャルティコーヒー(product-list/4)・デカフェ・カフェインレスコーヒー
(product-list/6)の4カテゴリのみ。それ以外(ドリップコーヒー=ドリップ
バッグのアソートセット専用カテゴリ、カフェオレベース、ギフトセット、
リキッドコーヒー/クラッシュゼリー/水出しコーヒー、お試しセット=おまかせ
詰め合わせ専用、グッズ、お得なセット=ドリップアソート専用、ネコポス商品=
銘柄を指定しない「お好きなスペシャルティ/ブレンド200g」枠、お歳暮
ギフトセット、特注商品)は単一銘柄の豆売りではないため、CATEGORY_PATHSで
対象カテゴリのみに絞り込む。

【非コーヒー豆商品の除外について】
実データ確認済み: 対象4カテゴリ内にも、月替わり詰め合わせ「スペシャルティ
200g×4種+ブレンド200g×1種 (計1,000g)」(9月号・8月号の2件、単一銘柄と
特定できない)と「デカフェ・コーヒードリップパック5杯入り」(ドリップ
バッグ、豆売りではない)が混在している。NON_BEAN_KEYWORDSで除外する。

【重量・価格のバリエーションについて】
実データ確認済み: 全商品が「種類」(豆/粉)と「容量」(100g/200g/300g/
500g/…業務用2kg)の2軸バリエーションを持つOcnk固有のvariation機構を
使っている。価格は容量のみに連動し「種類」(豆か粉か)では変わらない
ことを複数商品で確認済み(例: product/492は豆・粉どちらも100g=880円で
同額)。かつpConf.priceMin/pConf.priceMaxは常に最小容量(100g、先頭の
<option>)と最大容量の価格に一致することを確認済みのため、値段は
priceMinを直接採用し、容量は「容量」ラベルのselect内の先頭<option>
(=最小重量)のテキストから取得する。個別のvariation/price/stock配列
(pConf.priceArray[1][種類値][容量値]等)まで踏み込んだ解析は不要。

【SOLDOUT表記について】
実データ確認済み: 一時的に品切れの商品は商品名の先頭に「SOLDOUT」が
付与される(例:「SOLDOUT　■インドネシア / スマトラ・マンデリン・
アチェ・バテラ農協 / Ache Bahtera /ミディアム〜ハイロースト」)。
stock_status_synonyms.jsonの既存シノニム("sold out"、半角スペースあり)
とは表記が異なり半角スペースなしの「SOLDOUT」のため、シノニム辞書には
無い本店舗固有の表記としてスクレイパー側で個別に検出し、接頭辞を
商品名から除去した上でdetect_stock_status()にstructural_out_of_stock=True
として渡す。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "緑の館",
    "url": "https://www.midorinoyakata.com/",
    "platform": "おちゃのこネット",
    "address": "岐阜県下呂市萩原町花池123番地",
    "prefecture": "岐阜県",
    "robots_txt_status": "実質許可(2026-09確認。User-agent: *には制限なし。"
                          "GPTBot等AI系クローラーのみDisallow: /で本スクレイパーは"
                          "該当しない)",
}

BASE_URL = "https://midorinoyakata.ocnk.net"
CATEGORY_PATHS = ["product-list/2", "product-list/3", "product-list/4", "product-list/6"]
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["計1,000g", "ドリップパック"]
SOLDOUT_PREFIX_PATTERN = re.compile(r"^SOLDOUT[\s　]*", re.IGNORECASE)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
PRICE_MIN_PATTERN = re.compile(r"pConf\.priceMin\s*=\s*(\d+);")
VARIATION_LABEL_SELECT_PATTERN = re.compile(
    r'<span class="variation_label">([^<]*)</span>.*?<select[^>]*>(.*?)</select>', re.DOTALL
)
OPTION_PATTERN = re.compile(r'<option value="(\d+)">([^<]*)</option>')


def fetch_page(url: str) -> tuple[BeautifulSoup, str]:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser"), resp.text


def fetch_product_urls() -> list[str]:
    pids: set[str] = set()
    for path in CATEGORY_PATHS:
        soup, _ = fetch_page(f"{BASE_URL}/{path}")
        for a in soup.select(f'a[href*="{BASE_URL}/product/"]'):
            m = re.search(r"/product/(\d+)", a.get("href", ""))
            if m:
                pids.add(m.group(1))
    return [f"{BASE_URL}/product/{pid}" for pid in pids]


def extract_min_weight_g(html: str) -> int | None:
    """「容量」ラベルのselectブロックから、先頭(=最小重量)の<option>を
    重量として採用する(house rule: 重量違いは最小重量を代表とする)。"""
    for label, select_html in VARIATION_LABEL_SELECT_PATTERN.findall(html):
        if "容量" not in label:
            continue
        options = OPTION_PATTERN.findall(select_html)
        if not options:
            continue
        _, first_text = options[0]
        weight_m = WEIGHT_PATTERN.search(first_text)
        if weight_m:
            return int(weight_m.group(1))
    return None


def build_record(soup: BeautifulSoup, html: str, product_url: str) -> dict | None:
    title_el = soup.select_one('meta[property="og:title"]')
    raw_title = title_el["content"].strip() if title_el and title_el.get("content") else ""
    if not raw_title or any(kw in raw_title for kw in NON_BEAN_KEYWORDS):
        return None

    structural_out_of_stock = bool(SOLDOUT_PREFIX_PATTERN.match(raw_title))
    title = SOLDOUT_PREFIX_PATTERN.sub("", raw_title).strip()

    parsed = parse_product(title)

    price_m = PRICE_MIN_PATTERN.search(html)
    price = int(price_m.group(1)) if price_m else None

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

    weight_g = extract_min_weight_g(html)
    stock_status = detect_stock_status(title, structural_out_of_stock)

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
            soup, html = fetch_page(product_url)
            detail = build_record(soup, html, product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
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
    with open("data_midorinoyakata.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_midorinoyakata.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
