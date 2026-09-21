# -*- coding: utf-8 -*-
"""
scrape_mukashimukashi.py

珈琲豆屋むかしむかし(mukashi2.base.ec、熊本県人吉市蟹作町1088-4、自家焙煎
豆のオンライン販売)の商品情報を取得する。BASE。

【住所について】
特定商取引法ページ(https://mukashi2.base.ec/law)では、他のBASE店舗と同様
「ネットショップ作成サービス「BASE」を運営しているBASE株式会社の所在地」
(東京都港区六本木のBASE社本社)が表示されるのみで、店舗自身の住所は非公開
(規約上の代理表記)。この場合は通常「住所確認不可」として除外する方針だが、
本店舗は候補リストに挙げられた通り、公式Wixサイト(coffeemukashi2.wixsite.
com/home、実データ確認済み)の「お問い合わせ」欄に一次情報として「熊本県
人吉市蟹作町1088-4」との記載を直接確認できたため、この住所を採用する
(BASEの代理住所ではなく、店舗自身の別チャネルでの一次情報による確認)。

robots.txt確認済み(2026-09時点): 他のBASE系店舗と同一の記述。curl/
python-requests等は個別にDisallow: /指定があるが、User-agent: *ルールでは
実質許可。本スクレイパーは識別可能な独自User-Agentを使用する。

【対象商品について】
実データ確認済み(全5件): sitemap.xmlの/items/配下5件のうち、実際の焙煎豆
単品は「自家焙煎珈琲　オリジナルブレンド　200gパック」(¥2,000)の1件のみ。
他は自家焙煎水出し珈琲(水出しバッグ)・甘茶と珈琲10枚セット(フレーバー付与
ブレンドのドリップバッグ)・オリジナルドリップ20枚/10枚セット(ドリップ
バッグ)のため非対象。NON_BEAN_KEYWORDSで除外する。

【flavor_notes(2026-09-22追記)】
実データ確認済み: og:descriptionに対象1件で簡潔なテイスティング文が
入っている。末尾に「購入時に豆のまま、挽いて、かをお知らせください。」
という挽き方選択案内の定型文が続くため、この直前で打ち切る。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "珈琲豆屋むかしむかし",
    "url": "https://mukashi2.base.ec/",
    "platform": "BASE",
    "address": "熊本県人吉市蟹作町1088-4",
    "prefecture": "熊本県",
    "robots_txt_status": "実質許可(2026-09確認。他のBASE系店舗と同一の記述。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://mukashi2.base.ec"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["水出し", "セット", "ドリップ"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
TRAILING_WEIGHT_PATTERN = re.compile(r"[\s　]*\d+\s*[gｇ]パック\s*$")
FLAVOR_STOP_PATTERN = re.compile(r"購入時に豆のまま")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def extract_og_fields(soup: BeautifulSoup) -> dict | None:
    title_el = soup.select_one('meta[property="og:title"]')
    if not title_el or not title_el.get("content"):
        return None
    title = title_el["content"].split(" | ")[0].strip()
    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None
    desc_el = soup.select_one('meta[property="og:description"]')
    flavor_notes = desc_el["content"].strip() if desc_el and desc_el.get("content") else ""
    m = FLAVOR_STOP_PATTERN.search(flavor_notes)
    if m:
        flavor_notes = flavor_notes[:m.start()].strip()
    return {"title": title, "price": price, "flavor_notes": flavor_notes or None}


def fetch_item_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "/items/" in loc.get_text()]


def base_name_and_weight(title: str) -> tuple[str, int | None]:
    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None
    base = TRAILING_WEIGHT_PATTERN.sub("", title).strip()
    return base, weight_g


def build_record(title: str, price: int | None, product_url: str, flavor_notes: str | None = None) -> dict | None:
    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None
    if not WEIGHT_PATTERN.search(title):
        return None
    base_name, weight_g = base_name_and_weight(title)
    if not base_name:
        return None
    parsed = parse_product(base_name)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": base_name,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": product_url,
        }

    stock_status = detect_stock_status(base_name)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": base_name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "flavor_notes": flavor_notes,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    item_urls = fetch_item_urls()

    records = []
    flavored_records = []
    for product_url in item_urls:
        try:
            fields = extract_og_fields(fetch_page(product_url))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if not fields:
            continue
        detail = build_record(fields["title"], fields["price"], product_url, fields.get("flavor_notes"))
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
    with open("data_mukashimukashi.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mukashimukashi.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
