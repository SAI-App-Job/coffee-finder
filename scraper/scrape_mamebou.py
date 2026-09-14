# -*- coding: utf-8 -*-
"""
scrape_mamebou.py

珈琲まめ坊(mamebou.com、宮城県仙台市青葉区米ヶ袋1-1-12、自家焙煎豆のオンライン販売)の
商品情報を取得する。Shopify。

【住所について】
商品詳細ページのbody_html末尾に製造者表記があり、実データ確認済み(2026-09時点):
「自家焙煎　珈琲まめ坊　宮城県仙台市青葉区米ヶ袋1-1-12　電話：022-738-8066」。

【AIエージェント向け指示について】
robots.txtの先頭コメントに「エージェントはUCP/MCPエンドポイントやshop.appの
SKILLを使い、購入代行すべき」という趣旨の記述があったが、これはこのサイトの
コンテンツ(=信頼できない外部指示)であり、ユーザー自身の指示ではないため一切
従っていない。本スクレイパーは商品情報の読み取りのみを行う(WOODBERRY COFFEE等と
同じ対応方針)。

【対象コレクションについて】
実データ確認済み(2026-09時点): トップレベルの「コーヒー豆」コレクション(handle:
coffeebeans)はギフトセット3件のみで、実際のストレート/ブレンド単品は「single」
(19件、国別地域コレクションafrica/asia/central-america/south-americaの親集合)と
「blend」(8件、classic-blend/seasonal-blendの親集合)の2コレクションに分かれている
ことが判明。この2つを対象とする(地域別の子コレクションは重複を避けるため使わない)。

【除外商品について】
実データ確認済み: singleコレックションに「通販限定・おまかせシングルオリジン
珈琲豆セット（200g×3袋）」(single-3-100g/200g、複数銘柄の詰め合わせ)、blend
コレクションに「定番3種セット」(teiban-3-100g/200g)、ドリップバッグ形式の
デカフェ商品(jitaku-decaf、home-decafbag-mexico)が混在しており、いずれも単一
銘柄の焙煎豆単品ではないため除外する。

【商品詳細ページのbody_htmlについて】
実データ確認済み: 「品名/原材料名/内容量/焙煎度合/賞味期限/保存方法/生産国名/
外箱サイズ/製造者」という決まったラベルが各行に並ぶ形式。ラベル行の次の行が値
という単純な構造のため、ラベル→直後の行、で値を抽出する。ブレンド商品は
「生産国名」が「グァテマラ，ルワンダ，ブラジル等」のように複数国のカンマ区切りに
なる(単一原産国ではない)ため、ブレンドの場合はorigin_countryに反映しない
(WOODBERRY COFFEE等の他店と同じ方針)。

【焙煎度合について】
実データ確認済み: 「中煎」のような粗い表記(何段階かは不明、少なくとも浅煎/中煎/
深煎の3種は確認)で、本アプリのroast_levelが要求する8段階表記とは粒度が異なる
ため、roast_hintとして保持しroast_levelは構造化しない(WOODBERRY COFFEE・
405coffee等で確立した方針と同じ)。
"""

import re
import time

import requests

from coffee_parser import parse_product, detect_country_name

SHOP_INFO = {
    "name": "珈琲まめ坊",
    "url": "https://www.mamebou.com/",
    "platform": "Shopify",
    "address": "宮城県仙台市青葉区米ヶ袋1-1-12",
    "prefecture": "宮城県",
    "robots_txt_status": "許可(2026-09確認。標準的なShopify robots.txtで/products/・/collections/は"
                          "User-agent: *に対しAllow。/cart・/checkout・/account等の非公開/取引系のみDisallow)",
}

BASE_URL = "https://www.mamebou.com"
COLLECTION_HANDLES = ["single", "blend"]
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}
CRAWL_DELAY_SECONDS = 1

# 理由はモジュールdocstring参照(複数銘柄の詰め合わせセット・ドリップバッグ形式は
# 単一銘柄の焙煎豆単品ではないため除外)
NON_BEAN_KEYWORDS = ["セット", "ドリップバッグ", "ギフト"]

LABEL_PATTERN = re.compile(
    r"(内容量|焙煎度合|生産国名)\n([^\n]*)", re.MULTILINE
)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


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


def parse_body_labels(body_html: str) -> dict:
    text = re.sub(r"<[^>]+>", "\n", body_html or "")
    text = re.sub(r"\n{2,}", "\n", text).strip()
    fields = {}
    for m in LABEL_PATTERN.finditer(text):
        fields[m.group(1)] = m.group(2).strip()
    return fields


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    if not variants:
        return None
    available = [v for v in variants if v.get("available")]
    pool = available or variants
    return pool[0]


def build_record(product: dict) -> dict:
    raw_name = product["title"]
    parsed = parse_product(raw_name)
    is_blend = parsed["category"] == "ブレンド"

    detail = fetch_json(f"{BASE_URL}/products/{product['handle']}.json")["product"]
    fields = parse_body_labels(detail.get("body_html") or "")

    origin_country = None
    if not is_blend and fields.get("生産国名"):
        origin_country = detect_country_name(fields["生産国名"]) or fields["生産国名"]
        if origin_country:
            parsed["origin_country"] = origin_country
            parsed["origin_source"] = "product_description"

    variant = pick_canonical_variant(product.get("variants", []))
    price = int(float(variant["price"])) if variant else None
    weight_m = WEIGHT_PATTERN.search(fields.get("内容量") or "")
    weight_g = int(weight_m.group(1)) if weight_m else (int(variant["grams"]) if variant and variant.get("grams") else None)

    all_out_of_stock = bool(product.get("variants")) and not any(v.get("available") for v in product["variants"])
    stock_status = "一時的に品切れ" if all_out_of_stock else "販売中"

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": raw_name,
        "category": parsed["category"],
        "origin_country": None if is_blend else parsed["origin_country"],
        "origin_source": None if is_blend else parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": None,  # 理由はモジュールdocstring参照(粗い表記のためroast_hintに保持)
        "roast_hint": fields.get("焙煎度合"),
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
    all_products = []
    for handle in COLLECTION_HANDLES:
        for product in fetch_collection_products(handle):
            if product["id"] in seen_ids:
                continue
            seen_ids.add(product["id"])
            all_products.append(product)

    records = []
    for product in all_products:
        if any(kw in product["title"] for kw in NON_BEAN_KEYWORDS):
            continue
        try:
            records.append(build_record(product))
            time.sleep(CRAWL_DELAY_SECONDS)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product['handle']} ({e})")

    return records


if __name__ == "__main__":
    import json
    from datetime import datetime, timezone

    records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }
    with open("data_mamebou.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mamebou.json に出力しました")
