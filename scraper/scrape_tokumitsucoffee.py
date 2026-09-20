# -*- coding: utf-8 -*-
"""
scrape_tokumitsucoffee.py

徳光珈琲/TOKUMITSU COFFEE(store.tokumitsu-coffee.com、Shopify)の商品情報を
取得する。円山店・大通店・石狩店・銭函店・月寒西店の5店舗を展開する
多店舗チェーン(いずれも10店舗未満のため対象内)。

【住所について】
Shopifyストア側(store.tokumitsu-coffee.com)には特定商取引法ページ・会社概要
ページが見つからず、オンラインストアの/policies/legal-noticeも空欄
だった(2026-09確認)。別ドメインの公式サイト(tokumitsu-coffee.com/shop)の
「店舗情報」ページで実データ確認した5店舗のうち、石狩店(〒061-3202
石狩市花川南2条3丁目185番地、駐車場8台・週末のみ営業で焙煎工場を兼ねると
見られる)をロースタリー/本拠地として採用する(候補リストが挙げていた
5拠点のうち「石狩」に該当)。

【商品情報の取得方法について】
実データ確認済み: Shopify標準の/products.json(全175件)から取得する。
`product_type`タグが"roasttype-"で始まる商品(43件)のみが実際の焙煎豆
単品(シングルオリジン・ブレンド)で、それ以外(ギフトセット・アイス
コーヒー瓶・コーヒーゼリー・雑貨・珈琲教室等)は`product_type`が別の値
(空文字列や"0"等)のため、このタグで一次フィルタできる。

【対象商品についての除外】
実データ確認済み: roasttype-*タグが付く43件のうち、「ダンク式コーヒー
バッグ単品」9件(個包装ドリップバッグ、1袋のみの量り売りではない)と
「珈琲教室：基礎前半/後半セット」2件(体験講座であり商品ではない)を
NON_BEAN_KEYWORDSで除外し、残り32件が対象(BLEND #1〜#9の主力ブレンド9件
+ シングルオリジン各種)。

【重量について】
実データ確認済み: 「◯◯ 200g」のように商品名に明記されている場合はそこから
取得する。「BLEND #1」〜「BLEND #9」は商品名に重量表記が無いが、同一価格帯
(2,160円前後)の他の200g商品と価格水準が一致することを確認済みのため、
デフォルト200gを採用する。

robots.txt確認済み(2026-09時点): Shopify標準のUCPエージェント向け記述。
商品・カテゴリ・ページ等の公開HTMLはクロール可能。

【flavor_notes/farm_note(テイスティングノート・農園情報)について
(2026-09-20追記)】
実データ確認済み: body_htmlに、商品名から始まる短い風味の要約文(強調
タグ内の1文)に続けて数文の風味説明があり、単一原産地商品にはさらに
「生産国：.../地域：.../農園：.../農園主：.../品種：.../精製：.../
焙煎：...」の構造化ラベルが続く(<p>/<h3>/<h4>要素内、<br>で区切られる)。
末尾に「ご注文時のお願い」(豆/粉選択の注意書き)や「販売期間：」
(季節限定商品の販売期間)という定型の注意書きが必ず続くため、この
マーカーが現れた時点で本文を打ち切る。ブレンド商品はラベルが無く
風味説明のみ。p/h3/h4要素ごとにテキストを取り出し、ラベル行は
farm_note用フィールドとprocessing_methodに振り分け、それ以外の行を
flavor_notesとして採用する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status, normalize_processing_method

WHITESPACE_PATTERN = re.compile(r"[ \t]+")
DESC_LABEL_PATTERN = re.compile(r"^(生産国|地域|農園主|生産者|農園|品種|精製|焙煎)[：:]\s*(.*)$")
FARM_LABEL_TO_FIELD = {
    "生産国": "region_detail",
    "地域": "region_detail",
    "農園": "farm_name",
    "農園主": "producer_name",
    "生産者": "producer_name",
    "品種": "variety_note",
}
STOP_MARKERS = ("ご注文時のお願い", "販売期間")


def extract_flavor_and_farm(body_html: str | None) -> tuple[str | None, dict, str | None]:
    """理由はモジュールdocstring参照。"""
    if not body_html:
        return None, {}, None
    soup = BeautifulSoup(body_html, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")

    lines = []
    for el in soup.find_all(["p", "h3", "h4"]):
        for chunk in el.get_text().split("\n"):
            line = WHITESPACE_PATTERN.sub(" ", chunk).strip()
            if line:
                lines.append(line)

    farm: dict = {}
    processing_raw = None
    flavor_lines = []
    for line in lines:
        if any(line.startswith(marker) for marker in STOP_MARKERS):
            break
        m = DESC_LABEL_PATTERN.match(line)
        if m:
            label, value = m.group(1), m.group(2).strip()
            if not value:
                continue
            if label == "精製":
                processing_raw = value
            elif label == "焙煎":
                pass
            elif label in FARM_LABEL_TO_FIELD:
                field = FARM_LABEL_TO_FIELD[label]
                farm[field] = f"{farm[field]} {value}" if farm.get(field) else value
            continue
        flavor_lines.append(line)

    flavor_notes = "".join(flavor_lines).strip() or None
    return flavor_notes, farm, processing_raw

SHOP_INFO = {
    "name": "徳光珈琲",
    "url": "https://store.tokumitsu-coffee.com/",
    "platform": "Shopify",
    "address": "北海道石狩市花川南2条3丁目185番地",
    "prefecture": "北海道",
    "robots_txt_status": "許可(2026-09確認。Shopify標準の記述。商品・カテゴリ・"
                          "ページ等の公開HTMLはクロール可能)",
}

PRODUCTS_JSON_URL = "https://store.tokumitsu-coffee.com/products.json?limit=250"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 理由はモジュールdocstring参照
NON_BEAN_KEYWORDS = ["ダンク式コーヒーバッグ単品", "珈琲教室"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
DEFAULT_WEIGHT_G = 200


def fetch_products() -> list[dict]:
    resp = requests.get(PRODUCTS_JSON_URL, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json().get("products", [])


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    if not variants:
        return None
    return variants[0]


def build_record(product: dict) -> dict | None:
    title = (product.get("title") or "").strip()
    product_type = product.get("product_type") or ""
    if not title or not product_type.startswith("roasttype-"):
        return None
    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)
    product_url = f"https://store.tokumitsu-coffee.com/products/{product.get('handle')}"

    variants = product.get("variants") or []
    variant = pick_canonical_variant(variants)
    price = int(float(variant["price"])) if variant and variant.get("price") is not None else None

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

    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else DEFAULT_WEIGHT_G
    all_out_of_stock = bool(variants) and not any(v.get("available") for v in variants)
    stock_status = detect_stock_status(title, all_out_of_stock)

    flavor_notes, farm, processing_raw = extract_flavor_and_farm(product.get("body_html"))

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"] or normalize_processing_method(processing_raw),
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "farm_name": farm.get("farm_name"),
        "producer_name": farm.get("producer_name"),
        "region_detail": farm.get("region_detail"),
        "variety_note": farm.get("variety_note"),
        "flavor_notes": flavor_notes,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    products = fetch_products()

    records = []
    flavored_records = []
    for product in products:
        detail = build_record(product)
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
    with open("data_tokumitsucoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_tokumitsucoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
