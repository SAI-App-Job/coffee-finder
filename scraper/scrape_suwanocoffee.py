# -*- coding: utf-8 -*-
"""
scrape_suwanocoffee.py

SUWANO COFFEE(suwanokoffee.base.shop、〒830-0003 福岡県久留米市東櫛原町
1012-1 ユニバーシティ櫛原1F、自家焙煎とコーヒーテイクアウトの店)の
商品情報を取得する。BASE(白ラベルドメイン)。

【住所について】
特定商取引法ページ(https://suwanokoffee.base.shop/law)の「事業者の
所在地」に「〒8300003 福岡県久留米市東櫛原町1012-1ユニバーシティ櫛原1F」
と明記されており、BASE社の代理住所ではなく実店舗の住所であることを
確認済み(2026-09時点)。

robots.txt確認済み(2026-09時点): 他のBASE系店舗と同一の記述。curl/
python-requests等は個別にDisallow: /指定があるが、User-agent: *ルールでは
/cart/・/web_cart/・/shops/・/api/shops/・違反報告ページ以外はAllow: /。
本スクレイパーは識別可能な独自User-Agentを使用するため該当しない。

【商品情報の取得方法について】
実データ確認済み: 他のBASE系店舗と同様、SNSシェア用OGPメタタグ
(`og:title`・`product:price:amount`)から商品名・価格を取得する。

【非コーヒー豆商品の除外について】
実データ確認済み(全26件): 「ゲイシャ　100g ブラジル　ショコラ　100g
飲み比べ」(2銘柄飲み比べセット)・「コーヒー豆【自家焙煎】100gx4種セット」
(4銘柄詰め合わせ)が複数銘柄の詰め合わせで単一銘柄でないため対象外。
NON_BEAN_KEYWORDSで除外する。

【重量違いについて】
実データ確認済み: 同一銘柄が100g/200gの2形態で個別商品登録されている
ことが多いが、それぞれ独立した実在SKUのため重複排除は行わず個別の
レコードとして出力する。

【flavor_notes(2026-09-20追記)】
実データ確認済み: og:descriptionのほぼ全文がテイスティング・商品紹介文
になっている(構造化ラベルを持たない商品が大半)。一部商品は末尾に
「※開封後は、風味が失われることがあります。」等の保存方法定型文、
「＊送料無料で発送します。」等の発送定型文、または「生産地\t...」
「ゲイシャ地域：...」「《精製方法》...」「［コーヒー豆］...」(ブレンド
配合内訳)のようなタブ/コロン/記号区切りの構造化スペック・配合内訳が
続く。これらの開始位置のうち最初に出現したものの直前までをflavor_notes
として採用する(該当箇所が無い商品は全文を採用)。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "SUWANO COFFEE",
    "url": "https://suwanokoffee.base.shop/",
    "platform": "BASE",
    "address": "福岡県久留米市東櫛原町1012-1 ユニバーシティ櫛原1F",
    "prefecture": "福岡県",
    "robots_txt_status": "実質許可(2026-09確認。他のBASE系店舗と同一の記述。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://suwanokoffee.base.shop"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["飲み比べ", "セット"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
FLAVOR_STOP_PATTERN = re.compile(
    r"※開封後は|＊送料無料で発送します|生産地\t|ゲイシャ地域[：:]|《精製方法》|［コーヒー豆］"
)


def extract_flavor_notes(description: str | None) -> str | None:
    """理由はモジュールdocstring参照。"""
    if not description:
        return None
    m = FLAVOR_STOP_PATTERN.search(description)
    text = description[:m.start()] if m else description
    return text.strip() or None


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def extract_og_fields(soup: BeautifulSoup) -> dict | None:
    title_el = soup.select_one('meta[property="og:title"]')
    if not title_el or not title_el.get("content"):
        return None
    title = title_el["content"].split(" | ")[0].strip()
    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None
    desc_el = soup.select_one('meta[property="og:description"]')
    description = desc_el["content"] if desc_el and desc_el.get("content") else None
    return {"title": title, "price": price, "description": description}


def fetch_sitemap_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "/items/" in loc.get_text()]


def build_record(item: dict) -> dict | None:
    title = item["title"]
    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": item["price"],
            "product_url": item["url"],
        }

    stock_status = detect_stock_status(title)
    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None

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
        "flavor_notes": extract_flavor_notes(item.get("description")),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_sitemap_urls()

    records = []
    flavored_records = []
    for product_url in product_urls:
        try:
            fields = extract_og_fields(fetch_page(product_url))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if not fields:
            print(f"[warn] OGPメタタグが見つかりません: {product_url}")
            continue

        detail = build_record({
            "title": fields["title"], "price": fields["price"],
            "description": fields.get("description"), "url": product_url,
        })
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
    with open("data_suwanocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_suwanocoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
