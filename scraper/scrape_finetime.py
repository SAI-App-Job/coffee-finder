# -*- coding: utf-8 -*-
"""
scrape_finetime.py

FINETIME COFFEE ROASTERS(finetime.theshop.jp、東京都世田谷区経堂)の商品情報を
取得する。NAGI COFFEE(scrape_nagi.py)と同じTHE SHOP(BASE系)プラットフォーム
だが、ショップごとにテーマ(DOM構造)が異なる(実データ確認済み、2026-08時点。
NAGIはli.column/h2.show_on_hoverという素直なクラス名だが、本ショップは
items-grid_itemTitleText_5c97110fのようなCSS Modules風のハッシュ付き
クラス名を使うテーマ)。

robots.txt確認済み(2026-08時点): NAGI COFFEEと同一の記述(curl/python-requests/
aiohttp等の一般的なHTTPクライアントは個別にDisallow: /指定があるが、
User-agent: *ルールでは/cart/・/shops/・/api/shops/・違反報告ページ以外は
Allow: /)。本スクレイパーは商品詳細ページ(/items/)とカテゴリ一覧ページ
(/categories/)のみを使用し、いずれもDisallow対象に含まれない。念のため
requestsのデフォルト値ではなく識別可能なUser-Agent(CoffeeFinderBot/0.1)を
明示的に設定している。

【対象カテゴリを「地域」の3つにした理由】
サイトのカテゴリ構成は「地域別(中米/南米/アフリカ)」と「精選方法別横断
(ウォッシュト/ハニー/ナチュラル/アナエロビック)」の2系統があるが、実データ
調査の結果、精選方法別4カテゴリの合計はカタログ全12件中11件しかカバーせず
(「ルワンダ　KARISIMBI」がいずれの精選方法カテゴリにも属していなかった)、
地域別3カテゴリの方が全12件を過不足なくカバーすることを確認した。
「スペシャル・ロット」カテゴリの商品も地域別カテゴリと重複していた(実データ
確認済み)ため、地域別3カテゴリのみをクロール対象とする。

【商品詳細の取得元(JSON-LD構造化データ)】
実データ確認済み: 各商品詳細ページに<script type="application/ld+json">
で埋め込まれたschema.org Product形式の構造化データがあり、name/description/
offers.price/offers.availabilityを含む。descriptionは「ラベル / 値」形式の
行(コーヒー名(または農園名) / 地域 / 国 / 品種 / 標高 / 生産処理)が並び、
空行を挟んでテイスティングノート等の自由記述が続く(parse_description_fields
参照)。HTMLをDOM解析するより確実な一次情報のため、これを優先的に使う。

【ラベルが「コーヒー名」「農園名」で揺れる点について】
実データ確認済み: 商品によって先頭ラベルが「コーヒー名」(例:「ウォルカ・
サカロ（完熟チェリー）」)だったり「農園名」(例:「ロス・ポジトス」)だったり
する。いずれもfarm_noteの「農園:」断片として保持する。

【値が改行を挟んで続く場合について】
実データ確認済み(item 23262248「WORKA SAKARO NATURAL」): 同じ豆の
WASHEDバージョン(item 63925904)では「コーヒー名 / ウォルカ・サカロ
（完熟チェリー）」が1行に収まっているが、NATURALバージョンでは
「コーヒー名 / ウォルカ・サカロ」と「（完熟チェリー）」が別行に分かれて
おり、後者には「ラベル / 値」の区切り(スラッシュ)が無い。単純に「スラッシュを
含まない行=自由記述の開始」と判定すると、この注記行以降(地域・国・品種等)が
すべて自由記述側に混入してしまう不具合が実データで見つかった。空行に
達するまでは、スラッシュを含まない行を直前のラベルの値への継続行として
連結することで対応している(parse_description_fields参照)。

【重量について】
実データ確認済み: ほとんどの商品は重量が商品名にもdescriptionにも一切
記載が無い(店舗の標準サイズのみで販売しているとみられる)。唯一の例外
「パナマ　BARBARA (Geisha) 50g」のように、商品名末尾に半角/全角gの重量が
付く商品のみ記載がある。存在しない情報を推測しないため、重量が明記されて
いる商品以外はweight_gをnullのままにする。
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
    detect_stock_status,
    detect_country_name,
)
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "FINETIME COFFEE ROASTERS",
    "url": "https://finetime.theshop.jp/",
    "platform": "THE SHOP(BASE系)",
    "address": "東京都世田谷区経堂1-12-15",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-08確認。NAGI COFFEEと同一の記述。/cart/・/shops/・"
                          "/api/shops/・違反報告ページ以外はUser-agent: *でAllow。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://finetime.theshop.jp"
CRAWL_DELAY_SECONDS = 2
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 理由はモジュールdocstring参照(地域別3カテゴリで全12件をカバー、
# 精選方法別カテゴリだと1件漏れる)
LIST_CATEGORIES = {
    "5918245": "中米",
    "5918246": "南米",
    "5918247": "アフリカ",
}

DESC_LABEL_PATTERN = re.compile(r"^(.+?)\s*/\s*(.+)$")
ALTITUDE_RANGE_PATTERN = re.compile(r"([\d,]+)\s*[-〜~]\s*([\d,]+)\s*m")
ALTITUDE_SINGLE_PATTERN = re.compile(r"([\d,]+)\s*m")
WEIGHT_SUFFIX_PATTERN = re.compile(r"([\d.]+)\s*[gｇ]\s*$")


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


def parse_description_fields(description: str) -> tuple[dict, str]:
    """description本文(先頭が「ラベル / 値」の行の並び、空行を挟んで自由記述が
    続く)を、構造化フィールドと自由記述(テイスティングノート等)に分ける。
    理由はモジュールdocstring参照(スラッシュを含まない行は、空行に達するまで
    直前のラベルの値への継続行として扱う)。"""
    fields: dict[str, str] = {}
    intro_lines: list[str] = []
    in_fields = True
    current_label = None
    for line in (description or "").split("\n"):
        line = line.strip()
        if not line:
            in_fields = False
            current_label = None
            continue
        if in_fields:
            m = DESC_LABEL_PATTERN.match(line)
            if m:
                current_label = m.group(1).strip()
                fields[current_label] = m.group(2).strip()
                continue
            if current_label is not None:
                fields[current_label] += line
                continue
            in_fields = False
        intro_lines.append(line)
    return fields, "\n".join(intro_lines).strip()


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


def parse_weight_from_title(title: str) -> int | None:
    text = unicodedata.normalize("NFKC", title or "")
    m = WEIGHT_SUFFIX_PATTERN.search(text)
    return int(float(m.group(1))) if m else None


def build_record(product_url: str, product: dict, category_hint: str) -> dict:
    title = (product.get("name") or "").strip()
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        offers = product.get("offers") or {}
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": int(offers["price"]) if offers.get("price") else None,
            "product_url": product_url,
        }

    fields, intro = parse_description_fields(product.get("description") or "")

    farm_name = fields.get("コーヒー名") or fields.get("農園名")
    region_detail = fields.get("地域")
    country_raw = fields.get("国")
    variety = fields.get("品種")
    processing_raw = fields.get("生産処理")

    if country_raw:
        country = detect_country_name(country_raw)
        if country:
            parsed["origin_country"] = country
            parsed["origin_source"] = "product_description"
    parsed = apply_category_hint_fallback(parsed, category_hint)

    if processing_raw:
        parsed["processing_method"] = normalize_processing_method(processing_raw)

    altitude_min, altitude_max = parse_altitude(fields.get("標高"))

    farm_note = f"農園: {farm_name}" if farm_name else None

    offers = product.get("offers") or {}
    price = int(offers["price"]) if offers.get("price") else None
    availability = offers.get("availability") or ""
    structural_out_of_stock = "InStock" not in availability
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
        "farm_note": farm_note,
        "region_detail": region_detail,
        "variety": variety,
        "altitude_min_m": altitude_min,
        "altitude_max_m": altitude_max,
        "flavor_notes": intro or None,
        "blend_components": [],
        "price": price,
        "weight_g": parse_weight_from_title(title),
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def parse_product_detail(url: str, category_hint: str = "") -> dict:
    soup = fetch_page(url)
    product = extract_jsonld_product(soup)
    if not product:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": "",
            "non_bean": True,
            "product_url": url,
        }
    return build_record(url, product, category_hint)


def scrape_category_list_page(cid: str) -> list[dict]:
    soup = fetch_page(f"{BASE_URL}/categories/{cid}")
    items = soup.select('a[href*="/items/"]')

    results = []
    seen_urls = set()
    for link_el in items:
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


def scrape_all_products() -> tuple[list[dict], list[dict], list[dict]]:
    items_by_url: dict[str, dict] = {}
    for cid, category_hint in LIST_CATEGORIES.items():
        for item in scrape_category_list_page(cid):
            items_by_url.setdefault(item["product_url"], {**item, "category_hint": category_hint})
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
            detail = parse_product_detail(product_url, item["category_hint"])
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
        with open("data_finetime.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_finetime.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件、"
              f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
