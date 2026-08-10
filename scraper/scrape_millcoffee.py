# -*- coding: utf-8 -*-
"""
scrape_millcoffee.py

MiLL Coffee(baisenmill.com、Wixベース)の商品一覧・詳細ページをパースする。

一覧ページ・詳細ページともHTML構造を確認済み(2026-08時点)。一覧は「もっと見る」
ボタン(JS)によるページ送りだが、SEO用隠しリンクに ?page=N という素直なURL
クエリが仕込まれているため、JS実行なしで全ページ取得できる。

robots.txt確認済み(2026年8月時点): User-agent: * に Allow: / (lightboxクエリのみ除外)。
一般クローラーへの制限なし。

Wixサイトの特徴: data-hook属性が要素の目印として一貫して使われており、
テーマ変更の影響を受けにくく比較的安定したセレクタが組める。
"""

import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "MiLL Coffee",
    "url": "https://www.baisenmill.com/",
    "platform": "Wix",
    "address": "神奈川県川崎市多摩区南生田1-22-23",
    "prefecture": "神奈川県",
    "robots_txt_status": "許可(2026-08確認。User-agent:*にAllow:/、一般クローラーへの制限なし)",
}

CRAWL_DELAY_SECONDS = 10  # Denim bis同様のcourtesy設定を踏襲
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 商品説明(pre[data-hook="description"])内のキー=値パターン
DESC_ORIGIN_PATTERN = re.compile(r"原産国＝([^\n]+)")
DESC_ROAST_HINT_PATTERN = re.compile(r"推奨焙煎度＝([^\n]+)")
DESC_UNIT_PATTERN = re.compile(r"単位＝([^\n]+)")

# 折りたたみセクション(info-section-description)内のパターン
VARIETY_PATTERN = re.compile(r"品種【([^】]+)】")
PRODUCER_PATTERN = re.compile(r"生産者[：:]\s*([^\n]+)")
REGION_DETAIL_PATTERN = re.compile(r"生産地[：:]\s*([^\n]+)")
ALTITUDE_PATTERN = re.compile(r"標高[：:]\s*([^\n]+)")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    # <br>を改行として扱えるようテキストノードに変換しておく
    # (改行なしで連結されると、隣接する項目を正規表現が巻き込む恐れがあるため。
    #  Denim bis実装時に同種の不具合を経験済み)
    for br in soup.find_all("br"):
        br.replace_with("\n")
    return soup


def parse_product_detail(url: str) -> dict:
    """商品詳細ページ1件をパースする。

    フレーバーコーヒー(人工的に香り付けされたコーヒー)は産地・精選方法の
    個性を扱う本アプリの趣旨と異なるため、他の解析より先に判定し、
    該当する場合は産地等の詳細解析を行わず簡略なレコードを返す。
    """
    soup = fetch_page(url)

    name_el = soup.select_one('h1[data-hook="product-title"]')
    price_el = soup.select_one('span[data-hook="formatted-primary-price"]')

    raw_name = name_el.get_text(strip=True) if name_el else ""
    price = None
    if price_el:
        price_digits = re.sub(r"[^\d]", "", price_el.get_text(strip=True))
        price = int(price_digits) if price_digits else None

    parsed = parse_product(raw_name)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": raw_name,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": url,
        }

    desc_el = soup.select_one('pre[data-hook="description"]')

    desc_text = desc_el.get_text() if desc_el else ""
    desc_origin = DESC_ORIGIN_PATTERN.search(desc_text)
    roast_hint = DESC_ROAST_HINT_PATTERN.search(desc_text)
    unit = DESC_UNIT_PATTERN.search(desc_text)

    # 折りたたみセクション(商品情報/生産地情報など、セクション名は店舗依存)
    info_sections = {}
    for li in soup.select('li[data-hook="collapse-info-item"]'):
        title_el = li.select_one('h2[data-hook="info-section-title"]')
        body_el = li.select_one('div[data-hook="info-section-description"]')
        if title_el and body_el:
            info_sections[title_el.get_text(strip=True)] = body_el.get_text()

    product_info_text = info_sections.get("商品情報", "")
    region_info_text = info_sections.get("生産地情報", "")

    variety = VARIETY_PATTERN.search(product_info_text)
    producer = PRODUCER_PATTERN.search(region_info_text)
    region_detail = REGION_DETAIL_PATTERN.search(region_info_text)
    altitude = ALTITUDE_PATTERN.search(region_info_text)

    # 説明文の「原産国＝」表記があれば、商品名パースより優先して信頼する
    # (店舗が明示的に記載しているため、キーワード推測より確実)
    if desc_origin:
        parsed["origin_country"] = desc_origin.group(1).strip()
        parsed["origin_source"] = "product_description"
    parsed = apply_category_hint_fallback(parsed, None)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": raw_name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": None,  # MiLL Coffeeも注文時選択(ロースト・コンディションのドロップダウン)
        "roast_selectable": True,
        "roast_hint": roast_hint.group(1).strip() if roast_hint else None,  # 推奨焙煎度(参考表示)
        "unit_note": unit.group(1).strip() if unit else None,
        "variety_note": variety.group(1).strip() if variety else None,
        "producer_note": producer.group(1).strip() if producer else None,
        "region_detail": region_detail.group(1).strip() if region_detail else None,
        "altitude_note": altitude.group(1).strip() if altitude else None,
        "price": price,
        "product_url": url,
    }


# --- 一覧ページのクロール処理 -------------------------------------------------
# 実データ確認済み(2026-08時点): 商品グリッドは li[data-hook="product-list-grid-item"]。
# 画面上は「もっと見る」ボタン(JS)によるページ送りだが、SEO用の隠しリンク
# (ul[data-hook="product-list-pagination-seo"])に ?page=N という素直なURLクエリが
# 仕込まれているため、JS実行なしで全ページを取得できる。
LIST_BASE_URL = "https://www.baisenmill.com/"


def scrape_product_list_page(page: int) -> list[dict]:
    url = LIST_BASE_URL if page == 1 else f"{LIST_BASE_URL}?page={page}"
    soup = fetch_page(url)
    items = soup.select('li[data-hook="product-list-grid-item"]')

    results = []
    for item in items:
        root = item.select_one('div[data-hook="product-item-root"]')
        link = item.select_one('a[data-hook="product-item-container"]')
        name_el = item.select_one('p[data-hook="product-item-name"]')
        price_el = item.select_one('span[data-hook="product-item-price-to-pay"]')
        oos_el = item.select_one('span[data-hook="product-item-out-of-stock"]')

        if not (root and link and name_el):
            continue

        results.append({
            "slug": root.get("data-slug"),
            "raw_name": name_el.get_text(strip=True),
            "product_url": link.get("href"),
            "price_text": price_el.get("data-wix-price") if price_el else None,
            "out_of_stock": bool(oos_el),
        })
    return results


def scrape_all_products(fetch_details: bool = True, max_pages: int = 20) -> tuple[list[dict], list[dict]]:
    """一覧ページを全ページ辿り、各商品の詳細ページもパースして結合する。

    fetch_details=True の場合、一覧で取得したURLに対しparse_product_detail()を
    呼び出し、産地・精選方法・品種・生産者等の構造化情報まで取得する
    (詳細ページ1件ごとにリクエストが増えるため、courtesy delayを挟む)。

    戻り値は (products, flavored_products) のタプル。フレーバーコーヒーは
    産地・精選方法の個性を扱う本アプリの趣旨と異なる商品カテゴリのため、
    完全に分離して返す(本体のproductsには一切含めない)。
    """
    all_list_items = []
    for page in range(1, max_pages + 1):
        items = scrape_product_list_page(page)
        if not items:
            break
        all_list_items.extend(items)
        time.sleep(CRAWL_DELAY_SECONDS)

    if not fetch_details:
        return all_list_items, []

    records = []
    flavored_records = []
    for item in all_list_items:
        if not item["product_url"]:
            continue
        try:
            detail = parse_product_detail(item["product_url"])
            detail["out_of_stock"] = item["out_of_stock"]
            if detail.get("is_flavored"):
                flavored_records.append(detail)
            else:
                records.append(detail)
            time.sleep(CRAWL_DELAY_SECONDS)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['product_url']} ({e})")

    return records, flavored_records


if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) > 1:
        # 動作確認用: 個別の商品URLを指定してパース結果を確認できる
        result = parse_product_detail(sys.argv[1])
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        records, flavored_records = scrape_all_products()
        output = {
            "shop": SHOP_INFO,
            "products": records,
            # フレーバーコーヒーは産地・精選方法の個性を扱う本アプリの趣旨と異なるため
            # 完全に分離。フロントエンドの通常商品一覧には表示しない
            "flavored_products_excluded": flavored_records,
        }
        with open("data_millcoffee.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_millcoffee.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
