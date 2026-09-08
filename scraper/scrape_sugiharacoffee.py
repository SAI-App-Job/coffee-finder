# -*- coding: utf-8 -*-
"""
scrape_sugiharacoffee.py

すぎはらコーヒーロースター(sugihara-coffee.com、大阪府門真市浜町5-24、
自家焙煎豆のオンライン販売)の商品情報を取得する。カラーミーショップ
(shop-pro.jp旧ドメイン: sugiharacoffee.shop-pro.jp)。

robots.txt確認済み(2026-09時点): 他のカラーミー店舗と同一の記述。
User-agent: *に対し/secure/・/cart/のみDisallow。AhrefsBot等一部
ボットを個別にDisallow: /、それ以外は制限なし。

【非コーヒー豆商品の除外について】
実データ確認済み(sitemap.xml上211件): 6ヶ月定期便各種、器具・グッズ類
(KINTOコーヒーサーバー、オリジナルタンブラー/トートバッグ/マグカップ/
キャニスター、フレンチプレス、ペーパーフィルター、コーヒーカップ)、
焼き菓子類(フィナンシェ、クッキー各種、シュトーレン、ガトーショコラ、
ラミントン)、カフェオレベース・アイスコーヒー(瓶入り/ギフト)・水だし
コーヒーパック、ドリップバッグ各種、各種ギフトセット・詰め合わせが
非対象。NON_BEAN_KEYWORDSで除外する。

【重量表記の無い少量商品について】
実データ確認済み: 上記に該当しない銘柄のうち、ほぼ全ての産地銘柄に
「100g」「1kg」の重量表記付き商品と別に、重量表記が無く価格が
194〜300円程度に揃っている商品が存在する(例:「ミャンマー」194円 に対し
「ミャンマー 100g」864円、「ミャンマー 1Kg」6912円)。100g換算だと
極端に安価であり、実際は少量のお試し用/計り売り用の商品と判断できる
(通常サイズと重量スケールが噛み合わないため、そのまま代表商品として
残すとカタログの単価比較を誤らせる)。よって「重量表記が無く、かつ
価格が500円未満」の商品は非対象として除外する。

【重量違いの重複について】
実データ確認済み: 大半の銘柄が100g(定価)/1kg(単価類似)の2サイズで
個別商品登録されている。商品名から末尾の重量表記(1kgの「kg」2文字も
正しく除去)を除き、空白を全て詰めた基準名でグルーピングし、最小重量
(100g)を代表として採用する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "すぎはらコーヒーロースター",
    "url": "https://sugihara-coffee.com/",
    "platform": "カラーミーショップ",
    "address": "大阪府門真市浜町5-24",
    "prefecture": "大阪府",
    "robots_txt_status": "実質許可(2026-09確認。他のカラーミー店舗と同一の記述。"
                          "/secure/・/cart/のみDisallow。AhrefsBot等一部ボットを"
                          "個別にDisallow: /、それ以外は制限なし)",
}

BASE_URL = "https://sugiharacoffee.shop-pro.jp"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "定期便", "ドリップバッグ", "ドリップバック", "カフェオレベース", "アイスコーヒー",
    "ギフト", "セット", "クッキー", "フィナンシェ", "ラミントン", "シュトーレン",
    "ガトーショコラ", "フレンチプレス", "ペーパーフィルター", "マグカップ",
    "キャニスター", "タンブラー", "トートバッグ", "コーヒーサーバー", "コーヒーカップ",
    "水だしコーヒー",
]
COLORME_PATTERN = re.compile(r"var Colorme\s*=\s*(\{.*?\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*(kg|ｋｇ|[gｇ])", re.IGNORECASE)


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_pid_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "pid=" in loc.get_text()]


def extract_fields(soup: BeautifulSoup) -> dict | None:
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

    price = product.get("sales_price_including_tax") or product.get("sales_price")
    price = int(price) if price is not None else None

    weight_m = WEIGHT_PATTERN.search(title)
    if not weight_m and price is not None and price < 500:
        # 重量表記が無く極端に安価な少量お試し/計り売り品(上記docstring参照)
        return None

    structural_out_of_stock = product.get("stock_num") == 0
    return {"title": title, "price": price, "structural_out_of_stock": structural_out_of_stock}


def weight_key(title: str) -> float:
    m = WEIGHT_PATTERN.search(title)
    if not m:
        return float("inf")
    value = int(m.group(1))
    if "k" in m.group(2).lower():
        value *= 1000
    return value


def base_name(title: str) -> str:
    stripped = WEIGHT_PATTERN.sub("", title)
    return re.sub(r"\s+", "", stripped).strip()


def pick_canonical_items(items: list[dict]) -> list[dict]:
    by_base: dict[str, dict] = {}
    for item in items:
        key = base_name(item["title"])
        wkey = weight_key(item["title"])
        existing = by_base.get(key)
        if existing is None or wkey < weight_key(existing["title"]):
            by_base[key] = item
    return list(by_base.values())


def build_record(item: dict, product_url: str) -> dict | None:
    title = item["title"]
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": item["price"],
            "product_url": product_url,
        }

    stock_status = detect_stock_status(title, item.get("structural_out_of_stock", False))
    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = None
    if weight_m:
        weight_g = int(weight_m.group(1)) * 1000 if "k" in weight_m.group(2).lower() else int(weight_m.group(1))

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
        "price": item["price"],
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_pid_urls()

    all_items = []
    url_by_title: dict[str, str] = {}
    for product_url in product_urls:
        try:
            fields = extract_fields(fetch_page(product_url))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if not fields:
            continue
        all_items.append(fields)
        url_by_title[fields["title"]] = product_url

    canonical_items = pick_canonical_items(all_items)

    records = []
    flavored_records = []
    for item in canonical_items:
        detail = build_record(item, url_by_title[item["title"]])
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


if __name__ == "__main__":
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_sugiharacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_sugiharacoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
