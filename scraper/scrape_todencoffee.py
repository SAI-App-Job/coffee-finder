# -*- coding: utf-8 -*-
"""
scrape_todencoffee.py

Toden Coffee(todencoffee.base.shop、東京都豊島区雑司が谷)の商品情報を取得する。
BASEの白ラベルドメイン「.base.shop」(GONZO CAFE&BEANSと同系列)。

robots.txt確認済み(2026-09時点): 他のBASE系店舗と同一の記述。curl/
python-requests等は個別にDisallow: /指定があるが、User-agent: *ルールでは
/cart/・/web_cart/・/shops/・/api/shops/・違反報告ページ以外はAllow: /。
本スクレイパーは識別可能な独自User-Agentを使用するため該当しない。

【カタログ規模・非コーヒー豆商品の除外について】
実データ確認済み(sitemap.xml上132件): 大半は単一銘柄・ブレンドの焙煎豆
(100g/200g)だが、「高性能電動ミル カリタ ナイスカットG」(電動ミル)・
「【HARIO】水出し珈琲ポットミニ 600ml」(器具)・「カリフォルニア
ノンパレル キャンポス農園 アーモンド 45g」(アーモンド)の3種は
コーヒー豆ではないためNON_BEAN_KEYWORDSで除外する。また同一銘柄が
複数回(在庫入れ替え時期違い等)登録されているように見えるが、
それぞれ別商品ID(別URL)のため重複除去はせずそのまま個別商品として扱う
(GONZO CAFE&BEANSと同じ、店舗側の運用に委ねる方針)。

【商品説明(JSON-LDのdescription)について(2026-09-19追記)】
実データ確認済み(4商品): descriptionには「透明感のある柑橘系の明るい酸が
ここちよく」「ジャスミンを思わせる繊細な花や紅茶の香り」のような具体的な
風味描写が冒頭の自由記述として入っており、その後に「品種：/精製：or
製法：/地域：or産地：/標高：/推奨焙煎度：」というラベル：値の行が続く
(ラベルとコロンの間にタブ文字が入る商品もある)。以前はJSON-LDから
商品名・価格のみ取得し、この説明文自体を一切読んでいなかった。ラベル行が
始まる前の自由記述をflavor_notesとして採用し、ラベル行からは
farm_note構成要素(品種・精製方法・地域・標高)を取得する。ラベル行の後に
さらに続く農園・産地の長い紹介文(サンプル4商品中2件で確認)は対象としない
(flavor_notesとしては冒頭の風味描写で十分なため)。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status, normalize_processing_method
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "Toden Coffee",
    "url": "https://todencoffee.base.shop/",
    "platform": "BASE",
    "address": "東京都豊島区雑司が谷",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-09確認。他のBASE系店舗と同一の記述。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://todencoffee.base.shop"
CRAWL_DELAY_SECONDS = 1.5
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["ナイスカットG", "水出し珈琲ポット", "アーモンド"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")

# 理由はモジュールdocstring参照
DESC_LABEL_PATTERN = re.compile(r"^([^:：\n]{1,10})[:：]\s*(.+)$")
DESC_LABEL_TO_FIELD = {
    "品種": "variety_note",
    "精製": "processing_method",
    "製法": "processing_method",
    "地域": "region_detail",
    "産地": "region_detail",
    "標高": "altitude_note",
}


def parse_description_details(description: str | None) -> tuple[dict, str | None]:
    """理由はモジュールdocstring参照(ラベル行が始まる前の自由記述を
    flavor_notesとして採用し、ラベル行からfarm_note構成要素を取得する)。"""
    if not description:
        return {}, None
    fields: dict[str, str] = {}
    intro_lines: list[str] = []
    seen_label = False
    for raw_line in description.replace("\t", "").split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        m = DESC_LABEL_PATTERN.match(line)
        if m:
            label = "".join(m.group(1).split())
            field = DESC_LABEL_TO_FIELD.get(label)
            if field:
                fields.setdefault(field, m.group(2).strip())
                seen_label = True
                continue
        if not seen_label:
            intro_lines.append(line)
    flavor_notes = "".join(intro_lines) if intro_lines else None
    return fields, flavor_notes


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


def build_record(product_url: str, product: dict) -> dict | None:
    title = (product.get("name") or "").strip()
    if not title:
        return None
    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)

    if parsed["is_flavored"]:
        offers = product.get("offers") or {}
        price = int(offers["price"]) if offers.get("price") is not None else None
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": product_url,
        }

    offers = product.get("offers") or {}
    price = int(offers["price"]) if offers.get("price") is not None else None
    availability = offers.get("availability") or ""
    structural_out_of_stock = "InStock" not in availability
    stock_status = detect_stock_status(title, structural_out_of_stock)

    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None

    desc_fields, flavor_notes = parse_description_details(product.get("description"))
    processing_method = desc_fields.get("processing_method")
    processing_method = normalize_processing_method(processing_method) if processing_method else parsed["processing_method"]

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
        "region_detail": desc_fields.get("region_detail"),
        "altitude_note": desc_fields.get("altitude_note"),
        "variety_note": desc_fields.get("variety_note"),
        "blend_components": [],
        "flavor_notes": flavor_notes,
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def parse_product_detail(url: str) -> dict | None:
    soup = fetch_page(url)
    product = extract_jsonld_product(soup)
    if not product:
        return None
    return build_record(url, product)


def fetch_sitemap_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    urls = []
    for loc in soup.find_all("loc"):
        text = loc.get_text(strip=True)
        if "/items/" in text:
            urls.append(text)
    return urls


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_sitemap_urls()
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for product_url in product_urls:
        prev = previous.get(product_url)
        try:
            soup = fetch_page(product_url)
            product = extract_jsonld_product(soup)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue

        if not product:
            continue
        title = (product.get("name") or "").strip()
        if is_unchanged(prev, raw_name=title):
            records.append(prev)
            continue

        detail = build_record(product_url, product)
        if detail is None:
            continue
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
        with open("data_todencoffee.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_todencoffee.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
