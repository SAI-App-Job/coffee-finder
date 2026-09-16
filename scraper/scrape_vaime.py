# -*- coding: utf-8 -*-
"""
scrape_vaime.py

VAIME COFFEE(vaimecoffee.com、〒090-0838 北海道北見市西三輪4丁目722-24、
2024年11月開業の自家焙煎豆のオンライン販売)の商品情報を取得する。Shopify。

住所はトップページの記載にて実データ確認済み: 「〒090-0838 北海道北見市
西三輪4丁目722-24」(候補リストの住所と一致)。

robots.txt確認済み(2026-09時点): Shopify標準の記述。/cart等の取引系
ページのみDisallow、商品ページ(/products/)は一般クローラーに許可
(adsbot-googleセクションで明記)。本プロジェクトでShopify採用店舗は初めて
だが、公開のproducts.json(Shopify標準API)が利用可能で最も確実。

【商品一覧の取得方法について】
実データ確認済み(2026-09時点、全15件): Shopify標準のproducts.json
エンドポイント(/products.json?limit=250)から全商品のtitle・price・
body_html(商品説明)・tagsを取得する。

【対象商品の絞り込みについて】
実データ確認済み: 「ディップスタイル珈琲」(ドリップバッグ、単品/10個
セット)の2件のみが非対象(表記は「ディップ」だが実質ドリップバッグ)。
NON_BEAN_KEYWORDSで除外する。残り13件は全て単一銘柄の焙煎豆(100g)で、
body_html内に「・内容量<br>100g」等のラベルが付与されている。

【商品説明の構造】
実データ確認済み: body_html内に「・原産国<br>コロンビア」のように
「・ラベル<br>値」形式のラベル付き製品情報が明記されている
(原産国/エリア/生産者/標高/精製方法/焙煎度/品種/風味/内容量)。
タグ(tags)にも浅煎り/中煎り/深煎りが入っている場合があるが、無い商品も
あるため、本文中の「・焙煎度<br>...」ラベルを優先し、無ければtagsから
拾う。
"""

import re
import unicodedata

import requests

from coffee_parser import parse_product, detect_stock_status, normalize_processing_method, detect_country_name

SHOP_INFO = {
    "name": "VAIME COFFEE",
    "url": "https://vaimecoffee.com/",
    "platform": "Shopify",
    "address": "北海道北見市西三輪4丁目722-24",
    "prefecture": "北海道",
    "robots_txt_status": "許可(2026-09確認。Shopify標準のrobots.txt。/cart等の取引系ページのみ"
                          "Disallow、商品ページ(/products/)は一般クローラーに許可)",
}

BASE_URL = "https://vaimecoffee.com"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["ディップ", "ドリップバッグ"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
ROAST_HINT_KEYWORDS = ["浅煎り", "中煎り", "中深煎り", "中浅煎り", "深煎り"]
LABEL_PATTERN = re.compile(
    r"・(原産国|エリア|生産者|標高|精製方法|焙煎度|品種|風味|内容量)<br\s*/?>(.*?)</p>",
    re.DOTALL,
)


def fetch_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json", params={"limit": 250},
                         headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.json().get("products", [])


def parse_labels(body_html: str) -> dict:
    text = body_html or ""
    labels = {}
    for label, value in LABEL_PATTERN.findall(text):
        clean = re.sub(r"<[^>]+>", " ", value)
        clean = unicodedata.normalize("NFKC", clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        if clean:
            labels[label] = clean
    return labels


def detect_roast_hint(labels: dict, tags: list[str]) -> str | None:
    roast_text = labels.get("焙煎度", "")
    for kw in ROAST_HINT_KEYWORDS:
        if kw in roast_text:
            return kw
    for tag in tags or []:
        for kw in ROAST_HINT_KEYWORDS:
            if kw in tag:
                return kw
    return None


def build_record(product: dict) -> dict | None:
    raw_title = (product.get("title") or "").strip()
    # 理由: 商品名先頭に「19.」「1.」等の管理用連番が付いている商品がある
    # (実データ確認済み)ため、銘柄名の判定・表示双方に影響しないよう
    # raw_nameからは除去せず保持しつつ、parse_product用には連番を落とした
    # テキストで判定する。
    title_for_parse = re.sub(r"^\d+[.．]\s*", "", raw_title)
    title = unicodedata.normalize("NFKC", raw_title)

    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(unicodedata.normalize("NFKC", title_for_parse))

    variants = product.get("variants") or []
    price = int(float(variants[0]["price"])) if variants and variants[0].get("price") else None
    available = any(v.get("available") for v in variants) if variants else False

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": f"{BASE_URL}/products/{product.get('handle')}",
        }

    labels = parse_labels(product.get("body_html") or "")

    if labels.get("原産国"):
        country = detect_country_name(labels["原産国"])
        if country:
            parsed["origin_country"] = country
            parsed["origin_source"] = "product_description"

    if labels.get("精製方法"):
        parsed["processing_method"] = normalize_processing_method(labels["精製方法"])

    farm_note_parts = []
    if labels.get("エリア"):
        farm_note_parts.append(f"エリア: {labels['エリア']}")
    if labels.get("生産者"):
        farm_note_parts.append(f"生産者: {labels['生産者']}")
    if labels.get("標高"):
        farm_note_parts.append(f"標高: {labels['標高']}")
    if labels.get("品種"):
        farm_note_parts.append(f"品種: {labels['品種']}")
    farm_note = "、".join(farm_note_parts) if farm_note_parts else None

    weight_m = WEIGHT_PATTERN.search(labels.get("内容量", "")) or WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None

    structural_out_of_stock = not available
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
        "roast_level": None,
        "roast_hint": detect_roast_hint(labels, product.get("tags") or []),
        "roast_selectable": False,
        "post_processing_tags": parsed["post_processing_tags"],
        "farm_note": farm_note,
        "flavor_notes": labels.get("風味"),
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": f"{BASE_URL}/products/{product.get('handle')}",
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
    with open("data_vaime.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_vaime.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
