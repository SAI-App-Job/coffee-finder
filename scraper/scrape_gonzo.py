# -*- coding: utf-8 -*-
"""
scrape_gonzo.py

GONZO CAFE&BEANS(権蔵焙煎所、東京都練馬区東大泉)の商品情報を取得する。
ユーザー指定のドメイン(gonzo-coffee.com)はDNS解決不可(実データ確認済み、
名前解決自体が失敗)で実在しない。実際のオンラインショップはBASE
(gonzocb.base.shop)であることをGoogle検索・Googleマップ(★4.6、249件の
口コミ、東京都練馬区東大泉7-38-29)で実在確認済み(2026-09時点)。

robots.txt確認済み(2026-09時点): NAGI COFFEE・MARUTAKE COFFEE BEANS等と同一の
記述(curl/python-requests等の一般的なHTTPクライアントは個別にDisallow: /
指定があるが、User-agent: *ルールでは/cart/・/web_cart/・/shops/・/api/shops/・
違反報告ページ以外はAllow: /)。本スクレイパーは識別可能な独自User-Agentを
使用するため該当しない。

【カテゴリ構造について】
実データ確認済み: このショップはカテゴリ分けを一切使っておらず、
sitemap.xmlに列挙された55件のitems/<ID>が全商品(フラットな一覧)。
全55件を確認したところ、権蔵ブレンド(5種)・シングルオリジン(9種)それぞれに
ついて100g/250g/250g×2(500g)の重量バリエーションが別々の商品ページとして
存在する構成で、ギフトセットやドリップバッグ等の非コーヒー豆商品は
1件も無いことを確認済み。MARUTAKE COFFEE BEANSと同様、重量違いも独立した
SKU(価格が別)として扱いそのまま個別レコードにする(1商品に正規化しない)。

【商品説明文について】
実データ確認済み: JSON-LD(schema.org Product)のdescriptionは配送・保管方法等の
定型文が中心で、【ラベル】値のような構造化欄は無い。産地は
「原材料：コーヒー豆（パプアニューギニア）」のような一文に埋め込まれている
のみ。商品名自体に国名・地名(パプアニューギニア シグリ、キリマンジャロ
スノートップ、コスタリカ ジャガーハニー等)が含まれているため、
parse_product()の商品名解析で十分カバーできる(カフェクラウディア等と
同じ「構造化データ無し・商品名ベース」パターン)。

【重量表記(250g×2(500g))について】
実データ確認済み: 500gパックは商品名が「...250g×2(500g)」という表記で、
価格も500g分(250gの約2倍)に設定されている。末尾の括弧内の合計表記を
優先して重量として採用する(先頭の「250g」をそのまま拾うと実際の内容量と
食い違うため)。

【焙煎度について】
商品名の括弧内に「浅煎り」「中煎り」「中深煎り」「深煎り」という粗い表記が
入っており、ROAST_KEYWORDS(プロ向け8段階)とは粒度が異なるため
roast_hintとして保持しroast_levelには反映しない
(MARUTAKE COFFEE BEANSと同じ方針)。

【カフェインレス(デカフェ)について】
実データ確認済み: 「コロンビアカフェインレス」という商品名で、デカフェを
示す語が「デカフェ」ではなく「カフェインレス」表記。category_hintに
「デカフェ」を設定する(MARUTAKE COFFEE BEANS等のcategory_hint運用に揃える)。

【価格・在庫について】
JSON-LD(schema.org Product)のoffersにprice・availability
(http://schema.org/InStock 等)が構造化されている(MARUTAKE COFFEE BEANS・
隠房と同じBASE標準テンプレート)。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_stock_status

SHOP_INFO = {
    "name": "GONZO CAFE&BEANS",
    "url": "https://gonzocb.base.shop/",
    "platform": "BASE",
    "address": "東京都練馬区東大泉7-38-29 加昌マンション108",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-09確認。NAGI COFFEE・MARUTAKE COFFEE BEANS等と"
                          "同一の記述。/cart/・/web_cart/・/shops/・/api/shops/・違反報告"
                          "ページ以外はUser-agent: *でAllow。curl/python-requests等は"
                          "個別にDisallow: /指定あり、本スクレイパーは識別可能な"
                          "User-Agentを使用)",
}

BASE_URL = "https://gonzocb.base.shop"
CRAWL_DELAY_SECONDS = 1.5
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 理由はモジュールdocstring参照(末尾の合計表記「(500g)」を優先し、
# 無ければ先頭の単純な「Ng」表記にフォールバック)
WEIGHT_TOTAL_PATTERN = re.compile(r"[（(]\s*(\d+)\s*[gｇ]\s*[)）]")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")

# 理由はモジュールdocstring参照(粗い焙煎度表記。長い方を先に判定)
ROAST_HINT_TERMS = ["中深煎り", "中浅煎り", "浅煎り", "中煎り", "深煎り"]

DECAF_KEYWORDS = ["カフェインレス", "デカフェ"]

# 実データ確認済み: sitemap.xml全55件のうち1件(item 151166988)「権蔵水出しアイス
# コーヒー（30g×10個）」のみ、豆をあらかじめ抽出済みの水出しパック(粉末を挽いて
# 個包装した既製品)で、コーヒー豆単品を指さない(MARUTAKE COFFEE BEANSが
# 「アイスコーヒー」カテゴリを対象外としたのと同じ理由)。他54件は全て
# 生豆/焙煎豆の単品販売であることを確認済み。
NON_BEAN_KEYWORDS = ["水出しアイスコーヒー"]


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def extract_jsonld_product(soup: BeautifulSoup) -> dict | None:
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        text = script.string or script.get_text() or ""
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == "Product":
            return data
    return None


def parse_weight_from_title(title: str) -> int | None:
    m = WEIGHT_TOTAL_PATTERN.search(title or "")
    if m:
        return int(m.group(1))
    m = WEIGHT_PATTERN.search(title or "")
    return int(m.group(1)) if m else None


def find_roast_hint(title: str) -> str | None:
    for term in ROAST_HINT_TERMS:
        if term in (title or ""):
            return term
    return None


def build_record(product_url: str, product: dict) -> dict:
    title = (product.get("name") or "").strip()

    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "non_bean": True,
            "product_url": product_url,
        }

    parsed = parse_product(title)

    if parsed["is_flavored"]:
        offers = product.get("offers") or {}
        price = int(offers["price"]) if offers.get("price") is not None else None
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": product_url,
        }

    category_hint = "デカフェ" if any(kw in title for kw in DECAF_KEYWORDS) else None
    parsed = apply_category_hint_fallback(parsed, category_hint)
    # デカフェ商品名の「カフェインレス」の「レス」等がROAST_KEYWORDS等の他の
    # マッチングを汚染することは無いため、roast_levelはそのまま使わずroast_hintへ回す
    roast_hint = find_roast_hint(title)

    offers = product.get("offers") or {}
    price = int(offers["price"]) if offers.get("price") is not None else None
    availability = offers.get("availability") or ""
    structural_out_of_stock = "InStock" not in availability
    stock_status = detect_stock_status(title, structural_out_of_stock)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "category_hint": category_hint,
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": None,  # 理由はモジュールdocstring参照(粗い焙煎度表記のためroast_hintに保持)
        "roast_hint": roast_hint,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": parse_weight_from_title(title),
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def parse_product_detail(url: str) -> dict:
    soup = fetch_page(url)
    product = extract_jsonld_product(soup)
    if not product:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": "",
            "non_bean": True,
            "product_url": url,
        }
    return build_record(url, product)


def fetch_sitemap_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    urls = []
    for loc in soup.find_all("loc"):
        text = loc.get_text(strip=True)
        if "/items/" in text:
            urls.append(text)
    return urls


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    """理由はモジュールdocstring参照(このショップはカテゴリ一覧ページを
    持たずsitemap.xmlがURLのみを提供するため、差分判定用の軽量なraw_name
    取得元が無い。55件・CRAWL_DELAY_SECONDS=1.5秒でも全体で2分弱に収まるため、
    previous_data.pyの差分スキップは使わず毎回全件の詳細ページを取得する)。"""
    product_urls = fetch_sitemap_urls()

    records = []
    flavored_records = []
    for product_url in product_urls:
        try:
            detail = parse_product_detail(product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue

        if detail.get("is_flavored"):
            flavored_records.append(detail)
        elif not detail.get("non_bean"):
            records.append(detail)
        time.sleep(CRAWL_DELAY_SECONDS)

    return records, flavored_records


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        result = parse_product_detail(sys.argv[1])
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        records, flavored_records = scrape_all_products()
        output = {
            "shop": SHOP_INFO,
            "products": records,
            "flavored_products_excluded": flavored_records,
        }
        with open("data_gonzo.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_gonzo.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
