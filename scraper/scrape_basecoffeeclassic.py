# -*- coding: utf-8 -*-
"""
scrape_basecoffeeclassic.py

BASE COFFEE(basecoffeeclassic.com、愛知県一宮市印田通4-24、自家焙煎豆の
オンライン販売)の商品情報を取得する。Shopify(/products.json全件取得
方式)。

【店名・ドメインについて】
候補リストでは「shop.basecoffee.jp」「basecoffeeclassic.com」
「basecoffee.jp」の3ドメインが挙がっていたが、実データ確認の結果、
shop.basecoffee.jpはロリポップの404エラーページを返す非稼働ドメインで
あり、実際に稼働しているオンラインストアはbasecoffeeclassic.com
(Shopify)のみであることを確認した。「BASE COFFEE」というブランド名は
BASEプラットフォームとは無関係の店名(偶然の一致)であり、実際は
Shopifyで運営されている。basecoffee.jp(WordPress)は別サイト(会社概要等)
の可能性が高く、本スクレイパーでは対象としない。

robots.txt確認済み(2026-09時点): Shopify標準のrobots.txtでAllow: /
(AIエージェント向けagents.md/UCPエンドポイントの案内を含む標準
テンプレート)。制限なし。

【非コーヒー豆商品の除外について】
実データ確認済み: 全72商品のうち、ドリップバッグ(単品10個入り各種+
ギフトセット)・定期便(コーヒー豆300g/600g/1200g定期便、銘柄非依存の
サブスクプランのため対象外)・ギフト各種(おまかせギフトセット・
カフェオレベース3本セット等)・HARIO/メリタ製の器具・プラナチャイ・
オリジナルキャニスター缶・アメリカンプレス・無糖リキッドアイスコーヒー
(瓶入り完成品)・15ヵ国セット/アソートセット/飲み比べセット等の複数銘柄
詰め合わせ・「STANDART」(コーヒー文化系海外雑誌、重量バリエーションが
無くDefault Title単一バリアントのみで他の豆商品と構造が異なることを
確認済み)が非対象。NON_BEAN_KEYWORDSで除外する。残り約13件(ストレート・
ブレンド・デカフェ・アイスブレンド)を対象とする。

【重量バリエーションについて】
実データ確認済み: 各銘柄は250g/500g/750g/1000gの重量×豆のまま/挽き方の
組み合わせバリアントを持つが、variants.gramsは全て0固定(信頼できない、
バタリーコーヒーと同じ現象)。バリアントのtitle文字列(例:「250g / 豆」)
から正規表現で重量を抽出し、「豆」を含むバリアントを優先して代表を選ぶ。

【業務用コーヒー機器の混入について(2026-09-19追記)】
実データ再確認の結果、上記【非コーヒー豆商品の除外について】は本スクレイパー
実装当時(全72件)のスナップショットに基づく記述で、その後this店舗が
BONMAC・BUNN・Franke・Egro・Dr.Coffee・カフィテス等の業務用コーヒー機器
(グラインダー・エスプレッソマシン・サイフォン・ペーパーフィルター等)を
大量に取り扱うようになっており、現在は/products.json(250件)の大半(212件)が
これらの機器であることが判明した。機器のタイトルは銘柄名がブランド名の
数だけ存在し、キーワードの列挙では網羅できないため、Shopifyのproduct_type
フィールドで判定する(実データ確認済み: 機器は例外なくグラインダー/
セミオートエスプレッソマシン/ペーパーフィルター/全自動エスプレッソマシン/
コーヒー関連器具/その他周辺機器/洗浄剤/ブルーワー/デカンタ・サーバー/
オートタンパー/アンダーカウンター/焙煎機/カフィテス/全自動ドリップ式
コーヒーマシン/サイフォン/オートスチーマーのいずれかに分類されており、
豆商品は全件product_type未設定(空文字列)。EQUIPMENT_PRODUCT_TYPESに
一致する場合は非コーヒー豆として除外する)。

【flavor_notes(2026-09-21追記)】
実データ確認済み: body_htmlの先頭に商品固有のテイスティング文・産地/
ブレンドコンセプトの説明が入っており(対象12件全て確認)、その後に
必ず「<焙煎度名>ロースト（<roast> roast）<焙煎度カテゴリ>コーヒー」
という見出し(例:「ライトロースト（light roast）中煎りコーヒー」)で
始まる、焙煎度合いごとの店舗共通の一般論・焙煎行程・品質管理に関する
定型文(複数の商品で同一焙煎度なら一字一句同じ文面)が続く。その手前
までを採用する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "BASE COFFEE",
    "url": "https://basecoffeeclassic.com/",
    "platform": "Shopify",
    "address": "愛知県一宮市印田通4-24",
    "prefecture": "愛知県",
    "robots_txt_status": "実質許可(2026-09確認。Shopify標準のrobots.txtでAllow: /、制限なし)",
}

PRODUCTS_JSON_URL = "https://basecoffeeclassic.com/products.json?limit=250"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "STANDART", "ドリップバッグ", "コーヒーバッグ", "ギフト", "定期便",
    "カフェオレベース", "キャニスター", "ハリオ", "メリタ", "プラナチャイ",
    "セット", "アメリカンプレス", "リキッドアイスコーヒー",
]
# 理由はモジュールdocstring参照(業務用コーヒー機器の混入)
EQUIPMENT_PRODUCT_TYPES = {
    "グラインダー", "セミオートエスプレッソマシン", "ペーパーフィルター",
    "全自動エスプレッソマシン", "コーヒー関連器具", "その他周辺機器", "洗浄剤",
    "ブルーワー", "デカンタ・サーバー", "オートタンパー", "アンダーカウンター",
    "焙煎機", "カフィテス", "全自動ドリップ式コーヒーマシン", "サイフォン",
    "オートスチーマー",
}
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
FLAVOR_STOP_PATTERN = re.compile(r"[\w一-龠ぁ-んァ-ヶー]*ロースト（[a-z]+\s*roast）")


def extract_flavor_notes(body_html: str | None) -> str | None:
    """理由はモジュールdocstring参照。"""
    soup = BeautifulSoup(body_html or "", "html.parser")
    text = soup.get_text(" ", strip=True)
    m = FLAVOR_STOP_PATTERN.search(text)
    if m:
        text = text[: m.start()]
    return text.strip() or None


def fetch_products() -> list[dict]:
    resp = requests.get(PRODUCTS_JSON_URL, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json().get("products", [])


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    if not variants:
        return None
    available = [v for v in variants if v.get("available")]
    pool = available or variants

    def weight_key(v):
        m = WEIGHT_PATTERN.search(v.get("title") or "")
        return int(m.group(1)) if m else float("inf")

    def is_whole_bean(v):
        title = v.get("title") or ""
        return "豆" in title and "粉" not in title

    whole_bean_pool = [v for v in pool if is_whole_bean(v)] or pool
    return min(whole_bean_pool, key=weight_key)


def build_record(product: dict) -> dict | None:
    title = (product.get("title") or "").strip()
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None
    if (product.get("product_type") or "") in EQUIPMENT_PRODUCT_TYPES:
        return None

    parsed = parse_product(title)
    product_url = f"https://basecoffeeclassic.com/products/{product.get('handle')}"

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
        weight_g = int(m.group(1)) if m else None

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
        "flavor_notes": extract_flavor_notes(product.get("body_html")),
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
    with open("data_basecoffeeclassic.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_basecoffeeclassic.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
