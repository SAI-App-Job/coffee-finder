# -*- coding: utf-8 -*-
"""
scrape_obscuracoffee.py

OBSCURA COFFEE ROASTERS(shop.obscura-coffee.com、東京都世田谷区三軒茶屋・
広島市広島袋町の2拠点、自家焙煎豆のオンライン販売)の商品情報を取得する。

【店舗発見の経緯】
高田馬場エリアの調査を機に開始した全国の未調査エリア洗い出しの一環で、渋谷
エリアを調査した際に発見(渋谷区道玄坂1-12-1の渋谷東急フードショー内にも
店舗を構える)。本スクレイパーのSHOP_INFOは創業由来の三軒茶屋本店の住所を
代表値として採用する。

【対象カテゴリについて】
実データ確認済み(2026-09時点): 「シングルオリジン」(/product/list/4、27件)と
「ブレンド コーヒー」(/product/list/3、6件)の合計33件を対象とする。「生豆
（グリーンビーンズ）」「DRIP BAG」「ICED COFFEE」「COFFEE GIFT」「COFFEE
GOODS」は非対象。「DECAF」カテゴリは上記2カテゴリと商品が重複している
(デカフェ豆もシングルオリジン/ブレンドいずれかに属している)ため、別途
巡回はしない。「【季節限定】秋の珈琲豆3種セット」のような複数銘柄セットは
NON_BEAN_KEYWORDSで除外する。

【同一銘柄の200g/1kg重複について】
実データ確認済み: 多くの銘柄が「200g」「1kg」を別々の商品ページ(別pid)として
展開している(例: 「【深煎り】ケニア「ニャンジャファクトリー」1kg」pid=999と
「【深煎り】 ケニア「ニャンジャファクトリー」 200g」pid=998)。1商品1レコードの
原則に基づき、重量表記を除いた銘柄名が一致する場合は最小重量(200g)側のみを
採用する(1kgのみでバリエーションが無い銘柄はそのまま採用)。

【商品説明の構造について】
実データ確認済み(全商品で共通): div.spec_desc_overviewBlock_left_body に
「テイスティング文(1〜数文) + 酸味/コクの★段階評価 + 品種/地区/精製方法/標高の
ラベル付き仕様」が改行(<br>)区切りで並ぶ。酸味/コク評価行(「酸味：」「コク：」
で始まる行)と、それ以降のラベル行(「品種：」「地区：」「精製方法：」
「標高：」)は構造化フィールドとして個別に抽出し、flavor_notesにはテイスティング
文(見出し+説明文)のみを採用する(酸味/コクの記号評価や産地スペックの重複を
避けるため)。div.spec_desc_storyBlock_txt(STORY見出し、農園背景の長文)が
存在する場合はflavor_notesに追記する。

【重量・価格について】
実データ確認済み: 重量はタイトル末尾の「200g」「1kg」表記から取得する(1kg=1000g
に変換)。価格はdiv.spec__price内の数字をそのまま採用する(バリアント選択による
価格変動は無く、豆/粉の挽き方選択のみ)。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    normalize_processing_method,
    detect_stock_status,
    detect_country_name,
)

SHOP_INFO = {
    "name": "OBSCURA COFFEE ROASTERS",
    "url": "https://obscura-coffee.com/",
    "platform": "独自EC(shop.obscura-coffee.com)",
    "address": "東京都世田谷区三軒茶屋1-36-10",
    "prefecture": "東京都",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://shop.obscura-coffee.com"
CATEGORY_URLS = [f"{BASE_URL}/product/list/4", f"{BASE_URL}/product/list/3"]
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["セット", "アソート"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]|(\d+)\s*kg", re.IGNORECASE)
STRIP_WEIGHT_PATTERN = re.compile(r"\s*(\d+\s*[gｇ]|\d+\s*kg)\s*", re.IGNORECASE)


def fetch(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_product_urls() -> list[str]:
    urls = []
    seen = set()
    for cat_url in CATEGORY_URLS:
        soup = fetch(cat_url)
        for a in soup.select('a[href*="/product/detail/"]'):
            href = a.get("href", "")
            m = re.search(r"/product/detail/(\d+)", href)
            if not m:
                continue
            url = f"{BASE_URL}/product/detail/{m.group(1)}"
            if url not in seen:
                seen.add(url)
                urls.append(url)
    return urls


def parse_weight_g(title: str) -> int | None:
    m = re.search(r"(\d+)\s*kg", title, re.IGNORECASE)
    if m:
        return int(m.group(1)) * 1000
    m = re.search(r"(\d+)\s*[gｇ]", title)
    return int(m.group(1)) if m else None


def dedupe_by_base_name(items: list[dict]) -> list[dict]:
    """理由はモジュールdocstring参照(200g/1kgの重複は最小重量のみ採用)。
    実データ確認済み: 同一銘柄でも1kg版/200g版でタイトル中の空白(全角/半角)の
    入り方が微妙に異なる(例:「ニャンジャファクトリー」1kgには直前スペース無し、
    200g版は直前に半角スペース有り)ため、重量除去後に全角・半角空白を含む
    空白文字を総て削除してから比較する。"""
    groups: dict[str, list[dict]] = {}
    for item in items:
        base = STRIP_WEIGHT_PATTERN.sub("", item["title"])
        base = re.sub(r"[\s　]+", "", base)
        groups.setdefault(base, []).append(item)

    result = []
    for base, group in groups.items():
        group.sort(key=lambda x: x["weight_g"] or float("inf"))
        result.append(group[0])
    return result


def parse_explain(soup: BeautifulSoup) -> tuple[dict, str | None]:
    body = soup.select_one("div.spec_desc_overviewBlock_left_body")
    headings = soup.select("h5.spec_desc_overviewBlock_left_heading")
    if not body:
        return {}, None

    text = body.get_text("\n", strip=True)
    lines = [l for l in text.split("\n") if l.strip()]

    labels = {}
    flavor_lines = []
    for line in lines:
        m = re.match(r"^(品種|地区|精製方法|標高)[：:]\s*(.+)$", line)
        if m:
            labels[m.group(1)] = m.group(2).strip()
            continue
        if re.match(r"^(酸味|コク)[：:]", line):
            continue
        flavor_lines.append(line)

    # 見出し(赤字の「※お得な1kg袋入りです」等の注記を除く、テイスティング
    # キャッチコピー)も先頭に加える
    heading_texts = [
        h.get_text(" ", strip=True) for h in headings
        if h.get_text(strip=True) and "袋入り" not in h.get_text(strip=True)
    ]

    story_el = soup.select_one("div.spec_desc_storyBlock_txt")
    story_text = story_el.get_text(strip=True) if story_el else None

    flavor_parts = heading_texts + flavor_lines
    if story_text:
        flavor_parts.append(story_text)
    flavor_notes = "\n".join(flavor_parts) if flavor_parts else None

    return labels, flavor_notes


def build_record(product_url: str) -> dict | None:
    soup = fetch(product_url)
    h1 = soup.select_one("h1")
    title = h1.get_text(strip=True) if h1 else None
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)

    price_el = soup.select_one(".spec__price")
    price = None
    if price_el:
        m = re.search(r"[\d,]+", price_el.get_text())
        if m:
            price = int(m.group().replace(",", ""))

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

    labels, flavor_notes = parse_explain(soup)

    origin_note = labels.get("地区")
    if origin_note:
        detected = detect_country_name(origin_note) or detect_country_name(title)
        if detected:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "product_description"
    parsed = apply_category_hint_fallback(parsed, title)

    processing_note = labels.get("精製方法")
    if processing_note:
        parsed["processing_method"] = normalize_processing_method(processing_note)

    variety = labels.get("品種")
    farm_note = f"標高{labels['標高']}" if labels.get("標高") else None

    weight_g = parse_weight_g(title)
    stock_status = detect_stock_status(title)

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
        "variety": variety,
        "flavor_notes": flavor_notes,
        "farm_note": farm_note,
        "post_processing_tags": parsed["post_processing_tags"],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_product_urls()

    # まず軽量にタイトル・重量だけ集め、200g/1kg重複を除去してから詳細を確定する
    prelim = []
    for url in product_urls:
        soup = fetch(url)
        h1 = soup.select_one("h1")
        title = h1.get_text(strip=True) if h1 else None
        if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
            continue
        prelim.append({"url": url, "title": title, "weight_g": parse_weight_g(title)})

    deduped = dedupe_by_base_name(prelim)

    records = []
    flavored_records = []
    for item in deduped:
        detail = build_record(item["url"])
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


def main():
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_obscuracoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_obscuracoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
