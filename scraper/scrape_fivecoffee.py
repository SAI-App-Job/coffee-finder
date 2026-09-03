# -*- coding: utf-8 -*-
"""
scrape_fivecoffee.py

FIVE COFFEE STAND&ROASTERY(www.fivecoffee.jp、東京都台東区谷中、
2020年開業)の商品情報を取得する。BASEのカスタムドメイン。

【ドメインについて】
実データ確認済み: 「fivecoffee.jp」(wwwなし)はDNS未解決(名前解決不可)。
「www.fivecoffee.jp」でのみアクセス可能。

【商品情報の取得方法について(実データ調査で判明した不具合と対処)】
当初、`window.dataLayer.push({...})`というGoogleタグマネージャー向け
JSオブジェクトリテラルに埋め込まれた`item_name`/`itemPrice`を正規表現で
抽出する実装にしていたが、実際にGitHub Actionsから実行したところ
0件しか取得できない不具合が発生した。デバッグ出力で調査した結果、
GitHub Actions環境からのリクエストに対して返るHTMLには
`dataLayer`のスクリプト自体が含まれていないことが判明した(ローカルの
手元環境からのリクエストでは含まれていたため、ボット検知等により
GTM/アナリティクス関連スクリプトが条件付きで除去されている可能性が
高い)。一方、SNSシェア用のOGP(Open Graph)メタタグ
(`og:title`・`product:price:amount`)は常に静的に出力されており、
これはFacebook/Twitter等の外部クローラーが読めなければならない性質上
除去されにくいと考えられる。そのためOGPメタタグから商品名・価格を
取得する方式に変更した(入谷珈琲豆店の同種の不具合も同じ対処)。

robots.txt確認済み(2026-09時点、https://www.fivecoffee.jp/robots.txt):
他のBASE系店舗と同一の記述。curl/python-requests等は個別にDisallow: /
指定があるが、User-agent: *ルールでは/cart/・/web_cart/・/shops/・
/api/shops/・違反報告ページ以外はAllow: /。本スクレイパーは識別可能な
独自User-Agentを使用するため該当しない。

【非コーヒー豆商品の除外について】
実データ確認済み(sitemap.xml上34件、うちhome/about除く32件が商品):
ドリップバッグ("ドリップバック おまかせ5個パック")、水出しアイス
コーヒー用バッグ(2種)、CAFECブランドの器具(ドリッパー・フィルター、
5種)、コーヒー保存缶がコーヒー豆単品ではないためNON_BEAN_KEYWORDSで
除外する。残りは単一銘柄・ブレンドの焙煎豆(100g/210g)。

【在庫について】
実データ確認済み: 構造化された品切れフラグが見当たらないため、
商品名のテキストのみで在庫状態を判定する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "FIVE COFFEE STAND&ROASTERY",
    "url": "https://www.fivecoffee.jp/",
    "platform": "BASE",
    "address": "東京都台東区谷中1-3-6",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-09確認。他のBASE系店舗と同一の記述。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://www.fivecoffee.jp"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["ドリップバック", "水出しアイスコーヒー用バッグ", "CAFEC", "保存缶"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


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

    return {"title": title, "price": price}


def build_record(product_url: str, fields: dict) -> dict | None:
    title = fields["title"]
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
            "price": fields["price"],
            "product_url": product_url,
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
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": fields["price"],
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def parse_product_detail(url: str) -> dict | None:
    fields = extract_og_fields(fetch_page(url))
    if not fields:
        return None
    return build_record(url, fields)


def fetch_sitemap_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "/items/" in loc.get_text()]


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_sitemap_urls()
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for product_url in product_urls:
        prev = previous.get(product_url)
        try:
            fields = extract_og_fields(fetch_page(product_url))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue

        if not fields:
            print(f"[warn] OGPメタタグが見つかりません: {product_url}")
            continue
        if is_unchanged(prev, raw_name=fields["title"]):
            records.append(prev)
            continue

        detail = build_record(product_url, fields)
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        result = parse_product_detail(sys.argv[1])
        import json
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        records, flavored_records = scrape_all_products()
        output = {
            "shop": SHOP_INFO,
            "products": records,
            "flavored_products_excluded": flavored_records,
        }
        import json
        with open("data_fivecoffee.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_fivecoffee.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
