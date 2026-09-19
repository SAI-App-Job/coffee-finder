# -*- coding: utf-8 -*-
"""
scrape_eureka.py

Eureka Coffee Roasters(www.eureka-coffee.net、千葉県千葉市稲毛区緑町
1-8-16、2015年開業)の商品情報を取得する。Shopify(/products.json全件
取得方式)。裸ドメインはSSL証明書エラーのため「www.」付きでアクセスする。

robots.txt確認済み(2026-09時点): Shopify標準のrobots.txtで
"Public product, collection, page, blog, policy, cart, and localized
HTML is crawlable"と明記。制限なし。

【product_typeによるフィルタについて】
実データ確認済み: 全44商品中、product_type="コーヒー"の42件が対象。
"コーラ"(1件)・空文字列(1件、コーヒーサブスク)は対象外。

【豆のまま/挽き方バリエーションについて】
実データ確認済み: 各商品のバリエーションは「重量(100g等)」×
「挽き方(豆のまま/細挽き/中挽き等)」の組み合わせで価格は同額。
variantのgramsフィールドが常に0のため、variant.titleから正規表現で
重量を抽出する(option1/option2のどちらに重量が入るかは店舗により
順序が異なるため、title全体を対象にする)。

【flavor_notes/farm_note(テイスティングノート・農園情報)について
(2026-09-20追記)】
実データ確認済み(対象39商品全件): body_html(商品説明)を一切読んでいな
かった。2種類のテンプレートが混在する:
(1)旧形式(22件、単一原産国商品の大半): 冒頭の風味紹介文の後に
   「原産国：」「農園：」「標高：」「精製方法：」「品種：」の
   ラベル行が続く(1つの<p>に<br>で複数ラベルが連結されている商品
   もある、例: デカフェ商品)。
(2)新形式(3件、一部のブレンド): 冒頭にキャッチ文+説明文の2つの<p>、
   続いて<h3>見出し+<ul><li><strong>ラベル：</strong>値</li></ul>で
   ラベル情報を提供。
両形式とも、ラベル行より前の自由文をflavor_notesとして採用し、
「農園」「標高」「品種」ラベルをfarm_note用フィールドに、「精製方法」
ラベルをprocessing_methodに反映する(値が"MIX"や空の場合は採用しない
=ブレンド商品で原産国が複数国のため精製方法/品種も未確定であることを
示す値であり、情報として無意味なため)。「原産国」ラベル自体は
起点判定用のマーカーとしてのみ使い、既にtitleから取得しているため
専用フィールドには格納しない。ラベルが無いブレンドのドリップバッグ
商品(西千葉ブレンド等)も、「※」や重量価格行より前の自由文を同様に
flavor_notesとして採用する。
"""

import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status, normalize_processing_method
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "Eureka Coffee Roasters",
    "url": "https://www.eureka-coffee.net/",
    "platform": "Shopify",
    "address": "千葉県千葉市稲毛区緑町1-8-16",
    "prefecture": "千葉県",
    "robots_txt_status": "実質許可(2026-09確認。Shopify標準のrobots.txtでAllow: /、制限なし)",
}

PRODUCTS_JSON_URL = "https://www.eureka-coffee.net/products.json?limit=250"
CRAWL_DELAY_SECONDS = 1.0
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

TARGET_PRODUCT_TYPE = "コーヒー"
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_products() -> list[dict]:
    resp = requests.get(PRODUCTS_JSON_URL, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json().get("products", [])


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    if not variants:
        return None
    whole_bean = [v for v in variants if "豆のまま" in (v.get("title") or "")]
    pool = whole_bean or variants
    available = [v for v in pool if v.get("available")]
    final_pool = available or pool

    def weight_key(v):
        m = WEIGHT_PATTERN.search(v.get("title") or "")
        return int(m.group(1)) if m else float("inf")

    return min(final_pool, key=weight_key)


DESC_LABEL_PATTERN = re.compile(r"^([^:：\n]{1,10})[：:]\s*(.*)$")
FARM_LABEL_TO_FIELD = {
    "農園": "farm_name",
    "標高": "altitude_note",
    "品種": "variety_note",
}
DESC_GENERIC_STOP_PATTERN = re.compile(r"^(※|価格はすべて|送料|豆のまま|・ドリップバッグ|\d)")
# 実データ確認済み: 「グアテマラ ／カラウテ農園」に、店舗側の入力ミスと見られる
# 日本語を含まない文字列のみの<p>(例:"X,/6-b(Ue~z|")が本文冒頭に混入していた。
# 日本語(かな/カナ/漢字)を含まない行は風味紹介文として採用しない。
JAPANESE_CHAR_PATTERN = re.compile(r"[぀-ヿ一-鿿]")


def parse_description_details(body_html: str) -> tuple[str | None, dict, str | None]:
    """理由はモジュールdocstring参照。flavor_notes・farm情報・精製方法(生値)を返す。"""
    if not body_html:
        return None, {}, None
    soup = BeautifulSoup(body_html, "html.parser")
    flavor_lines = []
    farm: dict = {}
    processing_raw = None
    collecting_flavor = True
    for el in soup.find_all(["p", "li"]):
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
                    if value and value != "MIX":
                        farm[FARM_LABEL_TO_FIELD[label]] = value
                    continue
                if label == "精製方法":
                    collecting_flavor = False
                    if value and value != "MIX":
                        processing_raw = value
                    continue
                if label == "原産国":
                    collecting_flavor = False
                    continue
            if DESC_GENERIC_STOP_PATTERN.match(line):
                collecting_flavor = False
                continue
            if collecting_flavor and JAPANESE_CHAR_PATTERN.search(line):
                flavor_lines.append(line)
    flavor_notes = "".join(flavor_lines) or None
    return flavor_notes, farm, processing_raw


DECAF_KEYWORDS = ("カフェインレス", "デカフェ", "decaf")
DECAF_PROCESS_NAME_PATTERN = re.compile(
    r"(マウンテンウォーター(?:プロセス)?|スイスウォーター(?:プロセス|方式)?|"
    r"液体(?:CO2|二酸化炭素)|エチルアセテート|ウォータープロセス)"
)


def detect_decaf_process(title: str, processing_raw: str | None) -> str | None:
    """理由はモジュールdocstring参照。「精製方法」ラベルがデカフェ商品では
    カフェイン除去方法を指すため、processing_methodには使わずここに転用する。"""
    if not any(kw in title.lower() for kw in DECAF_KEYWORDS):
        return None
    m = DECAF_PROCESS_NAME_PATTERN.search(processing_raw or "")
    if m:
        return f"{m.group(1)}によりカフェインを除去"
    return "デカフェ(除去方法の詳細記載なし)"


def build_record(product: dict) -> dict | None:
    title = (product.get("title") or "").strip()
    if not title:
        return None

    parsed = parse_product(title)
    product_url = f"https://www.eureka-coffee.net/products/{product.get('handle')}"

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": None,
            "product_url": product_url,
        }

    variants = product.get("variants") or []
    variant = pick_canonical_variant(variants)
    price = int(float(variant["price"])) if variant and variant.get("price") is not None else None
    weight_g = None
    if variant:
        m = WEIGHT_PATTERN.search(variant.get("title") or "")
        if m:
            weight_g = int(m.group(1))

    all_out_of_stock = bool(variants) and not any(v.get("available") for v in variants)
    stock_status = detect_stock_status(title, all_out_of_stock)

    flavor_notes, farm, processing_raw = parse_description_details(product.get("body_html"))
    decaf_process = detect_decaf_process(title, processing_raw)
    processing_method = parsed["processing_method"] if decaf_process else (
        parsed["processing_method"] or normalize_processing_method(processing_raw)
    )

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
        "blend_components": [],
        "farm_name": farm.get("farm_name"),
        "altitude_note": farm.get("altitude_note"),
        "variety_note": farm.get("variety_note"),
        "flavor_notes": flavor_notes,
        "decaf_process": decaf_process,
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    products = fetch_products()
    targets = [p for p in products if p.get("product_type") == TARGET_PRODUCT_TYPE]
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for product in targets:
        product_url = f"https://www.eureka-coffee.net/products/{product.get('handle')}"
        title = (product.get("title") or "").strip()
        prev = previous.get(product_url)
        if is_unchanged(prev, raw_name=title):
            records.append(prev)
            continue

        detail = build_record(product)
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)
        time.sleep(CRAWL_DELAY_SECONDS)

    return records, flavored_records


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) > 1:
        products = fetch_products()
        match = next((p for p in products if p.get("handle") == sys.argv[1]), None)
        print(json.dumps(build_record(match) if match else None, ensure_ascii=False, indent=2))
    else:
        records, flavored_records = scrape_all_products()
        output = {
            "shop": SHOP_INFO,
            "products": records,
            "flavored_products_excluded": flavored_records,
        }
        with open("data_eureka.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_eureka.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
