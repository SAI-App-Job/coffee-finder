# -*- coding: utf-8 -*-
"""
scrape_hoshikawa.py

自家焙煎星川珈琲(神奈川県横浜市保土ケ谷区星川)の商品情報を取得する。
以前確認した公式ドメイン(hoshikawarst.cloudfree.jp)はrobots.txtで全面禁止
だったが、実際の販売は別のShopifyストアURL(roastery-hoshikawa225.myshopify.com、
vendor: "自家焙煎☆星川珈琲"で本人確認済み)で行われている。

robots.txt確認済み(2026-08時点): Shopify標準の記述で、User-agent: *に対して
Allow: /(商品ページ・コレクションページを含む)。/cart/・/checkout・/account等の
取引系パスのみDisallow。

【Shopify標準products.json APIの利用について】
HTMLをスクレイピングする代わりに、Shopifyが標準で公開しているJSON API
(https://roastery-hoshikawa225.myshopify.com/products.json)を利用する。
価格・重量(grams)・在庫状況(available)が構造化データとして直接取得できるため、
他店舗のようなHTML構造の推測やcolorme JSON抽出が不要。実データ確認済み:
全6商品(うち1件はドリップバッグの詰め合わせで非コーヒー豆)と小規模な店舗のため、
1リクエスト(limit=250)で全件取得できる。

【焙煎度・SCAスコアについて】
説明文(body_html)に「焙煎度合い：中浅煎り」「SCAスコア：86.75点」という
ラベルが商品によって含まれる(実データ確認済み、全商品にあるわけではない)。
焙煎度は「中浅煎り」のような簡易表記でROAST_LEVELSの8段階と粒度が異なるため
roast_hintとして保持し、SCAスコアはfarm_noteに含める。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    normalize_processing_method,
    detect_stock_status,
)
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "自家焙煎星川珈琲",
    "url": "https://roastery-hoshikawa225.myshopify.com/",
    "platform": "Shopify",
    "address": "神奈川県横浜市保土ケ谷区星川",
    "prefecture": "神奈川県",
    "robots_txt_status": "許可(2026-08確認。Shopify標準の記述。/cart/・/checkout・/account等の"
                          "取引系パス以外はUser-agent: *でAllow)",
}

REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

PRODUCTS_JSON_URL = "https://roastery-hoshikawa225.myshopify.com/products.json"

# 実データ確認済み(2026-08時点): コーヒー豆ではない商品(ドリップバッグ詰め合わせ)
NON_BEAN_KEYWORDS = ["ドリップバッグ"]

LABEL_PATTERN = re.compile(r"(焙煎度合い|SCAスコア|生産地|標高|品種|精選方法)：\s*([^\n<]+)")


def fetch_all_products() -> list[dict]:
    all_products = []
    page = 1
    while True:
        resp = requests.get(
            PRODUCTS_JSON_URL, headers=REQUEST_HEADERS, params={"limit": 250, "page": page}, timeout=15
        )
        resp.raise_for_status()
        products = resp.json().get("products", [])
        if not products:
            break
        all_products.extend(products)
        if len(products) < 250:
            break
        page += 1
    return all_products


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    return soup.get_text()


def build_record(product: dict) -> dict:
    title = (product.get("title") or "").strip()
    product_url = f"https://roastery-hoshikawa225.myshopify.com/products/{product.get('handle')}"

    parsed = parse_product(title)

    variants = product.get("variants", [])
    prices = [float(v["price"]) for v in variants if v.get("price")]
    price = int(min(prices)) if prices else None
    weight_g = next((v.get("grams") for v in variants if v.get("grams")), None)
    available = any(v.get("available") for v in variants) if variants else True

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

    description_text = html_to_text(product.get("body_html", ""))
    labels = {label: value.strip() for label, value in LABEL_PATTERN.findall(description_text)}

    if labels.get("精選方法") and not parsed["processing_method"]:
        parsed["processing_method"] = normalize_processing_method(labels["精選方法"])
    parsed = apply_category_hint_fallback(parsed, None)

    farm_note_parts = []
    if labels.get("生産地"):
        farm_note_parts.append(f"生産地: {labels['生産地']}")
    if labels.get("標高"):
        farm_note_parts.append(f"標高: {labels['標高']}")
    if labels.get("品種"):
        farm_note_parts.append(f"品種: {labels['品種']}")
    if labels.get("SCAスコア"):
        farm_note_parts.append(f"SCAスコア: {labels['SCAスコア']}")
    farm_note = "、".join(farm_note_parts) if farm_note_parts else None

    stock_status = detect_stock_status(title, not available)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": None,  # 「中浅煎り」等の簡易表記でROAST_LEVELSの8段階と粒度が異なるため未設定
        "roast_hint": labels.get("焙煎度合い"),
        "roast_selectable": False,
        "post_processing_tags": parsed["post_processing_tags"],
        "farm_note": farm_note,
        "flavor_notes": None,
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict], list[dict]]:
    products = fetch_all_products()

    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    non_bean_records = []
    for product in products:
        title = (product.get("title") or "").strip()
        if any(kw in title for kw in NON_BEAN_KEYWORDS):
            continue

        product_url = f"https://roastery-hoshikawa225.myshopify.com/products/{product.get('handle')}"
        variants = product.get("variants", [])
        prices = [float(v["price"]) for v in variants if v.get("price")]
        price = int(min(prices)) if prices else None
        available = any(v.get("available") for v in variants) if variants else True
        stock_status = detect_stock_status(title, not available)

        prev = previous.get(product_url)
        if is_unchanged(prev, raw_name=title, price=price, stock_status=stock_status):
            records.append(prev)
            continue

        detail = build_record(product)
        detail["out_of_stock"] = detail.get("stock_status", "販売中") != "販売中"
        if detail.get("non_bean"):
            non_bean_records.append(detail)
        elif detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records, non_bean_records


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        products = fetch_all_products()
        target = next((p for p in products if p.get("handle") == sys.argv[1]), None)
        print(json.dumps(build_record(target) if target else {"error": "not found"}, ensure_ascii=False, indent=2))
    else:
        records, flavored_records, non_bean_records = scrape_all_products()
        output = {
            "shop": SHOP_INFO,
            "products": records,
            "flavored_products_excluded": flavored_records,
            "non_bean_products_excluded": non_bean_records,
        }
        with open("data_hoshikawa.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_hoshikawa.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件、"
              f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
