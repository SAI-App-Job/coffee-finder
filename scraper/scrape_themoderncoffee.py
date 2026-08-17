# -*- coding: utf-8 -*-
"""
scrape_themoderncoffee.py

THE MODERN COFFEE(themoderncoffee.jp、Shopify製)の商品情報を取得する。
神奈川県川崎市宮前区鷺沼の単独店舗。

scrape_fuglen.pyをテンプレートに実装しているが、以下の点が異なる(実データ
確認済み、2026-08時点):

【products.jsonのスコープ】
FUGLENは`/collections/coffeebeans/products.json`というコーヒー豆専用
コレクションを持つが、この店舗にはそのようなコレクションが見当たらず、
ルート直下の`/products.json`(全15商品)を使う。焼き物作家・山田睦美氏の
カップ類やドリッパー等の器具がコーヒー豆と混在しているため、除外ロジックが
必要(FUGLENには無かった処理)。

【非コーヒー豆の除外】
実データ確認済み: 各商品のtagsフィールドが、コーヒー豆には"beans"、器具には
"item"、山田睦美氏のカップ類には空配列[]と、店舗側で明示的に分類されている。
この構造化タグが最も確実なため、"beans"タグの有無で判定する(キーワード
推測より優先)。

【商品説明(body_html)の構造】
FUGLENのようなth/td形式の表ではなく、「【国】ブラジル【位置】...【標高】...
【品種】...【生産処理】...【生産者】...」という全角カギ括弧ラベルの
自由記述(<br>区切り)。「フレーバー：...」も別行で存在する。

【ブレンドの判定について】
ブレンド商品は商品名に文字通り"<ブレンド>"を含む(例:「[豆] <ブレンド>Fruity」)。
coffee_parser.pyのBLEND_KEYWORDS(「ブレンド」を含むかの部分一致判定)で
そのまま検出できるため、特別な処理は不要。

【価格・重量の扱い】
バリアントは「150g × 挽き方(Beans/Paper/Espresso)」の組み合わせ。珈琲丸・
Rhizomagと同様、variants[].gramsの値(全バリアント一律500)がoption1の
重量表記(150g等)と一致しない不具合が実データで確認されたため、option1の
テキストから重量を正規表現で取り出すことを優先する。挽かない「Beans」を
優先して代表バリアントに選ぶ。

robots.txt確認済み(2026年8月時点): 標準的なShopify robots.txt
(User-agent: * にAllow: /、/products.jsonへの制限なし)。fetch成功。
"""

import json
import re
import time
from datetime import datetime, timezone

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
    "name": "THE MODERN COFFEE",
    "url": "https://themoderncoffee.jp/",
    "platform": "Shopify(products.jsonエンドポイントを利用)",
    "address": "神奈川県川崎市宮前区鷺沼1-12-2 鷺沼ビラスズキ1F",
    "prefecture": "神奈川県",
    "robots_txt_status": "許可(2026-08確認。標準的なShopify robots.txt。User-agent:*にAllow:/、"
                          "/products.jsonへの制限なし)",
}

BASE_URL = "https://themoderncoffee.jp"
CRAWL_DELAY_SECONDS = 3
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 【国】【位置】【標高】【品種】【生産処理】【生産者】という全角カギ括弧ラベルの
# 自由記述(実データ確認済み)。値は次のラベルまたは改行まで。
DESC_LABEL_PATTERN = re.compile(r"【(国|位置|標高|品種|生産処理|生産者)】\s*([^\n]*)")
FLAVOR_PATTERN = re.compile(r"フレーバー[：:]\s*(.+)")
VARIANT_WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")


def fetch_products_page(page: int) -> list[dict]:
    url = f"{BASE_URL}/products.json"
    resp = requests.get(url, params={"limit": 250, "page": page}, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json().get("products", [])


def parse_body_fields(body_html: str) -> dict:
    """body_html(<br>を改行に置換済みのテキストで処理)から【国】等のラベルと
    フレーバー行を抽出する。ブレンド商品はこの形式のラベルを持たないため、
    その場合は空辞書が返る(実データ確認済み)。"""
    if not body_html:
        return {"labels": {}, "flavor_notes": None}
    soup = BeautifulSoup(body_html, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    text = soup.get_text()

    labels = {label: value.strip() for label, value in DESC_LABEL_PATTERN.findall(text) if value.strip()}
    flavor_m = FLAVOR_PATTERN.search(text)
    flavor_notes = flavor_m.group(1).strip() if flavor_m else None

    return {"labels": labels, "flavor_notes": flavor_notes}


def weight_from_variant(variant: dict | None) -> int | None:
    if not variant:
        return None
    m = VARIANT_WEIGHT_PATTERN.search(variant.get("option1") or variant.get("title") or "")
    if m:
        return int(m.group(1))
    # フォールバック: option1側から取れない場合のみgramsを信頼する
    grams = variant.get("grams")
    return grams if isinstance(grams, int) and grams > 0 else None


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    """重量×挽き方バリアントから代表の1件を選ぶ。挽かない「Beans（豆）」を
    優先し、無ければ在庫があるバリアント、それも無ければ全バリアント中
    最小重量のものを使う(珈琲丸のpick_canonical_variant()と同じ考え方)。"""
    if not variants:
        return None

    def weight_key(v):
        w = weight_from_variant(v)
        return w if w is not None else float("inf")

    whole_bean = [v for v in variants if "beans" in (v.get("option2") or "").lower() or "豆" in (v.get("option2") or "")]
    available = [v for v in variants if v.get("available")]
    pool = whole_bean or available or variants
    return min(pool, key=weight_key)


def build_record(product: dict) -> dict:
    title = product.get("title", "")
    product_url = f"{BASE_URL}/products/{product.get('handle')}"
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        variant = pick_canonical_variant(product.get("variants", []))
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": int(float(variant["price"])) if variant else None,
            "product_url": product_url,
        }

    fields = parse_body_fields(product.get("body_html", ""))
    labels = fields["labels"]

    # 【国】欄は商品名からのキーワード推測より確実なため優先する
    # (MiLL Coffee・PHILOCOFFEA・FUGLENの「説明文優先」方針を踏襲)。
    # ブレンド商品は【国】欄自体を持たないため、この分岐に入らずorigin_country=Noneのまま
    if labels.get("国"):
        country = detect_country_name(labels["国"])
        if country:
            parsed["origin_country"] = country
            parsed["origin_source"] = "product_description"
    parsed = apply_category_hint_fallback(parsed, None)

    if labels.get("生産処理"):
        parsed["processing_method"] = normalize_processing_method(labels["生産処理"])

    variant = pick_canonical_variant(product.get("variants", []))
    structural_out_of_stock = not any(v.get("available") for v in product.get("variants", []))
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
        "roast_level": parsed["roast_level"],  # サイト上に焙煎度の指定は見当たらず(取れないことが多い)
        "post_processing_tags": parsed["post_processing_tags"],
        "producer_name": labels.get("生産者"),
        "region_detail": labels.get("位置"),
        "altitude_note": labels.get("標高"),
        "variety": labels.get("品種"),
        "flavor_notes": fields["flavor_notes"],
        "blend_components": [],  # ブレンド商品(<ブレンド>)は産地別内訳を持たず未対応
        "price": int(float(variant["price"])) if variant else None,
        "weight_g": weight_from_variant(variant),
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def is_bean_product(product: dict) -> bool:
    """tagsフィールドに"beans"が含まれるかで、コーヒー豆かどうかを判定する。
    実データ確認済み: コーヒー豆は"beans"、器具は"item"、山田睦美氏のカップ類は
    空配列[]と店舗側で明示的にタグ分類されている(キーワード推測より確実)。"""
    tags = product.get("tags") or []
    return any(str(t).lower() == "beans" for t in tags)


def scrape_all_products() -> tuple[list[dict], list[dict], list[dict]]:
    all_raw = []
    page = 1
    while True:
        batch = fetch_products_page(page)
        if not batch:
            break
        all_raw.extend(batch)
        page += 1
        time.sleep(CRAWL_DELAY_SECONDS)

    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    non_bean_records = []
    for product in all_raw:
        product_url = f"{BASE_URL}/products/{product.get('handle')}"

        if not is_bean_product(product):
            non_bean_records.append({
                "shop_name": SHOP_INFO["name"],
                "raw_name": product.get("title", ""),
                "non_bean": True,
                "product_url": product_url,
            })
            continue

        variant = pick_canonical_variant(product.get("variants", []))
        current_price = int(float(variant["price"])) if variant else None
        current_out_of_stock = not any(v.get("available") for v in product.get("variants", []))

        prev = previous.get(product_url)
        if is_unchanged(
            prev,
            raw_name=product.get("title", ""),
            price=current_price,
            out_of_stock=current_out_of_stock,
        ):
            records.append(prev)
            continue

        record = build_record(product)
        if record.get("is_flavored"):
            flavored_records.append(record)
        else:
            records.append(record)

    return records, flavored_records, non_bean_records


def main():
    records, flavored_records, non_bean_records = scrape_all_products()

    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
        "non_bean_products_excluded": non_bean_records,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }

    with open("data_themoderncoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[done] {len(records)}件を data_themoderncoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件、"
          f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
