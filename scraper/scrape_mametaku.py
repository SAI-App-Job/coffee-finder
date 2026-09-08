# -*- coding: utf-8 -*-
"""
scrape_mametaku.py

豆匠 まめのたくみ(mametakucoffee.com、〒653-0015 兵庫県神戸市長田区菅原通2-108、
自家焙煎豆のオンライン販売)の商品情報を取得する。カラーミーショップ。

robots.txt確認済み(2026-09時点): 他のカラーミー店舗と同一の記述。
User-agent: *に対し/secure/・/cart/のみDisallow。AhrefsBot等一部
ボットを個別にDisallow: /、それ以外は制限なし。

【文字コードについて】
実データ確認済み: レスポンスのContent-Typeヘッダーがcharset=EUC-JPを明示
しており、requestsが自動的に正しくデコードするため特別な対応は不要。

【商品一覧の取得方法について】
実データ確認済み: sitemap.xml(69件のpid付きURL)を商品一覧の取得元とする。
このうち3件(pid=160650294/160651881/160653589)は404となり実在しない
(サイトマップに残った削除済み商品と判断)。取得失敗時はスキップする。

【非コーヒー豆商品の除外について】
実データ確認済み: 全66件取得成功のうちドリップバッグ(単品/3個・5個入/
ギフト)・レギュラーコーヒーギフト(100g×3/4/6の詰め合わせで単一銘柄
ではない)・豆匠オリジナルカフェオレベース(リキッド)・「焙煎屋が本気で
ドリップしたアイスコーヒー(2本セット)」(液体ボトル)が非対象。
NON_BEAN_KEYWORDSで除外する。残り20件(定番ブレンド9種+ストレート等
11種、うち3種は「ネット限定」の200g表記あり)を対象とする。
「アイスブレンド」「アイスコーヒー」を含む銘柄(プレミアムアイス
コーヒー・ケニアアイスブレンド等)は液体ではなく焙煎豆のブレンド名
であるため対象に含める。

【重量について】
実データ確認済み: 商品ページに「ご使用量の目安 200g:コーヒーカップ
約16杯分、100g:コーヒーカップ約7杯分」という定型文が全商品ページに
共通して掲載されているのみで、これは一般的な使用量ガイドであり
商品固有の重量情報ではない(グアテマラ商品でも同一文言を確認)。
Colorme JSON内にも重量フィールドは存在せず(variantsは挽き方違いの
みで価格は全て同額)、商品名に明示的な重量表記がある「ネット限定」
3種(200g)以外はweight_gをNoneとする。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "豆匠 まめのたくみ",
    "url": "https://mametakucoffee.com/",
    "platform": "カラーミーショップ",
    "address": "兵庫県神戸市長田区菅原通2-108",
    "prefecture": "兵庫県",
    "robots_txt_status": "実質許可(2026-09確認。他のカラーミー店舗と同一の記述。"
                          "/secure/・/cart/のみDisallow。AhrefsBot等一部ボットを"
                          "個別にDisallow: /、それ以外は制限なし)",
}

BASE_URL = "https://mametakucoffee.com"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "ドリップバッグ", "レギュラーコーヒーギフト", "カフェオレベース",
    "本気でドリップしたアイスコーヒー",
]
COLORME_PATTERN = re.compile(r"var Colorme\s*=\s*(\{.*?\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ㎏]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_pid_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "pid=" in loc.get_text()]


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
    import json
    data = json.loads(m.group(1))
    product = data.get("product") or {}
    title = re.sub(r"<br\s*/?>", " ", product.get("name") or "").strip()
    title = re.sub(r"\s+", " ", title)
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)
    price = product.get("sales_price_including_tax") or product.get("sales_price")

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": int(price) if price is not None else None,
            "product_url": product_url,
        }

    structural_out_of_stock = product.get("stock_num") == 0
    stock_status = detect_stock_status(title, structural_out_of_stock)
    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = None
    if weight_m:
        weight_g = int(weight_m.group(1)) * 1000 if "㎏" in weight_m.group(0) else int(weight_m.group(1))

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
        "price": int(price) if price is not None else None,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_pid_urls()

    records = []
    flavored_records = []
    for product_url in product_urls:
        try:
            detail = build_record(fetch_page(product_url), product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
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
    with open("data_mametaku.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mametaku.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
