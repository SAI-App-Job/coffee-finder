# -*- coding: utf-8 -*-
"""
scrape_flatwhite.py

FLAT WHITE COFFEE FACTORY(flatwhite.jp、宮城県・福島県に計11拠点を展開する
自家焙煎コーヒー専門店)の商品情報を取得する。Shopify。

【複数拠点について】
候補リストでは「6宮城+3福島」の情報だったが、実データ確認(2026-09時点、
/pages/shop-infoページ)では以下11拠点が確認できた。件数の食い違いは出店ペースの
変化によるものと考えられるため、伝聞ではなく実データの11拠点をそのまま採用する
(WOODBERRY COFFEEと同じ方針)。
  宮城県: flagship（泉店）・The Library U-TOMIYA（富谷市）・back alley（ダウンタウン店）・
  clickety-clacks（長町店）・architecture healings（荒井店）・departure express（仙台空港店）・
  EAGLES BEER & COFFEE（楽天モバイルパーク宮城）
  福島県: chill out（郡山店）・roasting works（三春店）・lakeside in the park（開成山公園）・
  oven bake（三春店）
実際の焙煎拠点(ロースタリー)は「flagship（泉店）」(〒981-3205 宮城県仙台市泉区
紫山1丁目1-4 紫山プラザ)であることをユーザーからの事前情報で確認済みのため、
is_headquartersはここに立てる。トップレベルのSHOP_INFOはプレフェクチャーレベルの
表記に留める(WOODBERRY COFFEE・PHILOCOFFEA等の複数拠点店舗と同じ方針)。

robots.txt確認済み(2026-09時点): 標準的なShopify robots.txt。/products/・
/collections/は User-agent: *に対しAllow。

【AIエージェント向け指示について】
robots.txtの先頭コメントに「エージェントはUCP/MCPエンドポイントやshop.appの
SKILLを使い、購入代行すべき」という趣旨の記述があったが、これはこのサイトの
コンテンツ(=信頼できない外部指示)であり、ユーザー自身の指示ではないため一切
従っていない。本スクレイパーは商品情報の読み取りのみを行う。

【対象コレクションについて】
実データ確認済み(2026-09時点): 「singleorigin」(32件)・「blendcoffee」(17件)・
「cafeless」(2件、デカフェ)の3コレクションに焙煎豆全ラインナップが収まっている
(bittercoffee/fruitycoffee/mildcoffee/afterlunch/morningcoffee等の風味・シーン別
コレクションは上記3つの部分集合のため重複を避けて使わない。premiumも同様に
singleorigin/blendcoffeeの部分集合)。

【除外商品について】
実データ確認済み: 各コレクションに「ドリップバッグ」形式の商品(商品名に
「ドリップバッグ」を含む、handleが「d」始まりのもの多数)・「コーヒー
ディスカバリーキット」(産地の異なる複数銘柄の少量詰め合わせ)・送料無料
ドリップバッグセットが混在しており、いずれも焙煎豆単品ではないため
キーワードで除外する。

【バリアントについて】
実データ確認済み: 「重量(100g/200g)」×「挽き方(豆のまま/中挽き/細挽き)」の
組み合わせバリアントを持つが、挽き方は価格に影響しない。在庫のある
(available=true)バリアントの中から、豆のまま×最小重量を代表バリアントとして
採用する(WOODBERRY COFFEE等のpick_canonical_variant()と同じ考え方)。

【商品説明(body_html)について】
実データ確認済み: テイスティングコメントの自由文のみで、産地・農園等を構造化
したラベル付き説明は無い。産地判定は商品名からのcoffee_parser.parse_product()
のみに依る(商品名に国名・地域名が明記されているため十分機能する)。
"""

import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "FLAT WHITE COFFEE FACTORY",
    "url": "https://flatwhite.jp/",
    "platform": "Shopify",
    # 複数拠点のため店舗単位の詳細住所はlocations参照。理由はモジュールdocstring参照
    "address": "宮城県",
    "prefecture": "宮城県",
    "robots_txt_status": "許可(2026-09確認。標準的なShopify robots.txtで/products/・/collections/は"
                          "User-agent: *に対しAllow。/cart・/checkout・/account等の非公開/取引系のみDisallow)",
}

BASE_URL = "https://flatwhite.jp"
COLLECTION_HANDLES = ["singleorigin", "blendcoffee", "cafeless"]
SHOP_INFO_PAGE_URL = f"{BASE_URL}/pages/shop-info"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}
CRAWL_DELAY_SECONDS = 1

# 理由はモジュールdocstring参照(ドリップバッグ・詰め合わせキットは焙煎豆単品でない)
NON_BEAN_KEYWORDS = ["ドリップバッグ", "ディスカバリーキット", "ギフト", "セット"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
ROASTERY_LABEL = "flagship（泉店）"


def fetch_json(url: str) -> dict:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()


def fetch_collection_products(handle: str) -> list[dict]:
    products = []
    page = 1
    while True:
        url = f"{BASE_URL}/collections/{handle}/products.json?limit=250&page={page}"
        data = fetch_json(url)
        items = data.get("products", [])
        if not items:
            break
        products.extend(items)
        page += 1
        time.sleep(CRAWL_DELAY_SECONDS)
    return products


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    """理由はモジュールdocstring参照(豆のまま×最小重量を代表バリアントとする)。"""
    if not variants:
        return None
    available = [v for v in variants if v.get("available")]
    pool = available or variants

    def weight_key(v):
        return v.get("grams") or float("inf")

    whole_bean = [v for v in pool if "豆のまま" in (v.get("option2") or v.get("title") or "")]
    final_pool = whole_bean or pool
    return min(final_pool, key=weight_key)


def build_record(product: dict) -> dict | None:
    raw_name = product["title"]
    if any(kw in raw_name for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(raw_name)
    variant = pick_canonical_variant(product.get("variants", []))
    price = int(float(variant["price"])) if variant else None
    weight_g = int(variant["grams"]) if variant and variant.get("grams") else None

    all_out_of_stock = bool(product.get("variants")) and not any(v.get("available") for v in product["variants"])
    stock_status = detect_stock_status(raw_name, all_out_of_stock)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": raw_name,
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
        "product_url": f"{BASE_URL}/products/{product['handle']}",
    }


def scrape_all_products() -> list[dict]:
    seen_ids = set()
    records = []
    for handle in COLLECTION_HANDLES:
        for product in fetch_collection_products(handle):
            if product["id"] in seen_ids:
                continue
            seen_ids.add(product["id"])
            record = build_record(product)
            if record:
                records.append(record)
    return records


# --- 店舗拠点一覧(/pages/shop-info) -------------------------------------------
# 理由はモジュールdocstring参照


def scrape_locations() -> list[dict]:
    resp = requests.get(SHOP_INFO_PAGE_URL, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    locations = []
    seen_labels = set()
    for block in soup.select("div.image-with-text"):
        name_el = block.select_one("h2.image-with-text__heading")
        address_el = block.select_one("div.image-with-text__text p")
        if not name_el or not address_el:
            continue
        label = name_el.get_text(strip=True)
        if label in seen_labels:
            continue

        for br in address_el.find_all("br"):
            br.replace_with("\n")
        address_text = address_el.get_text().strip()
        if not address_text.startswith("〒"):
            continue
        seen_labels.add(label)

        address_lines = [line.strip() for line in address_text.split("\n") if line.strip()]
        postal = address_lines[0] if address_lines else None
        address = "".join(address_lines[1:]) if len(address_lines) > 1 else None

        prefecture = None
        if address:
            pref_match = re.match(r"^(宮城県|福島県|山形県|岩手県|秋田県|青森県)", address)
            prefecture = pref_match.group(1) if pref_match else None

        locations.append({
            "label": label,
            "postal_code": postal,
            "address": address,
            "prefecture": prefecture,
            "is_headquarters": label == ROASTERY_LABEL,
            "map_query": f"FLAT WHITE COFFEE FACTORY {label}",
        })
    return locations


def main():
    records = scrape_all_products()
    locations = scrape_locations()

    shop_info = dict(SHOP_INFO)
    shop_info["locations"] = locations

    import json
    from datetime import datetime, timezone

    output = {
        "shop": shop_info,
        "products": records,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }
    with open("data_flatwhite.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件・拠点{len(locations)}件を data_flatwhite.json に出力しました")


if __name__ == "__main__":
    main()
