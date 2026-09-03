# -*- coding: utf-8 -*-
"""
scrape_ginmame.py

カメヤマ珈琲(ginmame.com、東京都荒川区東日暮里、生豆焙煎専門店)の商品情報を
取得する。WordPressの独自テーマ(Welcart等の既存プロジェクトで見た構造化
class名を持たない、店舗オリジナルのカート実装)。

robots.txt確認済み(2026-09時点、https://www.ginmame.com/robots.txt):
標準的なWordPress設定(/wp-admin/のみDisallow、admin-ajax.phpは例外的にAllow)。
「ginmame.com」(wwwなし)はTLSハンドシェイクに失敗するため、必ず
「www.ginmame.com」でアクセスする。

【商品一覧の取得方法について】
実データ確認済み: カテゴリ別のタクソノミー一覧ページを探したが、コーヒー豆
単体を指すクリーンなカテゴリが見当たらなかったため、`wp-sitemap-posts-post-1.xml`
(全80件、投稿タイプ"post"がそのまま商品ページを兼ねる)を起点とし、
NON_BEAN_KEYWORDSで除外する方式を採用した。カリタ/ハリオ等の器具(ドリッパー・
サーバー・ペーパーフィルター等)、お菓子(ロータスビスケット)、
「セット」「ギフト」を含む福袋・贈答用の詰め合わせ商品が非対象。

【価格・重量について】
実データ確認済み: 商品詳細ページの本文(id="more-N"を含む段落)に
「●200ｇ：1,800円（税込み）」のように複数の重量帯の価格が箇条書きされている。
先頭(最小重量)の行を代表として採用する。

【産地について】
実データ確認済み: 商品名自体に銘柄名(「ゴールデンマンデリン」等)が含まれ
parse_product()で判定できることが多いが、本文に「●原産国⇒インドネシア」
という明示ラベルもあるため、商品名から判定できなかった場合のフォールバックに
使う。
"""

import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_country_name, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "カメヤマ珈琲",
    "url": "https://www.ginmame.com/",
    "platform": "WordPress(独自テーマ)",
    "address": "東京都荒川区東日暮里6-22-14",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-09確認。標準的なWordPress設定。"
                          "/wp-admin/のみDisallow。「www.」無しドメインはTLS接続不可のため"
                          "www.ginmame.comを使用)",
}

BASE_URL = "https://www.ginmame.com"
CRAWL_DELAY_SECONDS = 1
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["カリタ", "ハリオ", "ビスケット", "ギフトボックス", "セット", "ギフト"]
WEIGHT_PRICE_PATTERN = re.compile(r"●\s*(\d+)\s*[ｇg]\s*[：:]\s*([\d,]+)\s*円")
ORIGIN_LABEL_PATTERN = re.compile(r"原産国⇒([^\s<\n]+)")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_sitemap_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/wp-sitemap-posts-post-1.xml")
    return sorted({loc.get_text(strip=True) for loc in soup.find_all("loc") if "/item/" in loc.get_text()})


def build_record(product_url: str, title: str, body_text: str) -> dict | None:
    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)

    weight_price_matches = WEIGHT_PRICE_PATTERN.findall(body_text)
    price = None
    weight_g = None
    if weight_price_matches:
        weights = [(int(w), int(p.replace(",", ""))) for w, p in weight_price_matches]
        weight_g, price = min(weights, key=lambda pair: pair[0])

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

    if not parsed["origin_country"]:
        origin_m = ORIGIN_LABEL_PATTERN.search(body_text)
        if origin_m:
            country = detect_country_name(origin_m.group(1))
            if country:
                parsed["origin_country"] = country
                parsed["origin_source"] = "structural"

    structural_out_of_stock = "itemsoldout" in body_text
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
        "roast_level": parsed["roast_level"],
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def parse_product_detail(url: str) -> dict | None:
    soup = fetch_page(url)
    title_el = soup.select_one('meta[property="og:title"]')
    title = title_el["content"].strip() if title_el and title_el.get("content") else ""
    if not title:
        return None
    body_text = str(soup)
    return build_record(url, title, body_text)


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_sitemap_urls()
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for product_url in product_urls:
        prev = previous.get(product_url)
        try:
            soup = fetch_page(product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue

        title_el = soup.select_one('meta[property="og:title"]')
        title = title_el["content"].strip() if title_el and title_el.get("content") else ""
        if not title:
            continue
        if is_unchanged(prev, raw_name=title):
            records.append(prev)
            continue

        detail = build_record(product_url, title, str(soup))
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)
        time.sleep(CRAWL_DELAY_SECONDS)

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
        with open("data_ginmame.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_ginmame.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
