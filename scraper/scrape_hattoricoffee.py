# -*- coding: utf-8 -*-
"""
scrape_hattoricoffee.py

服部珈琲工房(はっとりコーヒー工房、hattori-coffee.shop-pro.jp、島根県松江市
西川津町4003番地BSマンション1F、自家焙煎豆のオンライン販売)の商品情報を
取得する。カラーミーショップ(shop-pro.jp)。公式コーポレートサイト
(hattori-coffee.co.jp)からこのショップへ直接リンクされていることを確認済み。

【住所について】
候補リストの住所(島根県松江市西川津町4003番地BSマンション1F)は、公式
コーポレートサイト(hattori-coffee.co.jp)からのリンク先が本ショップである
ことを確認したうえで、複数の独立した第三者情報源(Yahoo!マップ・ホット
ペッパー等)で一致していることから採用する。本ショップ自体のtokushoho相当
ページに住所記載が見当たらなかったため、コーポレートサイトを実質的な一次
情報源として扱う。

robots.txt確認済み(2026-09時点): 他のカラーミー店舗と同一の記述。
User-agent: *に対し/secure/・/cart/のみDisallow。AhrefsBot等一部ボットを
個別にDisallow: /、それ以外は制限なし。

【対象カテゴリについて】
実データ確認済み: このショップは「コーヒー」(cbid=2466236)カテゴリの他に
福袋・お歳暮・ドリップバッグ・カフェラテベース・水出し珈琲・紅茶・ギフト・
焼き菓子・コーヒー器具・ココア・ジャム・カトラリー等の多数の非コーヒー豆
カテゴリを持つため、「コーヒー」カテゴリのみをクロール対象とする。

【重量違いの重複について】
実データ確認済み(2026-09時点、全12件): 4銘柄(香りのためのぶれんど・酸と酷
のぶれんど・もか・きりまんじゃろ)がそれぞれ100g/200g/500gの3サイズで独立
した商品として登録されている(バリアントではない、重量はvariantsではなく
商品名自体に全角混じりで表記される。例:「香りのためのぶれんど 2００ｇ」)。
NFKC正規化してから商品名の重量表記を検出し、それを除いた基準名でグルーピング
して最小重量(100g)を代表として採用する(タウンコーヒーと同じ方式)。

【非コーヒー豆商品の除外について】
実データ確認済み: 「【定期購入毎月1日12ヶ月】香りのためのぶれんど５００ｇ」
1件のみ定期購入契約のため除外する。

【flavor_notes(2026-09-22追記)】
実データ確認済み: 商品ページのdiv.p-product-explain__body(見出し
「DETAIL」)に対象4件全てで簡潔なテイスティング文が入っている。注文/
配送案内等の無関係な定型文の混入は無いため全文をそのまま採用する。
この店舗の実ページはEUC-JPでエンコードされており(Content-Type:
text/html; charset=EUC-JP)、build_record()が使うfetch_page()は
Colorme JSON(JSエスケープ済みでASCII安全)の解析用にresp.encodingを
強制的にutf-8としているため、このdiv直下の生テキストをそのまま読むと
文字化けする。そのためflavor_notes抽出だけはresp.apparent_encodingで
再取得する専用関数を用いる。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "服部珈琲工房",
    "url": "https://hattori-coffee.shop-pro.jp/",
    "platform": "カラーミーショップ",
    "address": "島根県松江市西川津町4003番地BSマンション1F",
    "prefecture": "島根県",
    "robots_txt_status": "実質許可(2026-09確認。他のカラーミー店舗と同一の記述。"
                          "/secure/・/cart/のみDisallow。AhrefsBot等一部ボットを"
                          "個別にDisallow: /、それ以外は制限なし)",
}

BASE_URL = "https://hattori-coffee.shop-pro.jp"
COFFEE_CATEGORY_URL = f"{BASE_URL}/?mode=cate&cbid=2466236&csid=0"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["定期購入"]
COLORME_PATTERN = re.compile(r"var Colorme\s*=\s*(\{.*?\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def extract_flavor_notes(product_url: str) -> str | None:
    # 理由はモジュールdocstring参照(実ページはEUC-JPだがfetch_page()は
    # Colorme JSON解析用にutf-8を強制するため、ここだけapparent_encodingで
    # 再取得する)
    resp = requests.get(product_url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding
    soup = BeautifulSoup(resp.text, "html.parser")
    el = soup.select_one("div.p-product-explain__body")
    text = el.get_text(strip=True) if el else ""
    return text or None


def fetch_pid_urls() -> list[str]:
    soup = fetch_page(COFFEE_CATEGORY_URL)
    urls = set()
    for a in soup.select('a[href*="pid="]'):
        href = a.get("href", "")
        m = re.search(r"pid=(\d+)", href)
        if m:
            urls.add(f"{BASE_URL}/?pid={m.group(1)}")
    return sorted(urls)


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
    title = re.sub(r"<br\s*/?>", " ", product.get("name") or "").strip()
    title = re.sub(r"\s+", " ", title)
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)

    variants = product.get("variants") or []
    price = product.get("sales_price_including_tax") or product.get("sales_price")

    # 理由はモジュールdocstring参照: このショップは重量違い(100g/200g/500g)が
    # バリアントではなく別商品として登録されているため、重量は商品名から
    # 直接取得する(全角数字混じり表記があるためNFKC正規化してから検出する)。
    normalized_title = unicodedata.normalize("NFKC", title)
    weight_m = WEIGHT_PATTERN.search(normalized_title)
    weight_g = int(weight_m.group(1)) if weight_m else None

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
        "flavor_notes": extract_flavor_notes(product_url),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price) if price is not None else None,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def pick_canonical_products(items: list[dict]) -> list[dict]:
    by_base_name: dict[str, tuple[int, dict]] = {}
    for item in items:
        normalized_title = unicodedata.normalize("NFKC", item["raw_name"])
        weight_key = item["weight_g"] if item["weight_g"] is not None else float("inf")
        base = WEIGHT_PATTERN.sub("", normalized_title)
        base = re.sub(r"\s+", " ", base).strip()
        existing = by_base_name.get(base)
        if existing is None or weight_key < existing[0]:
            by_base_name[base] = (weight_key, item)
    return [item for _weight, item in by_base_name.values()]


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_pid_urls()

    all_items = []
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
            all_items.append(detail)

    records = pick_canonical_products(all_items)

    return records, flavored_records


if __name__ == "__main__":
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_hattoricoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_hattoricoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
