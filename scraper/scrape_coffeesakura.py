# -*- coding: utf-8 -*-
"""
scrape_coffeesakura.py

コーヒーサクラ(shop.coffeesakura.co.jp、愛知県瀬戸市内田町2-76、自家焙煎豆
のオンライン販売)の商品情報を取得する。Shopify(/products.json全件取得
方式)。

robots.txt確認済み(2026-09時点): Shopify標準のrobots.txtでAllow: /
(AIエージェント向けagents.md/UCPエンドポイントの案内を含む標準
テンプレート)。制限なし。

【product_typeによるフィルタについて】
実データ確認済み: 全163商品中、product_type="コーヒー豆"の42件が対象。
"コーヒーミル"(11)・"ドリップバッグ"(11)・"生豆"(12、未焙煎の生豆)・
"ギフト"(4)・"ドリップポット"(1)は非対象。またproduct_typeが空欄(82件)
の中に、器具・フィルター・生豆保存缶・抹茶・チラシ等の非対象商品に
混じって焙煎豆単品が2件だけ存在する(「台湾コーヒー豆40g」「台湾産
92向陽高山農園コーヒー豆」、いずれもタグ・product_type未設定のまま
登録されたと見られる)。この2件は商品名を個別に指定して追加対象とする
(EXTRA_BEAN_TITLES)。

【非コーヒー豆商品の除外について】
実データ確認済み: product_type="コーヒー豆"の42件のうち「店長おすすめ
コーヒー豆セット5種類計1000ｇ」「【メール便送料込】　コーヒー豆お試し
セット　5種類×60g計300g」の2件は複数銘柄の詰め合わせセットのため
NON_BEAN_KEYWORDS("セット")で除外する。「インフューズドコーヒー豆
（ストロベリー）100g」はフレーバー(香料)を後付けした商品だが、
coffee_parserのフレーバー検出は「フレーバーコーヒー」等の文言一致のみで
「インフューズド」+括弧内フレーバー名という表記には反応しないため、
NON_BEAN_KEYWORDS("インフューズド")で個別に除外する。

【重量違いの重複について】
実データ確認済み: 大半の銘柄が100g版・200g版を別々のShopify商品として
登録している(バリアントではなく商品自体が別、例:「オータムブレンド
コーヒー豆　100ｇ」と「オータムブレンドコーヒー豆　200ｇ」)。商品名から
重量表記を除いた基準名でグルーピングし、最小重量を代表として採用する。

【重量・価格の取得について】
実データ確認済み: 大半の商品は同一商品内に挽き方違い(豆のまま/中挽き/
粗挽き/細挽き/エスプレッソ用等)のバリアントを持ち、価格・grams(重量)は
バリアント間で同一(例: オータムブレンドは全バリアントgrams=100・
price=680)。「豆のまま」バリアントを優先して代表として採用する。
例外として「台湾産　92向陽高山農園コーヒー豆」は商品名に重量が無く、
代わりにバリアント側(例:「2024年　200g」「2024年　100g」「2024年
50g」)に重量・価格違いが存在する。この商品はgramsフィールドが実データ
不備で全バリアント一律1000固定になっている(信頼できない)ため、grams
フィールドは使わずバリアントのタイトル文字列から重量を都度正規表現で
抽出し、最小重量のバリアントを代表として採用する。
"""

import re

import requests

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "コーヒーサクラ",
    "url": "https://shop.coffeesakura.co.jp/",
    "platform": "Shopify",
    "address": "愛知県瀬戸市内田町2-76",
    "prefecture": "愛知県",
    "robots_txt_status": "実質許可(2026-09確認。Shopify標準のrobots.txtでAllow: /、制限なし)",
}

PRODUCTS_JSON_URL = "https://shop.coffeesakura.co.jp/products.json?limit=250"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

TARGET_PRODUCT_TYPE = "コーヒー豆"
# 実データ確認済み: product_type・tagsが未設定のまま登録されている焙煎豆単品
# (docstring参照)。商品名で個別に拾う。
EXTRA_BEAN_TITLES = {"台湾コーヒー豆40g", "台湾産　92向陽高山農園コーヒー豆"}
NON_BEAN_KEYWORDS = ["セット", "インフューズド"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_products() -> list[dict]:
    resp = requests.get(PRODUCTS_JSON_URL, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json().get("products", [])


def pick_fixed_weight_variant(variants: list[dict]) -> dict | None:
    """商品名に重量が明記されているケース向け: 挽き方バリアントの中から
    「豆のまま」を優先して代表を選ぶ(価格・重量はバリアント間で同一)。"""
    if not variants:
        return None
    available = [v for v in variants if v.get("available")]
    pool = available or variants

    def is_whole_bean(v):
        title = v.get("title") or v.get("option1") or ""
        return "豆のまま" in title

    whole_bean = [v for v in pool if is_whole_bean(v)]
    return (whole_bean or pool)[0]


def pick_variable_weight_variant(variants: list[dict]) -> tuple[dict | None, int | None]:
    """商品名に重量が無く、バリアント側に重量違いがあるケース向け(台湾産
    92向陽高山農園コーヒー豆)。gramsフィールドは実データ不備のため使わず、
    バリアントのタイトル文字列から重量を抽出して最小重量を代表とする。"""
    if not variants:
        return None, None
    available = [v for v in variants if v.get("available")]
    pool = available or variants

    def weight_key(v):
        m = WEIGHT_PATTERN.search(v.get("title") or v.get("option1") or "")
        return int(m.group(1)) if m else float("inf")

    variant = min(pool, key=weight_key)
    weight = weight_key(variant)
    return variant, (weight if weight != float("inf") else None)


def build_group_key(title: str) -> str:
    key = WEIGHT_PATTERN.sub("", title)
    key = re.sub(r"[^\w一-龠ぁ-んァ-ヶー]+", "", key)
    return key.lower()


def build_record(product: dict) -> dict | None:
    title = (product.get("title") or "").strip()
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)
    product_url = f"https://shop.coffeesakura.co.jp/products/{product.get('handle')}"

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
    title_weight_m = WEIGHT_PATTERN.search(title)
    if title_weight_m:
        weight_g = int(title_weight_m.group(1))
        variant = pick_fixed_weight_variant(variants)
    else:
        variant, weight_g = pick_variable_weight_variant(variants)

    price = int(float(variant["price"])) if variant and variant.get("price") is not None else None
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


def pick_canonical_items(items: list[dict]) -> list[dict]:
    by_base_name: dict[str, dict] = {}
    for item in items:
        base_name = build_group_key(item["title"])

        def weight_of(it):
            m = WEIGHT_PATTERN.search(it["title"])
            return int(m.group(1)) if m else float("inf")

        existing = by_base_name.get(base_name)
        if existing is None or weight_of(item) < weight_of(existing):
            by_base_name[base_name] = item
    return list(by_base_name.values())


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    products = fetch_products()
    targets = [
        p for p in products
        if p.get("product_type") == TARGET_PRODUCT_TYPE or (p.get("title") or "").strip() in EXTRA_BEAN_TITLES
    ]
    canonical_products = pick_canonical_items(
        [{"title": (p.get("title") or "").strip(), "product": p} for p in targets]
    )

    records = []
    flavored_records = []
    for item in canonical_products:
        detail = build_record(item["product"])
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
    with open("data_coffeesakura.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeesakura.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
