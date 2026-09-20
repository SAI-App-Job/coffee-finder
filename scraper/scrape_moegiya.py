# -*- coding: utf-8 -*-
"""
scrape_moegiya.py

萌季屋(moegiya-coffee-shop.com、千葉県市川市八幡、2005年開業、
スペシャルティコーヒー専門ロースター)の商品情報を取得する。
カラーミーショップ。

robots.txt確認済み(2026-09時点): /secure/・/cart/のみDisallow
(User-agent: *)。AhrefsBot/DotBot/MegaIndex/MJ12bot/PetalBot/
SemrushBot/SEOkicks/serpstatbotを個別にDisallow: /。それ以外は制限なし。

【商品一覧の取得方法について】
実データ確認済み: ナビゲーションのカテゴリ構成(「ブレンドから選ぶ」
「季節限定」「デカフェ」等)が重複表示のため、sitemap.xmlに列挙された
全24件の`?pid=`商品を起点とし、NON_BEAN_KEYWORDSで除外する方式を
採用した(GONZO CAFE&BEANS等と同じパターン)。

【商品情報の取得方法について】
実データ確認済み: 焙煎処 縁の木・豆香房と同じ、商品詳細ページに
埋め込まれたJS変数`var Colorme = {...}`のproduct.name/
sales_price_including_taxから商品名・価格を取得する。

【非コーヒー豆商品の除外について】
実データ確認済み(24件): 「コーヒーバッグ」(ドリップバッグ)、
「ギフトBOX」を含む複数銘柄詰め合わせ(4件)、「水出しコーヒーバッグ」が
コーヒー豆単品ではないためNON_BEAN_KEYWORDSで除外する。残り18件は
ストレート豆・季節ブレンド・デカフェ。

【flavor_notes(2026-09-21追記)】
実データ確認済み: 商品詳細ページのdiv.product-order-exp内に、産地
ストーリーとテイスティング文が地の文で混在する長文があり(対象17件
全てで確認)、一部商品では末尾に「生産国」「地域」「生産者」「標高」
「品種」「農園名」「農園主」「位置」等のラベル付きスペック行、または
「●」で始まる補足見出しセクション(用語解説・ブレンド全般の説明等)が
続く。これらの行が最初に出現する箇所より前を採用する(出現しない商品は
全文を採用)。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "萌季屋",
    "url": "https://moegiya-coffee-shop.com/",
    "platform": "カラーミーショップ",
    "address": "千葉県市川市八幡",
    "prefecture": "千葉県",
    "robots_txt_status": "実質許可(2026-09確認。/secure/・/cart/のみDisallow。"
                          "AhrefsBot等一部ボットを個別にDisallow: /、それ以外は制限なし)",
}

BASE_URL = "https://moegiya-coffee-shop.com"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["コーヒーバッグ", "ギフトBOX", "水出し"]
COLORME_PATTERN = re.compile(r"var Colorme\s*=\s*(\{.*?\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
FLAVOR_STOP_PATTERN = re.compile(
    r"^(生産国|地域|生産者|標高|品種|生産処理プロセス|生産処理|栽培種|農園名|農園主|位置)[\s　]|^●"
)


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def extract_flavor_notes(soup: BeautifulSoup) -> str | None:
    """理由はモジュールdocstring参照。"""
    el = soup.select_one("div.product-order-exp")
    if not el:
        return None
    for br in el.find_all("br"):
        br.replace_with("\n")
    lines = [line.strip() for line in el.get_text().split("\n") if line.strip()]
    flavor_lines = []
    for line in lines:
        if FLAVOR_STOP_PATTERN.match(line):
            break
        flavor_lines.append(line)
    text = "\n".join(flavor_lines).strip()
    return text or None


def fetch_pid_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    urls = []
    for loc in soup.find_all("loc"):
        text = loc.get_text(strip=True)
        if "pid=" in text:
            urls.append(text)
    return urls


def build_record(soup: BeautifulSoup, product_url: str) -> dict | None:
    script_text = ""
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        if "var Colorme" in text:
            script_text = text
            break

    m = COLORME_PATTERN.search(script_text)
    if not m:
        return None
    data = json.loads(m.group(1))
    product = data.get("product") or {}
    title = (product.get("name") or "").strip()
    if not title:
        return None

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
            "price": product.get("sales_price_including_tax") or product.get("sales_price"),
            "product_url": product_url,
        }

    price = product.get("sales_price_including_tax") or product.get("sales_price")
    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None

    structural_out_of_stock = product.get("stock_num") == 0
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
        "flavor_notes": extract_flavor_notes(soup),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price) if price is not None else None,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_pid_urls()
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for product_url in product_urls:
        prev = previous.get(product_url)
        try:
            soup = fetch_page(product_url)
            detail = build_record(soup, product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue

        if detail is None:
            continue
        if is_unchanged(prev, raw_name=detail["raw_name"]):
            records.append(prev)
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        url = sys.argv[1]
        result = build_record(fetch_page(url), url)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        records, flavored_records = scrape_all_products()
        output = {
            "shop": SHOP_INFO,
            "products": records,
            "flavored_products_excluded": flavored_records,
        }
        with open("data_moegiya.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_moegiya.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
