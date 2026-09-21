# -*- coding: utf-8 -*-
"""
scrape_toyotomicoffee.py

とよとみ珈琲(toyotomicoffee.com、〒770-0866 徳島県徳島市末広2-1-43、
自家焙煎豆のオンライン販売)の商品情報を取得する。Shopify(/products.json
全件取得方式)。

【住所について】
実データ確認済み(2026-09時点): 公式サイトの特定商取引法ページ
(https://toyotomicoffee.com/policies/legal-notice)で「〒770-0866
徳島市末広2丁目1番43号」と一致確認済み。

robots.txt確認済み(2026-09時点): Shopify標準のrobots.txtでAllow: /
(AIエージェント向けagents.md/UCPエンドポイントの案内を含む標準
テンプレート)。制限なし。

【非コーヒー豆商品の除外について】
実データ確認済み(全50件): ドリップバッグ/コーヒーバッグ単品・セット
(イタリアンブレンド/とよとみブレンド、1pcs/10pcs)・ギフト用ドリップバッグ
詰め合わせ各種・マスターのおすすめ+選べる2種のBOX(定期便含む、産地不定の
アソート)・手提げ袋/ラッピング(包装資材)・熨斗各種(内祝・御中元・御歳暮・
御祝・御供)・「【特別割引】とよとみ珈琲 オリジナルアイスコーヒー」
(2026-09-21新規追加、瓶入りの完成品リキッド、variantの単位が「本」で
グラム表記が無い)が非対象。NON_BEAN_KEYWORDSで除外する。

【BOX版の重複について】
実データ確認済み: 各ストレート/ブレンド銘柄について、通常版(200g、
handle末尾なし)とBOX版(100g、handle末尾"-box"、贈答用パッケージ)が
別商品として登録されている。BOX版はAPI上価格が0円で取得され信頼できない
ため、通常版(200g・1200円)のみを対象とし、"-box"のhandleを持つ商品は
除外する。

【重量・価格について】
実データ確認済み: 対象化した9種のストレート/4種のブレンドは全て単一
バリアント・200g・1,200円で統一されている。

【flavor_notes(2026-09-21追記)】
実データ確認済み: body_htmlにテイスティング文・産地の背景ストーリーが
地続きで入っている(対象14件全て確認)。末尾に必ず「▼注意点」という
「買えば買うほどお得」等の販売単位に関する店舗共通の定型注意書きが続く
ため、そこで切り落とす。一部の単一農園ロットの説明にはテーブル形式の
構造化スペック欄(栽培エリア/サプライヤー/農園面積/栽培面積/品種/標高/
精製方法)が独立した行として入るため、ラベルのみの行を除去する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "とよとみ珈琲",
    "url": "https://toyotomicoffee.com/",
    "platform": "Shopify",
    "address": "徳島県徳島市末広2-1-43",
    "prefecture": "徳島県",
    "robots_txt_status": "実質許可(2026-09確認。Shopify標準のrobots.txtでAllow: /、制限なし)",
}

PRODUCTS_JSON_URL = "https://toyotomicoffee.com/products.json?limit=250"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "ドリップバッグ", "コーヒーバッグ", "ギフト", "BOX", "手提げ袋",
    "ラッピング", "包装", "熨斗", "内祝", "御中元", "御歳暮", "御祝", "御供",
    "オリジナルアイスコーヒー",
]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
FLAVOR_STOP_PATTERN = re.compile(r"▼注意点")
FLAVOR_SPEC_LABEL_LINE_PATTERN = re.compile(
    r"^(栽培エリア|サプライヤー|農園面積|栽培面積|品種|標高|精製方法|農園主)$"
)


def extract_flavor_notes(body_html: str | None) -> str | None:
    """理由はモジュールdocstring参照。"""
    soup = BeautifulSoup(body_html or "", "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    text = soup.get_text("\n", strip=True)
    stop_m = FLAVOR_STOP_PATTERN.search(text)
    if stop_m:
        text = text[: stop_m.start()]
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    lines = [l for l in lines if not FLAVOR_SPEC_LABEL_LINE_PATTERN.match(l)]
    return "\n".join(lines).strip() or None


def fetch_products() -> list[dict]:
    resp = requests.get(PRODUCTS_JSON_URL, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json().get("products", [])


def is_excluded(product: dict) -> bool:
    title = (product.get("title") or "").strip()
    handle = (product.get("handle") or "").strip()
    if not title:
        return True
    if handle.endswith("-box"):
        return True
    return any(kw in title for kw in NON_BEAN_KEYWORDS)


def build_record(product: dict) -> dict | None:
    title = (product.get("title") or "").strip()
    parsed = parse_product(title)
    product_url = f"https://toyotomicoffee.com/products/{product.get('handle')}"

    variants = product.get("variants") or []

    if parsed["is_flavored"]:
        price = int(float(variants[0]["price"])) if variants and variants[0].get("price") is not None else None
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": product_url,
        }

    price = int(float(variants[0]["price"])) if variants and variants[0].get("price") is not None else None
    weight_matches = WEIGHT_PATTERN.findall(title)
    weight_g = int(weight_matches[-1]) if weight_matches else (variants[0].get("grams") if variants else None)

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
    filtered = [p for p in products if not is_excluded(p)]

    records = []
    flavored_records = []
    for product in filtered:
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
    with open("data_toyotomicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_toyotomicoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
