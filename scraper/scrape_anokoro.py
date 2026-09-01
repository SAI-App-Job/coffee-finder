# -*- coding: utf-8 -*-
"""
scrape_anokoro.py

珈琲家あのころ(anokoro.theshop.jp、東京都世田谷区)の商品情報を取得する。

【対象サイトについて(kazuki-coffee.jpではなくtheshop.jpを使う理由)】
ユーザーから最初に依頼のあったanokoro.kazuki-coffee.jp(WordPress製の店舗
紹介サイト)を実データ確認したところ、価格情報が一切無いことが判明した
(「商品の詳細や価格はオンラインショップに記載しております」と明記され、
/beanslist/ページの各豆のリンクは本サイトanokoro.theshop.jpの商品ページへ
遷移する構成)。実際の価格・在庫データは本サイト側にあるため、ユーザーに
確認の上、こちらを対象とすることにした。

【プラットフォームについて】
THE SHOP(BASE系)。NAGI COFFEE(scrape_nagi.py)・FINETIME COFFEE ROASTERS
(scrape_finetime.py)と同じくschema.org JSON-LD構造化データを持つテーマ
(class名のハッシュ値からは3店舗とも同一テーマ系統と確認: items-grid_*_
5c97110f)。ただし本サイトはdescription欄の情報がこれまでで最も構造化されて
おり(下記参照)、FINETIMEのような「スラッシュを跨ぐ継続行」の特殊処理は不要。

robots.txt確認済み(2026-09時点): NAGI COFFEE・FINETIME COFFEE ROASTERSと同一の
記述(curl/python-requests/aiohttp等の一般的なHTTPクライアントは個別に
Disallow: /指定があるが、User-agent: *ルールでは/cart/・/shops/・違反報告
ページ以外はAllow: /)。本スクレイパーが使用する商品詳細ページ(/items/)と
カテゴリ一覧ページ(/categories/)はいずれもDisallow対象に含まれない。

【対象カテゴリについて】
「コーヒー豆」(親カテゴリ、id=7380383)配下に「ブレンドコーヒー豆」(4件)・
「シングルオリジンコーヒー豆」(10件)の2サブカテゴリがあり、実データ確認済み
(2026-09時点): 親カテゴリのページ自体がこの2サブカテゴリの合計14件と完全に
一致する(ページネーション無し、全14件が1ページに収まることも確認済み)。
「ギフトセット」「200g用ギフト袋」「ギフトボックス」「オリジナル商品」
「リキッドコーヒー」「グッズ」「コーヒー抽出器具」等の非対象カテゴリは
親カテゴリに含まれておらず、除外用のキーワード処理は不要だった。

【商品詳細ページのdescription(JSON-LD)の構造について】
実データ確認済み(14件全件): 以下の順で構造化されたテキストが並ぶ。
  1行目: 商品名(タイトルと重複、無視)
  焙煎：<8段階表記>（<粗い説明>）  ← ライト〜イタリアンの専門用語がそのまま
    使われており、商品名の【】内にも同じ表記が含まれるため、
    coffee_parser.parse_product()の商品名解析だけでroast_levelが正しく
    判定できる(本スクレイパー側で個別に抽出する必要は無い)
  内容量：<重量>g
  ▼香味パラメーター▼ / 甘味：★★★☆☆　酸味：...　(星評価。本アプリの
    スキーマに対応する構造化フィールドが無いため取り込まない)
  ■■■　詳細情報　■■■ (シングルオリジンのみ。ブレンドには無い)
  地域：<エリア>
  農園：<農園名>
  品種：<品種>
  標高：<標高>
  精製：<精選方法>
  【デカフェ処理方法】：<デカフェ加工方法>  (デカフェ商品のみ)
  (自由記述のテイスティングコメント)
  【Cup Impression】
  <フレーバー用語の並び>
  (店の定型文、無視)
ラベル行はすべて「ラベル：値」形式(【デカフェ処理方法】のみ【】で囲まれる)で
一貫しているため、汎用的な行パーサーで抽出する(parse_description_fields参照)。

【デカフェ商品の「精製」欄について】
実データ確認済み(146299843「メキシコ　トリウンフォ・ベルデ」): デカフェ商品にも
「精製：ウォッシュト」という通常のコーヒーチェリー精製方法の欄と、別途
「【デカフェ処理方法】：ウォータープロセス：マウンテンウォーター(デスカメックス社)」
という専用欄が明確に分かれて存在する。豆善(scrape_mamezen.py)のように欄を
振り分ける必要が無く、そのままprocessing_method/decaf_processに対応させられる。

【ブレンドについて】
実データ確認済み(4件全件): ブレンドは「■■■　詳細情報　■■■」ブロック自体が
存在せず(地域・農園・品種・標高・精製の記載無し)、配合比率の記載も無い。
産地情報は一切公開されていないため、origin_country/blend_componentsは
空(null/[])のままにする。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, normalize_processing_method, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "珈琲家あのころ",
    "url": "https://anokoro.theshop.jp/",
    "platform": "THE SHOP(BASE系)",
    "address": "東京都世田谷区若林4-20-9 岡村ビル1F",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-09確認。NAGI COFFEE・FINETIME COFFEE ROASTERSと同一の記述。"
                          "/cart/・/shops/・違反報告ページ以外はUser-agent: *でAllow。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://anokoro.theshop.jp"
CRAWL_DELAY_SECONDS = 2
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 理由はモジュールdocstring参照(親カテゴリがブレンド/シングルオリジンの
# 2サブカテゴリを過不足なく包含する)
CATEGORY_ID = "7380383"  # コーヒー豆

DETAIL_LABEL_PATTERN = re.compile(r"^【?([^：\n【】]+)】?：\s*(.*)$")
ALTITUDE_RANGE_PATTERN = re.compile(r"([\d,]+)\s*[-〜~]\s*([\d,]+)\s*m")
ALTITUDE_SINGLE_PATTERN = re.compile(r"([\d,]+)\s*m")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def extract_jsonld_product(soup: BeautifulSoup) -> dict | None:
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        text = script.string or script.get_text() or ""
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == "Product":
            return data
    return None


def parse_description_fields(description: str) -> tuple[dict, list[str]]:
    """description本文を「ラベル：値」の行ごとに抽出しつつ、【Cup Impression】
    見出し以降の自由記述行をフレーバー用語として別に集める。理由はモジュール
    docstring参照。"""
    fields: dict[str, str] = {}
    flavor_terms: list[str] = []
    in_cup_impression = False

    for line in (description or "").split("\n"):
        line = line.strip()
        if not line:
            in_cup_impression = False
            continue
        if line == "【Cup Impression】":
            in_cup_impression = True
            continue
        if in_cup_impression:
            flavor_terms.append(line)
            continue
        m = DETAIL_LABEL_PATTERN.match(line)
        if m:
            fields[m.group(1).strip()] = m.group(2).strip()

    return fields, flavor_terms


def parse_altitude(altitude_text: str | None) -> tuple[int | None, int | None]:
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


def parse_weight(text: str | None) -> int | None:
    if not text:
        return None
    m = WEIGHT_PATTERN.search(unicodedata.normalize("NFKC", text))
    return int(m.group(1)) if m else None


def build_record(product_url: str, product: dict) -> dict:
    title = (product.get("name") or "").strip()
    parsed = parse_product(title)
    is_blend = parsed["category"] == "ブレンド"

    fields, flavor_terms = parse_description_fields(product.get("description") or "")
    decaf = "デカフェ" in title

    processing_raw = None if is_blend else fields.get("精製")
    processing_method = normalize_processing_method(processing_raw) if processing_raw else None
    decaf_process = fields.get("デカフェ処理方法") if decaf else None

    altitude_min, altitude_max = (None, None) if is_blend else parse_altitude(fields.get("標高"))

    offers = product.get("offers") or {}
    price = int(offers["price"]) if offers.get("price") else None
    availability = offers.get("availability") or ""
    structural_out_of_stock = "InStock" not in availability
    stock_status = detect_stock_status(title, structural_out_of_stock)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing_method,
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "post_processing_tags": parsed["post_processing_tags"],
        "farm_name": None if is_blend else fields.get("農園"),
        "region_detail": None if is_blend else fields.get("地域"),
        "variety": None if is_blend else fields.get("品種"),
        "altitude_min_m": altitude_min,
        "altitude_max_m": altitude_max,
        "decaf_process": decaf_process,
        "flavor_notes": "、".join(flavor_terms) if flavor_terms else None,
        "blend_components": [],
        "price": price,
        "weight_g": parse_weight(fields.get("内容量")),
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def parse_product_detail(url: str) -> dict:
    soup = fetch_page(url)
    product = extract_jsonld_product(soup)
    if not product:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": "",
            "non_bean": True,
            "product_url": url,
        }
    return build_record(url, product)


def scrape_category_list() -> list[dict]:
    soup = fetch_page(f"{BASE_URL}/categories/{CATEGORY_ID}")
    results = []
    seen_urls = set()
    for link_el in soup.select('a[href*="/items/"]'):
        title_el = link_el.select_one('[class*="itemTitleText"]')
        if not title_el:
            continue
        href = link_el.get("href", "")
        product_url = href if href.startswith("http") else f"{BASE_URL}{href}"
        if product_url in seen_urls:
            continue
        seen_urls.add(product_url)
        results.append({"raw_name": title_el.get_text(strip=True), "product_url": product_url})
    return results


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    items = scrape_category_list()
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    non_bean_records = []
    for item in items:
        prev = previous.get(item["product_url"])
        if is_unchanged(prev, raw_name=item["raw_name"]):
            records.append(prev)
            continue

        try:
            detail = parse_product_detail(item["product_url"])
            if detail.get("non_bean"):
                non_bean_records.append(detail)
            else:
                records.append(detail)
            time.sleep(CRAWL_DELAY_SECONDS)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['product_url']} ({e})")

    return records, non_bean_records


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        result = parse_product_detail(sys.argv[1])
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        records, non_bean_records = scrape_all_products()
        output = {
            "shop": SHOP_INFO,
            "products": records,
            "non_bean_products_excluded": non_bean_records,
        }
        with open("data_anokoro.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_anokoro.json に出力しました"
              f"(非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
