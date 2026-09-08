# -*- coding: utf-8 -*-
"""
scrape_basecoffeeawaji.py

BASE COFFEE(basecoffee.net、兵庫県南あわじ市倭文長田224、自家焙煎豆の
オンライン販売)の商品情報を取得する。Shopify(/products.json全件取得
方式)。

【住所について】
候補リストでは「南あわじ市山和文長224」だったが、公式サイトの特定商
取引法ページ(https://basecoffee.net/policies/legal-notice)で実際に
確認したところ「〒656-0152 兵庫県南あわじ市倭文長田224」であることを
確認したため、こちらを正としている。

【店名について】
候補リストの注記どおり「BASE COFFEE」という店名だがBASEプラットフォーム
とは無関係で、実データ確認の結果Shopifyで運営されていることを確認した。
同名の別会社(愛知県一宮市、basecoffeeclassic.com)がすでに
scrape_basecoffeeclassic.pyとして実装済みのため、本ファイルはファイル名を
basecoffeeawaji(淡路島)として区別する。

robots.txt確認済み(2026-09時点): Shopify標準のrobots.txtでAllow: /
(AIエージェント向けagents.md/UCPエンドポイントの案内を含む標準
テンプレート)。制限なし。

【非コーヒー豆商品の除外について】
実データ確認済み: 全74商品のうち、ふくワッフル各種・ワッフルラスク各種
(菓子)・アイスコーヒーセット/ギフト(瓶入り完成品セット)・カフェラテ
ベース(無糖リキッド)・自家焙煎アイスコーヒー(リキッドコーヒー、瓶入り
完成品)・カップオン珈琲各種(個包装ドリップ、銘柄別・セット問わず全て)・
季節のお薦め珈琲定期便(銘柄非依存のサブスク)・ギフト用紙袋/ふくろう
クッション等雑貨・コーヒーマイスターおすすめ6種/酸味好き3種セット/
苦味好き3種セット/BASE COFFEE人気3種セット/おすすめ珈琲セット(複数銘柄
詰め合わせ)が非対象。NON_BEAN_KEYWORDSで除外する。残り33件
(11銘柄×100g/250g/500gの3サイズ)を対象とする。

【重量違いの重複について】
実データ確認済み: 各銘柄が100g/250g/500gの3サイズでそれぞれ独立した
商品として登録されている(Shopifyのバリアントではなく別商品)。バリアント
は挽き方(豆のまま/粉・ペーパーフィルター用/粉・その他)のみで、価格は
挽き方に依らず同一。商品名から末尾の重量を除いた基準名でグルーピングし、
最小重量(100g)を代表として採用する(亀山珈琲焙煎所と同じ方式)。
"""

import re

import requests

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "BASE COFFEE（南あわじ市）",
    "url": "https://basecoffee.net/",
    "platform": "Shopify",
    "address": "兵庫県南あわじ市倭文長田224",
    "prefecture": "兵庫県",
    "robots_txt_status": "実質許可(2026-09確認。Shopify標準のrobots.txtでAllow: /、制限なし)",
}

PRODUCTS_JSON_URL = "https://basecoffee.net/products.json?limit=250"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "ふくワッフル", "ワッフルラスク", "セット", "カフェラテベース",
    "リキッドコーヒー", "カップオン珈琲", "定期便", "雑貨", "おすすめ",
]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_products() -> list[dict]:
    resp = requests.get(PRODUCTS_JSON_URL, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json().get("products", [])


def normalize_base_name(title: str) -> str:
    base = WEIGHT_PATTERN.sub("", title)
    return re.sub(r"\s+", " ", base).strip()


def pick_canonical_products(products: list[dict]) -> list[dict]:
    by_base_name: dict[str, tuple[int, dict]] = {}
    for product in products:
        title = (product.get("title") or "").strip()
        weight_matches = WEIGHT_PATTERN.findall(title)
        weight_key = int(weight_matches[-1]) if weight_matches else float("inf")
        base = normalize_base_name(title)
        existing = by_base_name.get(base)
        if existing is None or weight_key < existing[0]:
            by_base_name[base] = (weight_key, product)
    return [product for _weight, product in by_base_name.values()]


def build_record(product: dict) -> dict | None:
    title = (product.get("title") or "").strip()
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)
    product_url = f"https://basecoffee.net/products/{product.get('handle')}"

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
    price = int(float(variants[0]["price"])) if variants and variants[0].get("price") is not None else None
    weight_matches = WEIGHT_PATTERN.findall(title)
    weight_g = int(weight_matches[-1]) if weight_matches else None

    all_out_of_stock = bool(variants) and not any(v.get("available") for v in variants)
    stock_status = detect_stock_status(title, all_out_of_stock)

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
    filtered = [
        p for p in products
        if not any(kw in (p.get("title") or "") for kw in NON_BEAN_KEYWORDS)
    ]
    canonical_products = pick_canonical_products(filtered)

    records = []
    flavored_records = []
    for product in canonical_products:
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
    with open("data_basecoffeeawaji.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_basecoffeeawaji.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
