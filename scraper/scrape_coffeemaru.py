# -*- coding: utf-8 -*-
"""
scrape_coffeemaru.py

珈琲丸(coffee-maru.store、Shopify製)の商品情報を取得する。神奈川県川崎市
高津区(高津本店)の単独店舗。楽天市場・BASEにも出店しているが、自社Shopify
ストア(coffee-maru.store)のみを対象とする。

robots.txt確認済み(2026年8月時点): Shopify標準のUser-agent: * / Allow: /。
チェックアウト・アカウント・cart.js等の取引系エンドポイントのみDisallow。
/products.jsonへの制限記述なし。

【products.jsonエンドポイントについて】
FUGLENと違い、店舗固有の「coffeebeans」のような単一コレクションが見当たら
なかった(実データ確認済み: frontpage/カフェインレス/中煎り等、複数の小さな
コレクションに分散)。ルート直下の`/products.json`(コレクション指定なしの
全商品エンドポイント)を試したところ200 OKで返り、現時点(2026-08)で3商品
(いずれも単一産地のコーヒー豆、非コーヒー豆の商品は無し)というごく小規模な
店舗であることを確認済み。将来的に非コーヒー豆の商品が追加された場合の
除外ロジックは、実例が無い状態で作り込むと誤りうるため今回は見送っている。

【価格・重量の扱い】
バリアントは「重量(100g/200g等) × 挽き方(豆のまま/中挽き/粗挽き/細挽き)」の
組み合わせ。FUGLENと違い`variants[].grams`の値が実際の重量と一致しない
(例:「200g」バリアントなのにgrams:60等の入力ミスと見られる値が混在)ことが
実データで確認されたため、バリアントのtitle文字列(例:「100g（まずはこちらを）」)
から重量を正規表現で取り出すことを優先し、取れない場合のみgramsにフォール
バックする。「豆のまま」(挽かない状態)を優先し、その中で最小重量のものを
代表として採用する(FUGLENのpick_canonical_variant()と同じ考え方)。

【産地情報の扱い】
body_html内に「生産国　○○」のようにラベルと全角スペースで区切られた行が
含まれる商品がある一方、無い商品も実データで確認された(3商品中1商品のみ)。
その場合でも商品名(例:「ケニア マサイAA」「ルワンダ 走れ！ライオン」)に
産地国名が直接含まれているため、coffee_parser.pyの商品名パースで十分
対応できることを確認済み。
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
    "name": "珈琲丸",
    "url": "https://coffee-maru.store/",
    "platform": "Shopify(products.jsonエンドポイントを利用)",
    "address": "神奈川県川崎市高津区二子2-18-9 HOME194-C",
    "prefecture": "神奈川県",
    "robots_txt_status": "許可(2026-08確認。Shopify標準のUser-agent:*にAllow:/。/products.jsonへの制限記述なし)",
}

BASE_URL = "https://coffee-maru.store"
CRAWL_DELAY_SECONDS = 1  # robots.txt確認済み(2026-08時点): Crawl-delay指定なし。個人開発の反復スピード
# 優先だが、小規模個人店が多いためcourtesy設定(間隔を空けること自体)は維持する
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# body_html内の「ラベル　値」形式(コロンではなく全角スペース区切り)を抽出する。
# 実データ確認済みのラベル: 生産国/生産エリア/品種/精製方法/規格/煎り方
DESC_LABEL_PATTERN = re.compile(
    r"^\s*(生産国|生産エリア|品種|精製方法|規格|煎り方)[\s　]+(.+?)\s*$", re.MULTILINE
)

# バリアントのtitle文字列(例:「100g（まずはこちらを）」)から重量(g)を取り出す。
# variants[].gramsは実データ確認済みで信用できない値が混在していたため
# 優先的には使わない(下のpick_canonical_variant参照)。
VARIANT_WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")


def fetch_products_page(page: int) -> list[dict]:
    url = f"{BASE_URL}/products.json"
    resp = requests.get(url, params={"limit": 250, "page": page}, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json().get("products", [])


def parse_body_fields(body_html: str) -> dict:
    """body_html内の「生産国　○○」のような、ラベルと値を全角スペースで区切る
    表記から情報を抽出する。<p>タグごとに改行を挟んでから正規表現をかける
    (改行を挟まないと隣接する項目を巻き込む恐れがあるため、Denim bis実装時
    に経験した不具合と同じ対策)。全商品に必ず存在するわけではない
    (実データ確認済み: 3商品中1商品のみ)。
    """
    if not body_html:
        return {}
    soup = BeautifulSoup(body_html, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    paragraphs = [p.get_text() for p in soup.find_all("p")]
    text = "\n".join(paragraphs) if paragraphs else soup.get_text(separator="\n")

    raw = {}
    for m in DESC_LABEL_PATTERN.finditer(text):
        label, value = m.group(1), m.group(2).strip()
        if value:
            raw[label] = value
    return raw


def weight_from_variant(variant: dict | None) -> int | None:
    if not variant:
        return None
    m = VARIANT_WEIGHT_PATTERN.search(variant.get("title") or "")
    if m:
        return int(m.group(1))
    # フォールバック: title側から取れない場合のみgramsを信頼する
    grams = variant.get("grams")
    return grams if isinstance(grams, int) and grams > 0 else None


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    """複数の重量・挽き方バリアントの中から、代表として使う1件を選ぶ。
    「豆のまま」(挽かない状態)の中で最小重量のものを優先し、無ければ
    在庫があるバリアント、それも無ければ全バリアント中最小重量のものを使う。"""
    if not variants:
        return None

    def weight_key(v):
        w = weight_from_variant(v)
        return w if w is not None else float("inf")

    whole_bean = [v for v in variants if "豆のまま" in (v.get("title") or "")]
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

    # 商品説明の「生産国」表記は商品名からのキーワード推測より確実なため優先する
    # (MiLL Coffee・PHILOCOFFEA・FUGLENの「説明文優先」方針を踏襲)。
    # 説明文に無い場合(実データ確認済み: 3商品中2商品)は、商品名パースの
    # 結果(例:「ケニア マサイAA」→ケニア)をそのまま使う。
    if fields.get("生産国"):
        country = detect_country_name(fields["生産国"])
        if country:
            parsed["origin_country"] = country
            parsed["origin_source"] = "product_description"
    parsed = apply_category_hint_fallback(parsed, None)

    if fields.get("精製方法"):
        parsed["processing_method"] = normalize_processing_method(fields["精製方法"])

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
        "roast_level": parsed["roast_level"],  # 商品名からの8段階判定(取れないことが多い)
        "roast_hint": fields.get("煎り方"),  # 「浅煎り/中煎り/深煎り」の簡易表記(参考表示)
        "roast_selectable": False,
        "post_processing_tags": parsed["post_processing_tags"],
        "region_detail": fields.get("生産エリア"),
        "variety": fields.get("品種"),
        "grade_note": fields.get("規格"),
        "blend_components": [],  # 実データではブレンド商品の例が見つからず未対応
        "price": int(float(variant["price"])) if variant else None,
        "weight_g": weight_from_variant(variant),
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
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
    for product in all_raw:
        product_url = f"{BASE_URL}/products/{product.get('handle')}"
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

    return records, flavored_records


def main():
    records, flavored_records = scrape_all_products()

    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }

    with open("data_coffeemaru.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[done] {len(records)}件を data_coffeemaru.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
