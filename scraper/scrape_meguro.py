# -*- coding: utf-8 -*-
"""
scrape_meguro.py

COFFEE ROASTERY MEGURO(神奈川県横浜市中区元町・中華街)の商品情報を取得する。
公式サイト(roasterymeguro.com)自体はWordPress製の情報サイトで通販機能を持たず、
実際の販売は別ドメインのBASE(roasterym.base.shop)上で行われている
(実データ確認済み、2026-08時点。「コーヒー豆の説明とご注文はこちらから」ページに
BASEストアへのリンクが1つ置かれているだけで、WordPress側に商品情報は無い)。

NAGI COFFEE(scrape_nagi.py)と同じBASE系プラットフォームだが、テーマが異なる
(実データ確認済み: NAGIはサーバーサイドレンダリングの素朴なHTML、MEGUROは
CSSモジュール風のハッシュ付きクラス名を持つ新しいテーマ。ただしどちらも
価格・商品名・説明文はJS実行なしで取得できるHTML内に含まれている)。

robots.txt確認済み: NAGI COFFEEのTHE SHOPと同一の記述(`curl`/`python-requests`等を
個別にDisallow: /、`User-agent: *`では/items/を含め大部分がAllow)。

【対象商品の絞り込みについて】
sitemap.xml(https://roasterym.base.shop/sitemap.xml)を商品URL一覧の情報源として
使う。ホームページのグリッド表示にページネーションが見当たらず(実データ確認済み:
ホームページの商品数8件とsitemap.xmlの/items/件数8件が一致)、店舗の全商品が
コーヒー豆(ストレート、デカフェ含む)のみで非コーヒー豆商品が見当たらないため、
キーワードベースの非コーヒー豆除外ロジックは持たない。

【焙煎度・挽き方について】
注文オプション(cot-itemOrder-variationName)が「〇浅煎り　ペーパー用に挽きます」
のように焙煎度+挽き方を1つの文字列に連結した形で提供されており、TSUKIKOYA/Mameya
のようなoption1/option2の分離が無い。含まれる浅煎り/中深煎り/深煎りの語を
拾って焙煎度の選択肢として扱う。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    detect_stock_status,
)
from previous_data import load_previous_products

SHOP_INFO = {
    "name": "COFFEE ROASTERY MEGURO",
    "url": "https://roasterymeguro.com/",
    "platform": "BASE",
    "address": "神奈川県横浜市中区元町・中華街",
    "prefecture": "神奈川県",
    "robots_txt_status": "実質許可(2026-08確認。NAGI COFFEEのTHE SHOPと同一の記述。"
                          "/cart/・/web_cart/・/shops/・/api/shops/以外はUser-agent: *でAllow)",
}

CRAWL_DELAY_SECONDS = 2
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

SITEMAP_URL = "https://roasterym.base.shop/sitemap.xml"

ROAST_TERMS = ["浅煎り", "中深煎り", "深煎り"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    return soup


LOC_PATTERN = re.compile(r"<loc>([^<]+)</loc>")


def list_item_urls() -> list[str]:
    # xml.etree/lxml等の追加依存を避けるため、正規表現でシンプルに<loc>を拾う
    # (このプロジェクトのCI環境はrequests/beautifulsoup4のみをインストールする構成)
    resp = requests.get(SITEMAP_URL, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    urls = LOC_PATTERN.findall(resp.text)
    return [u for u in urls if "/items/" in u]


def build_record(product_url: str, title: str, description_text: str, price: int | None) -> dict:
    parsed = parse_product(title)

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

    parsed = apply_category_hint_fallback(parsed, None)

    weight_g = None
    m = WEIGHT_PATTERN.search(title)
    if m:
        weight_g = int(m.group(1))

    decaf_process = None
    if "カフェインレス" in title or "デカフェ" in title:
        decaf_process = "デカフェ(除去方法の詳細記載なし)"

    stock_status = detect_stock_status(title)

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
        "roast_hint": None,
        "roast_selectable": False,
        "post_processing_tags": parsed["post_processing_tags"],
        "farm_note": description_text.strip() if description_text else None,
        "flavor_notes": None,
        "blend_components": [],
        "decaf_process": decaf_process,
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def parse_product_detail(url: str) -> dict:
    soup = fetch_page(url)

    title_el = soup.select_one("[class*='item-detail_itemTitle_']")
    title = title_el.get_text(strip=True) if title_el else ""

    price_el = soup.select_one("[class*='item-detail_price_']")
    price = None
    if price_el:
        price_match = re.search(r"([\d,]+)", price_el.get_text())
        if price_match:
            price = int(price_match.group(1).replace(",", ""))

    desc_el = soup.select_one("[class*='item-detail_description_']")
    description_text = desc_el.get_text() if desc_el else ""

    record = build_record(url, title, description_text, price)

    roast_options = sorted({
        term for el in soup.select("[class*='cot-itemOrder-variationName']")
        for term in ROAST_TERMS if term in el.get_text()
    })
    if roast_options:
        record["roast_hint"] = "／".join(roast_options)
        record["roast_selectable"] = len(roast_options) > 1

    return record


def scrape_all_products() -> tuple[list[dict], list[dict], list[dict]]:
    item_urls = list_item_urls()

    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    non_bean_records = []
    for product_url in item_urls:
        prev = previous.get(product_url)
        # sitemap.xmlは商品名・価格を含まないため、一覧段階での差分判定は行わず、
        # 全商品を毎回detail取得する(店舗規模が小さい=8件程度のため、コストは小さい)
        try:
            detail = parse_product_detail(product_url)
            detail["out_of_stock"] = detail.get("stock_status", "販売中") != "販売中"
            if detail.get("non_bean"):
                non_bean_records.append(detail)
            elif detail.get("is_flavored"):
                flavored_records.append(detail)
            else:
                records.append(detail)
            time.sleep(CRAWL_DELAY_SECONDS)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            if prev:
                records.append(prev)

    return records, flavored_records, non_bean_records


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        result = parse_product_detail(sys.argv[1])
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        records, flavored_records, non_bean_records = scrape_all_products()
        output = {
            "shop": SHOP_INFO,
            "products": records,
            "flavored_products_excluded": flavored_records,
            "non_bean_products_excluded": non_bean_records,
        }
        with open("data_meguro.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_meguro.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件、"
              f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
