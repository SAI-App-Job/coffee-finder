# -*- coding: utf-8 -*-
"""
scrape_itukacoffee.py

いつか珈琲屋(itukacoffee.official.ec、神奈川県平塚市河内)の商品情報を取得する。
カフェクラウディア(scrape_cafeclaudia.py)と同じBASEプラットフォームだが、
異なるBASEテーマ(店舗ごとに選べるデザインテンプレート)が使われているため、
CSSセレクタ・DOM構造は別物として実データから調べ直した。

【カフェクラウディアとの違いについて】実データ確認済み(2026-08時点):
カフェクラウディアの`div.card`ベースの一覧、`h1.itemTitle`の商品タイトル、
`id="price"`の価格divは本店には存在しない(BASEテーマが異なるため)。代わりに
一覧ページは`a[href*="/items/"]`(class名にビルドハッシュが付くため属性値の
部分一致で拾う)、詳細ページは`h2[class*="item-detail_itemTitle"]`(タイトル。
注意: `<h1>`はショップロゴ画像に使われており商品タイトルではない)、
`p[class*="item-detail_price"]`(価格)、`p[class*="item-detail_soldOut"]`
(SOLD OUT表示。存在すれば品切れ)という構造。

【対象カテゴリについて】実データ確認済み(2026-08時点): 「オリジナルブレンド」
(id=2239064、7件)と「シングルオリジン／産地別」(id=2239068、13件)の2カテゴリ
で豆売り商品を網羅できる。「焙煎度合いで選ぶ」配下の4小カテゴリは上記2つと
同じ商品を焙煎度別に再掲載しているだけの導線(実データ確認済み: 同一商品URLが
複数カテゴリに出現)のため、二重取得を避けるためスクレイピング対象に含めない。
「飲み比べセット」「コーヒーバッグ」「カフェオレベース」「ギフト」「福袋」は
豆売り商品ではないため対象外。「オリジナルブレンド」カテゴリ内にも
「【飲み比べ】ブレンド100ｇ×３種セット」という比較セット商品が1件混在して
いたため、商品名に「セット」を含む商品は除外する。

【商品説明文の構造化データについて】実データ確認済み(2026-08時点): 商品詳細
ページの説明文(`item-detail_description`)には、読み物調の紹介文に続けて
「ラベル：値」形式の行が入っている。ブレンドは「焙煎度合い：X」「生産国：Y」
(Yは複数国をカンマ区切りで併記)のみ、シングルオリジンはさらに「エリア：X」
「標高：X」「品種：X」「農園名：X」「生産処理：X」「生産者：X」まで含む。
商品名からのパース(coffee_parser.parse_product、他店舗と同じ一次情報源)を
基本としつつ、産地国・精選方法が商品名だけで判定できなかった場合の
フォールバック、および農園名・品種・標高・生産者・エリア(商品名には出てこない
情報)の取得元として、この構造化ラベル行を利用する。

【デカフェの検出について】実データ確認済み: 「デカフェ　メキシコ　チアパス
　シティロースト」のようにタイトルへ「デカフェ」が明記される。カフェクラ
ウディアと同じdetect_decaf_processヘルパーを再利用する(除去方法の記載が
無い場合は「デカフェ(除去方法の詳細記載なし)」を返す)。

robots.txt確認済み(2026-08時点): カフェクラウディアと同一のBASE標準
robots.txt。curl/python-requests等の匿名UAは名指しで全面禁止されているが、
独自User-Agent(CoffeeFinderBot)は「User-agent: *」規定の対象となり、
/cart/・/web_cart/・/shops/・/api/shops/等以外は許可されている。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    normalize_processing_method,
    detect_country_name,
    detect_stock_status,
)

SHOP_INFO = {
    "name": "いつか珈琲屋",
    "url": "https://itukacoffee.official.ec/",
    "platform": "BASE",
    "address": "神奈川県平塚市河内1-7-1",
    "prefecture": "神奈川県",
    "robots_txt_status": (
        "許可(2026-08確認。カフェクラウディアと同一のBASE標準robots.txt。"
        "curl/python-requests等の匿名UAは名指しで全面禁止だが、独自User-Agent"
        "(CoffeeFinderBot)は「User-agent: *」規定の対象となり、"
        "/cart/・/web_cart/・/shops/・/api/shops/等以外は許可)"
    ),
}

BASE_URL = "https://itukacoffee.official.ec"
# 実データ確認済み: 「オリジナルブレンド」「シングルオリジン／産地別」の
# 2カテゴリで豆売り商品を網羅できる(モジュール冒頭docstring参照)
TARGET_CATEGORY_IDS = [2239064, 2239068]
CRAWL_DELAY_SECONDS = 1  # robots.txt確認済み(2026-08時点): User-agent:*にCrawl-delay指定なし
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

EXCLUDE_TITLE_KEYWORDS = ["セット"]

WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
FIELD_LINE_PATTERN = re.compile(
    r"^(焙煎度合い|生産国|エリア|標高|品種|農園名|生産処理|生産者)\s*[：:]\s*(.+)$"
)
ALTITUDE_RANGE_PATTERN = re.compile(r"([\d,]+)\s*[-〜~]\s*([\d,]+)\s*m")
ALTITUDE_SINGLE_PATTERN = re.compile(r"([\d,]+)\s*m")
DECAF_PROCESS_NAME_PATTERN = re.compile(r"(マウンテンウォータープロセス)")


def fetch_soup(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def is_decaf(title: str) -> bool:
    return "カフェインレス" in title or "デカフェ" in title


def detect_decaf_process(title: str, fields: dict) -> str | None:
    """実データ確認済み: デカフェ商品では「生産処理」欄がコーヒーチェリーの
    精選方法ではなく脱カフェイン方法(例:「マウンテンウォーター製法」)を
    指しているため、その値を最優先で使う(processing_methodへは流用しない。
    is_decaf()呼び出し側で除外している)。"""
    if not is_decaf(title):
        return None
    if fields.get("生産処理"):
        return fields["生産処理"]
    m = DECAF_PROCESS_NAME_PATTERN.search(title)
    if m:
        return f"{m.group(1)}によりカフェインを除去"
    return "デカフェ(除去方法の詳細記載なし)"


def parse_description_fields(description_text: str) -> dict:
    """「ラベル：値」形式の行を辞書にする(モジュール冒頭docstring参照)。"""
    fields = {}
    for raw_line in description_text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        m = FIELD_LINE_PATTERN.match(line)
        if m:
            fields[m.group(1)] = m.group(2).strip()
    return fields


def parse_altitude(altitude_text: str | None) -> tuple[int | None, int | None]:
    """実データ確認済み: 「1570-1770m」「1600ｍ」「１，７００～１８８０ｍ」の
    ように、半角/全角の数字・カンマ・波ダッシュ・m表記が店舗内でも商品ごとに
    揺れている。unicodedata.normalize("NFKC", ...)で全角数字・全角カンマ・
    全角m・全角チルダを半角へ正規化してからスペースを除去し、半角基準の
    パターンだけで一貫して扱えるようにする。「1, 400 ｍ～ 1,500 ｍ」のように
    数値ごとに単位が付く表記は範囲パターンにマッチしないため、単一値として
    先頭の数値のみ拾う(実データ確認済み: この1件のみ発生。範囲の一部でも
    取得できる方を優先)。"""
    if not altitude_text:
        return None, None
    text = unicodedata.normalize("NFKC", altitude_text)
    text = re.sub(r"\s", "", text)
    m = ALTITUDE_RANGE_PATTERN.search(text)
    if m:
        return int(m.group(1).replace(",", "")), int(m.group(2).replace(",", ""))
    m = ALTITUDE_SINGLE_PATTERN.search(text)
    if m:
        value = int(m.group(1).replace(",", ""))
        return value, value
    return None, None


def scrape_category_list_page(category_id: int, page: int) -> list[str]:
    url = f"{BASE_URL}/categories/{category_id}"
    if page > 1:
        url += f"?page={page}"
    soup = fetch_soup(url)

    urls = []
    seen = set()
    for link in soup.select('a[href*="/items/"]'):
        href = link.get("href", "")
        product_url = href if href.startswith("http") else f"{BASE_URL}{href}"
        if product_url in seen:
            continue
        seen.add(product_url)
        urls.append(product_url)
    return urls


def parse_product_detail(url: str) -> dict:
    soup = fetch_soup(url)

    title_el = soup.select_one('[class*="item-detail_itemTitle"]')
    raw_name = title_el.get_text(strip=True) if title_el else ""

    price_el = soup.select_one('[class*="item-detail_price_"]')
    price = None
    if price_el:
        m = re.search(r"[¥￥]([\d,]+)", price_el.get_text())
        if m:
            price = int(m.group(1).replace(",", ""))

    weight_match = WEIGHT_PATTERN.search(raw_name)
    weight_g = int(weight_match.group(1)) if weight_match else None

    sold_out = soup.select_one('[class*="item-detail_soldOut"]') is not None
    stock_status = detect_stock_status(raw_name, sold_out)

    desc_el = soup.select_one('[class*="item-detail_description"]')
    description_text = desc_el.get_text() if desc_el else ""
    fields = parse_description_fields(description_text)

    parsed = parse_product(raw_name)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": raw_name,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "stock_status": stock_status,
            "product_url": url,
        }

    # ブレンドは生産国を単一の産地として持たない(「生産国：ニカラグア、
    # エルサルバドル」のように複数国併記のため、data-model.mdの設計どおり
    # origin_countryはnullのままにする)
    if not parsed["origin_country"] and parsed["category"] != "ブレンド" and fields.get("生産国"):
        detected = detect_country_name(fields["生産国"]) or fields["生産国"]
        parsed["origin_country"] = detected
        parsed["origin_source"] = "product_description"
    parsed = apply_category_hint_fallback(parsed, None)

    # デカフェ商品の「生産処理」欄は脱カフェイン方法を指すため、精選方法
    # (processing_method)へは流用しない(detect_decaf_process側で使う)
    if not parsed["processing_method"] and fields.get("生産処理") and not is_decaf(raw_name):
        parsed["processing_method"] = normalize_processing_method(fields["生産処理"])

    altitude_min_m, altitude_max_m = parse_altitude(fields.get("標高"))

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
        "roast_selectable": False,  # 実データ確認済み: 選択肢は挽き方・重量のみで焙煎度選択は無い
        "post_processing_tags": parsed["post_processing_tags"],
        "farm_name": fields.get("農園名"),
        "producer_name": fields.get("生産者"),
        "region_detail": fields.get("エリア"),
        "altitude_min_m": altitude_min_m,
        "altitude_max_m": altitude_max_m,
        "variety": fields.get("品種"),
        "decaf_process": detect_decaf_process(raw_name, fields),
        "weight_g": weight_g,
        "price": price,
        "stock_status": stock_status,
        "product_url": url,
    }


def is_target_title(raw_name: str) -> bool:
    return not any(kw in raw_name for kw in EXCLUDE_TITLE_KEYWORDS)


def scrape_all_products(max_pages: int = 20) -> tuple[list[dict], list[dict]]:
    all_urls: list[str] = []
    seen_urls = set()
    for category_id in TARGET_CATEGORY_IDS:
        for page in range(1, max_pages + 1):
            urls = scrape_category_list_page(category_id, page)
            if not urls:
                break
            for u in urls:
                if u not in seen_urls:
                    seen_urls.add(u)
                    all_urls.append(u)
            time.sleep(CRAWL_DELAY_SECONDS)

    records = []
    flavored_records = []
    for url in all_urls:
        try:
            detail = parse_product_detail(url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {url} ({e})")
            continue
        if not is_target_title(detail["raw_name"]):
            continue
        detail["out_of_stock"] = detail.get("stock_status", "販売中") != "販売中"
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)
        time.sleep(CRAWL_DELAY_SECONDS)

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
        with open("data_itukacoffee.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_itukacoffee.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
