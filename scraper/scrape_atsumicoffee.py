# -*- coding: utf-8 -*-
"""
scrape_atsumicoffee.py

あつみ珈琲(Atsumi Coffee、atsumicoffee.shopselect.net、〒802-0064
福岡県北九州市小倉北区片野1-1-10、自家焙煎スペシャルティコーヒー専門店
「あつみ珈琲 北九州小倉片野店」)の商品情報を取得する。BASE
(shopselect.net、BASEの旧ブランドドメイン)。

【住所について】
特定商取引法ページ(https://atsumicoffee.shopselect.net/law)の「事業者の
所在地」に「〒8020064 福岡県北九州市小倉北区片野1-1-10」と明記されて
おり、BASE社の代理住所ではなく実店舗の住所であることを確認済み
(2026-09時点)。

robots.txt確認済み(2026-09時点): 他のBASE系店舗と同一の記述。curl/
python-requests等は個別にDisallow: /指定があるが、User-agent: *ルールでは
/cart/・/web_cart/・/shops/・/api/shops/・違反報告ページ以外はAllow: /。
本スクレイパーは識別可能な独自User-Agentを使用するため該当しない。

【商品情報の取得方法について】
実データ確認済み: 他のBASE系店舗と同様、SNSシェア用OGPメタタグ
(`og:title`・`product:price:amount`)から商品名・価格を取得する。

【非コーヒー豆商品の除外について】
実データ確認済み(全25件): 「あつみセレクトご自宅用」(複数銘柄の
福袋的セット、金額表記のみで銘柄不明)・Atsumi Select ドリップバッグ
各種・ドリップバッグギフト各種・水出しコーヒーギフト・珈琲豆お任せ
ギフト・詰め合わせお任せギフト・アバカ コーヒーフィルター(器具)が
非対象。NON_BEAN_KEYWORDSで除外する。

【flavor_notes(2026-09-21追記)】
実データ確認済み: og:descriptionにテイスティング文が直接入っており
(対象12件全て確認)、その後に必ず「(1)焙煎度合いと」または
「(1)煎り具合と」で始まる挽き方選択案内・割引案内・配送案内が続く。
500g商品の一部では先頭に「★豆はまとめ買いがおススメ！500gは通常
価格の13%OFFでお得です★」という店舗共通のセール文言が付く。これらを
除去し、テイスティング文のみを採用する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "あつみ珈琲",
    "url": "https://atsumicoffee.shopselect.net/",
    "platform": "BASE",
    "address": "福岡県北九州市小倉北区片野1-1-10",
    "prefecture": "福岡県",
    "robots_txt_status": "実質許可(2026-09確認。他のBASE系店舗と同一の記述。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://atsumicoffee.shopselect.net"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "セレクト", "ドリップバッグ", "ギフト", "SET", "詰め合わせ", "コーヒーフィルター",
]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
FLAVOR_LEADING_PATTERN = re.compile(r"^★豆はまとめ買いがおススメ！500gは通常価格の13%OFFでお得です★")
FLAVOR_STOP_PATTERN = re.compile(r"\(1\)(?:焙煎度合い|煎り具合)と")


def extract_flavor_notes(description: str | None) -> str | None:
    """理由はモジュールdocstring参照。"""
    if not description:
        return None
    text = FLAVOR_LEADING_PATTERN.sub("", description)
    m = FLAVOR_STOP_PATTERN.search(text)
    if m:
        text = text[: m.start()]
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
    flavor_notes = extract_flavor_notes(desc_el["content"]) if desc_el and desc_el.get("content") else None
    return {"title": title, "price": price, "flavor_notes": flavor_notes}


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
        "flavor_notes": item.get("flavor_notes"),
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
            "title": fields["title"],
            "price": fields["price"],
            "url": product_url,
            "flavor_notes": fields.get("flavor_notes"),
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
    with open("data_atsumicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_atsumicoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
