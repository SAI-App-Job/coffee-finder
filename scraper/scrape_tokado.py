# -*- coding: utf-8 -*-
"""
scrape_tokado.py

豆香洞コーヒー(TOKADO COFFEE、tokado-coffee.shop-pro.jp、〒816-0943
福岡県大野城市白木原3-3-1、2013年ジャパンカップテイスターズ選手権優勝の
自家焙煎豆専門店)の商品情報を取得する。カラーミーショップ(shop-pro.jp)。

【住所について】
特定商取引法ページ(https://tokado-coffee.shop-pro.jp/?mode=sk)で
「816-0943 福岡県大野城市白木原３丁目３−１」を確認済み(2026-09時点、
EUC-JPで直接デコードして確認。WebFetch経由だと文字化けする)。

【文字コードについて】
実データ確認済み: Content-Type: text/html; charset=EUC-JP。

【テーマについて】
実データ確認済み: `li.product-list__unit`テーマ(倉敷珈琲館/アースベリー
コーヒーと同系統)。一覧ページの時点で商品名(a.product-list__name)・
価格(span.product-list__price、税込)が静的HTMLで直接出力されているため、
詳細ページへの個別アクセスは行わない。

【非コーヒー豆商品の除外について】
実データ確認済み: カフェオレベース(2本セット等)・ドリップバッグ(ギフト
箱含む)・コーヒー器具・ようかんとのギフトセットが非対象。
NON_BEAN_KEYWORDSで除外する。

【重量について】
実データ確認済み: 商品名に【200g】のように角括弧で重量が明記されている。
同一銘柄の重量違い(【200g】と【3種 大袋】等の増量パック)は商品名が
完全には一致しないため重複排除は行わず、角括弧内が数値+gの場合のみ
weight_gとして採用する。

robots.txt確認済み(2026-09時点): shop-pro.jp標準の記述で、本スクレイパーが
使う一覧・詳細ページ(?mode=srh, ?pid=)は制限対象外。

【flavor_notes・farm_note構成要素について(2026-09-19追記)】
上記の理由で詳細ページへの個別アクセスを行っていなかったが、実データ確認
(3商品)の結果、div.product__explain内に商品によって異なる2種類の
構造化コンテンツが存在することが判明した: (a)「【焙煎人のテイスティング
ノート】」という明示的な見出しに続くカッピングコメント、(b)「*味わいの
特徴：」という見出しに続く風味描写、さらにその後に「【DATA】」見出しで
「農園：/品種：/エリア：/標高：/精製：」のラベル：値が続く商品もある(COE
ロット等の上位商品)。星評価の行(「香り　★★★★★★☆☆」等)はいずれの
見出しの後にも続くことがあるため、風味描写の終端シグナルとして使う。
3商品目のように在庫サービスパック等、どちらの見出しも無い商品は
flavor_notesを取得しない(誤って保管方法の説明等を風味描写として扱わない
ため)。詳細ページの個別取得(97商品、キャッシュ機構が無いため毎回)という
コスト増を伴うが、本プロジェクトの他の同規模店舗でも同様の毎回詳細取得を
行っており許容範囲と判断した。
"""

import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status, normalize_processing_method

SHOP_INFO = {
    "name": "豆香洞コーヒー",
    "url": "https://tokado-coffee.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "福岡県大野城市白木原3-3-1",
    "prefecture": "福岡県",
    "robots_txt_status": "実質許可(2026-09確認。shop-pro.jp標準のrobots.txtで、"
                          "本スクレイパーが使う一覧・詳細ページは制限対象外)",
}

BASE_URL = "https://tokado-coffee.shop-pro.jp"
LIST_BASE_URL = "https://tokado-coffee.shop-pro.jp/?mode=srh&keyword=&sort=n"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "カフェオレベース", "ドリップバッグ", "ギフト", "コーヒー器具", "ようかん",
    "水出しコーヒーバッグ", "羊羹", "共著",  # 共著: 焙煎解説書籍『All About Roasting』を除外
]
PRICE_PATTERN = re.compile(r"([\d,]+)\s*円")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
TOTAL_COUNT_PATTERN = re.compile(r"全\s*(\d+)\s*商品")
ITEMS_PER_PAGE = 12  # 実データ確認済み(2026-09時点。「全117商品 1-12表示」)
CRAWL_DELAY_SECONDS = 1

# 理由はモジュールdocstring参照
TASTING_NOTE_HEADING_PATTERN = re.compile(r"【焙煎人のテイスティングノート】")
FLAVOR_CHARACTERISTIC_PATTERN = re.compile(r"^\*?\s*味わいの特徴[：:]\s*(.*)$")
STAR_RATING_LINE_PATTERN = re.compile(r"^(香り|酸味|苦味|甘味|ボディ)\s*★")
DATA_HEADING_PATTERN = re.compile(r"【DATA】")
DISCLAIMER_LINE_PATTERN = re.compile(r"^※")
DATA_LABEL_PATTERN = re.compile(r"^([^:：\n]{1,6})[：:]\s*(.+)$")
DATA_LABEL_TO_FIELD = {
    "農園": "farm_name",
    "品種": "variety_note",
    "エリア": "region_detail",
    "標高": "altitude_note",
    "精製": "processing_method",
}


def parse_flavor_and_farm(soup: BeautifulSoup) -> tuple[str | None, dict]:
    """理由はモジュールdocstring参照。"""
    el = soup.select_one("div.product__explain")
    if not el:
        return None, {}
    lines = [line.strip() for line in el.get_text(separator="\n").split("\n") if line.strip()]

    flavor_notes = None
    heading_idx = next((i for i, l in enumerate(lines) if TASTING_NOTE_HEADING_PATTERN.search(l)), None)
    if heading_idx is None:
        heading_idx = next((i for i, l in enumerate(lines) if FLAVOR_CHARACTERISTIC_PATTERN.match(l)), None)
        lead_match = FLAVOR_CHARACTERISTIC_PATTERN.match(lines[heading_idx]) if heading_idx is not None else None
        content = [lead_match.group(1)] if lead_match and lead_match.group(1) else []
        start = heading_idx + 1 if heading_idx is not None else None
    else:
        content = []
        start = heading_idx + 1

    if start is not None:
        for line in lines[start:]:
            if DATA_HEADING_PATTERN.search(line) or STAR_RATING_LINE_PATTERN.match(line):
                break
            if DISCLAIMER_LINE_PATTERN.match(line):
                continue
            content.append(line)
        flavor_notes = "".join(content) or None

    fields: dict[str, str] = {}
    data_idx = next((i for i, l in enumerate(lines) if DATA_HEADING_PATTERN.search(l)), None)
    if data_idx is not None:
        for line in lines[data_idx + 1:]:
            if line.startswith("【"):
                break
            m = DATA_LABEL_PATTERN.match(line)
            if not m:
                continue
            label = "".join(m.group(1).split())
            field = DATA_LABEL_TO_FIELD.get(label)
            if field:
                fields.setdefault(field, m.group(2).strip())

    return flavor_notes, fields


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return BeautifulSoup(resp.text, "html.parser")


def scrape_list_page(page: int) -> tuple[list[dict], int | None]:
    url = LIST_BASE_URL if page == 1 else f"{LIST_BASE_URL}&page={page}"
    soup = fetch_page(url)

    total_count = None
    m = TOTAL_COUNT_PATTERN.search(soup.get_text())
    if m:
        total_count = int(m.group(1))

    items = []
    for li in soup.select("li.product-list__unit"):
        name_el = li.select_one("a.product-list__name")
        link_el = li.select_one('a[href^="?pid="]')
        if not name_el or not link_el:
            continue
        title = name_el.get_text(strip=True)
        if any(kw in title for kw in NON_BEAN_KEYWORDS):
            continue
        price = None
        price_el = li.select_one("span.product-list__price")
        if price_el:
            m = PRICE_PATTERN.search(price_el.get_text())
            if m:
                price = int(m.group(1).replace(",", ""))
        items.append({
            "raw_name": title,
            "product_url": BASE_URL + "/" + link_el["href"],
            "price": price,
        })
    return items, total_count


def build_record(item: dict) -> dict | None:
    title = item["raw_name"]
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": item["price"],
            "product_url": item["product_url"],
        }

    if not parsed.get("origin_country") and parsed.get("category") != "ブレンド":
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "non_bean": True,
            "product_url": item["product_url"],
        }

    stock_status = detect_stock_status(title)
    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None

    flavor_notes, desc_fields = parse_flavor_and_farm(fetch_page(item["product_url"]))
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
        "farm_name": desc_fields.get("farm_name"),
        "region_detail": desc_fields.get("region_detail"),
        "altitude_note": desc_fields.get("altitude_note"),
        "variety_note": desc_fields.get("variety_note"),
        "blend_components": [],
        "flavor_notes": flavor_notes,
        "price": item["price"],
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["product_url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    all_items = []
    seen_urls = set()
    page = 1
    max_pages = 1
    while page <= max_pages:
        items, total_count = scrape_list_page(page)
        if total_count:
            import math
            max_pages = max(max_pages, math.ceil(total_count / ITEMS_PER_PAGE))
        new_items = []
        for i in items:
            if i["product_url"] in seen_urls:
                continue
            seen_urls.add(i["product_url"])
            new_items.append(i)
        if not new_items:
            break
        all_items.extend(new_items)
        page += 1

    records = []
    flavored_records = []
    non_bean_records = []
    for item in all_items:
        detail = build_record(item)
        time.sleep(CRAWL_DELAY_SECONDS)
        if detail is None:
            continue
        if detail.get("non_bean"):
            non_bean_records.append(detail)
        elif detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records, non_bean_records


if __name__ == "__main__":
    import json

    records, flavored_records, non_bean_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
        "non_bean_products_excluded": non_bean_records,
    }
    with open("data_tokado.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_tokado.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件、"
          f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
