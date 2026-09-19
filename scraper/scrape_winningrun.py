# -*- coding: utf-8 -*-
"""
scrape_winningrun.py

豆工房ウイニングラン(mamekobo.ocnk.net、〒709-0611 岡山県岡山市東区楢原
514-6、自家焙煎豆のオンライン販売)の商品情報を取得する。おちゃのこネット
(Ocnk)。

ファイル名について: 既存の scrape_mamekobo.py は別店舗(豆香房、東京都
千代田区)に既に使用されているため、店舗名の英語表記「Winning Run」から
本ファイルは scrape_winningrun.py とする。

robots.txt確認済み(2026-09時点): 他のOcnk店舗と同一の記述。User-agent: *
には制限なし(GPTBot/Bytespider/TikTokSpider/meta-externalagentのみ
Disallow: /で本スクレイパーは該当しない)。

【商品一覧の取得方法について】
実データ確認済み: sitemap.xmlに/product/N形式の個別商品ページへの
リンクが37件含まれており、全件がコーヒー豆単品(除外対象の詰め合わせ・
器具等は無い)。

【価格表記について】
実データ確認済み: 商品名に「生豆220ｇでの焙煎(税込)価格」のように、
焙煎前の生豆重量を基準にした価格であることが明記されている(注文後に
生豆から焙煎する方式)。本スクレイパーではこの生豆重量をweight_gとして
採用する(焙煎後の実重量はこれよりやや少なくなるが、この店の価格基準に
準拠する)。

【重量違いの重複について】
実データ確認済み: 「ハワイコナ」「キングブルマンＮＯ1」の2銘柄のみ
220g/110gの2種類の重量で別商品ページとして登録されている。商品名から
「生豆◯ｇでの焙煎(税込)価格」の部分を除いた基準名でグルーピングし、
最小重量(110g)を代表として採用する。

【flavor_notes/farm_note(テイスティングノート・農園情報)について
(2026-09-20追記)】
実データ確認済み(37商品全件): おちゃのこネットのdiv.item_desc_textに
店主による1〜2文の風味紹介文があり、単一銘柄の一部商品では続けて
「生産者：」「農園：」「地域：」「エリア：」「生産国：」「標高：」
「品種：」「精製：」「精製方法：」ラベルの農園情報、さらにその後に
農園の歴史等の長い説明文が続く場合がある。以前はog:title/価格のみ
取得しこの要素自体を一切読んでいなかった。ラベル行より前の自由文を
flavor_notesとして採用し、ラベル値はfarm_note用フィールドに反映する
(ラベル以降の追加説明文はEureka Coffee Roasters等と同様、構造化できない
ためflavor_notesには含めない)。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status, normalize_processing_method

SHOP_INFO = {
    "name": "豆工房ウイニングラン",
    "url": "https://mamekobo.ocnk.net/",
    "platform": "おちゃのこネット",
    "address": "岡山県岡山市東区楢原514-6",
    "prefecture": "岡山県",
    "robots_txt_status": "実質許可(2026-09確認。User-agent: *には制限なし。"
                          "GPTBot/Bytespider/TikTokSpider/meta-externalagentのみ"
                          "Disallow: /で本スクレイパーは該当しない)",
}

BASE_URL = "https://mamekobo.ocnk.net"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

WEIGHT_TAIL_PATTERN = re.compile(r"[\s　]*生豆\s*(\d+)\s*[gｇ]\s*での焙煎\s*(?:税込)?\s*価格\s*$")
DESC_LABEL_PATTERN = re.compile(r"^([^:：\n]{1,10})[：:]\s*(.*)$")
FARM_LABEL_TO_FIELD = {
    "生産者": "producer_name",
    "農園": "farm_name",
    "地域": "region_detail",
    "エリア": "region_detail",
    "生産国": "region_detail",
    "標高": "altitude_note",
    "品種": "variety_note",
}


def parse_description_details(soup: BeautifulSoup) -> tuple[str | None, dict, str | None]:
    """理由はモジュールdocstring参照。flavor_notes・farm情報・精製方法(生値)を返す。"""
    el = soup.select_one("div.item_desc_text")
    if not el:
        return None, {}, None
    flavor_lines = []
    farm: dict = {}
    processing_raw = None
    collecting_flavor = True
    for raw_line in el.get_text(separator="\n").split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        m = DESC_LABEL_PATTERN.match(line)
        if m:
            label = "".join(m.group(1).split())
            value = m.group(2).strip()
            if label in FARM_LABEL_TO_FIELD:
                collecting_flavor = False
                if value:
                    farm[FARM_LABEL_TO_FIELD[label]] = value
                continue
            if label in ("精製", "精製方法"):
                collecting_flavor = False
                if value:
                    processing_raw = value
                continue
        if collecting_flavor:
            flavor_lines.append(line)
    flavor_notes = "".join(flavor_lines) or None
    return flavor_notes, farm, processing_raw


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_product_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [
        loc.get_text(strip=True) for loc in soup.find_all("loc")
        if re.search(r"/product/\d+$", loc.get_text(strip=True))
    ]


def extract_fields(soup: BeautifulSoup) -> dict | None:
    title_el = soup.select_one('meta[property="og:title"]')
    if not title_el or not title_el.get("content"):
        return None
    title = re.sub(r"\s+", " ", title_el["content"].strip())
    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None
    return {"title": title, "price": price}


def base_name_and_weight(title: str) -> tuple[str, int | None]:
    m = WEIGHT_TAIL_PATTERN.search(title)
    weight_g = int(m.group(1)) if m else None
    base = WEIGHT_TAIL_PATTERN.sub("", title).strip()
    return base, weight_g


def pick_canonical_items(items: list[dict]) -> list[dict]:
    by_base_name: dict[str, dict] = {}
    for item in items:
        base, weight_g = base_name_and_weight(item["title"])
        item["base_name"] = base
        item["weight_g"] = weight_g
        weight_key = weight_g if weight_g is not None else float("inf")
        existing = by_base_name.get(base)
        if existing is None:
            by_base_name[base] = item
            continue
        existing_weight = existing["weight_g"] if existing["weight_g"] is not None else float("inf")
        if weight_key < existing_weight:
            by_base_name[base] = item
    return list(by_base_name.values())


def build_record(item: dict) -> dict | None:
    title = item["base_name"]
    if not title:
        return None
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

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"] or normalize_processing_method(item.get("processing_method_raw")),
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "farm_name": item.get("farm", {}).get("farm_name"),
        "producer_name": item.get("farm", {}).get("producer_name"),
        "region_detail": item.get("farm", {}).get("region_detail"),
        "altitude_note": item.get("farm", {}).get("altitude_note"),
        "variety_note": item.get("farm", {}).get("variety_note"),
        "flavor_notes": item.get("flavor_notes"),
        "price": item["price"],
        "weight_g": item["weight_g"],
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_product_urls()

    all_items = []
    for product_url in product_urls:
        try:
            soup = fetch_page(product_url)
            fields = extract_fields(soup)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if not fields:
            continue
        flavor_notes, farm, processing_raw = parse_description_details(soup)
        all_items.append({
            "title": fields["title"],
            "price": fields["price"],
            "url": product_url,
            "flavor_notes": flavor_notes,
            "farm": farm,
            "processing_method_raw": processing_raw,
        })

    canonical_items = pick_canonical_items(all_items)

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
    with open("data_winningrun.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_winningrun.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
