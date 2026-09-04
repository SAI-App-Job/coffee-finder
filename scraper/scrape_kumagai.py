# -*- coding: utf-8 -*-
"""
scrape_kumagai.py

熊谷珈琲(shop.kumagaicoffee.com、埼玉県さいたま市大宮区浅間町、
自家焙煎スペシャルティコーヒー専門店。浦和岸町店を含む2拠点)の商品
情報を取得する。カラーミーショップ。

robots.txt確認済み(2026-09時点): 他のカラーミー店舗と同一の記述。
User-agent: *に対し/secure/・/cart/のみDisallow。AhrefsBot等一部
ボットを個別にDisallow: /、それ以外は制限なし。

【商品名の重複構造について】
実データ確認済み(全98件): ほぼ全ての商品が「通常版」と「【店舗受け取り
専用】通常版」(店頭受取専用、内容は同一)のペアで重複登録されている。
「【店舗受け取り専用】」を含む商品は除外し、通常版のみを対象とする。
また同一銘柄について通常サイズ(100g等)の商品とは別に「大容量！...
1kg」という大容量パックが個別商品として登録されているが、実データ
確認済み(全銘柄で確認)で大容量版に対応する通常サイズ版が必ず存在する
ため、「大容量」を含む商品も除外し、通常サイズ版側の最小重量
バリエーションを採用する。

【非コーヒー豆商品の除外について】
実データ確認済み: 「水出しコーヒーパック」「ウェディングドリップ
パック」「ドリップパック7種類飲み比べセット」「クマガイブレンド
ドリップパック15個入り」「水出しコーヒー7個入りセット」「熊谷珈琲の素
（もと）」(コーヒー濃縮液)「コーヒー豆 取り分け用保存袋」がコーヒー豆
単品ではないためNON_BEAN_KEYWORDSで除外する。

【重量・価格について】
実データ確認済み: 商品詳細ページに埋め込まれたJS変数`var Colorme =
{...}`のproduct.variants配列に、各バリエーションの
option1_value(重量+価格、例:「100ｇ（850円）」)・
option2_value(挽き方、例:「豆のまま」)・option_price_including_taxが
構造化データとして入っている。「豆のまま」のうち通常サイズ(お試し
1杯分サイズを除く、後述)の最小重量を代表バリアントとして採用する
(焙煎処 縁の木・豆香房・萌季屋・豆NAKANOと同じColorme系JSON方式だが、
重量・価格が別テーブルではなくvariants配列自体に含まれる点が異なる)。

【お試し1杯分サイズの除外について】
実データ確認済み: 一部商品(超！スペシャルブレンド等)に「20g(お試し
1杯分 390円)」という通常サイズ(100g/250g/500g)とは別枠の小容量
オプションが存在し、これが最小重量のため代表バリアントに選ばれると
実質的な単価が通常サイズの何倍にも見える不自然な表示になる
(390円/20g ≒ 1950円/100g相当 vs 実際の100gは1680円)。
option1_valueに「お試し」を含むオプションは候補から除外し、通常
サイズの中から最小重量を選ぶ。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "熊谷珈琲",
    "url": "https://shop.kumagaicoffee.com/",
    "platform": "カラーミーショップ",
    "address": "埼玉県さいたま市大宮区浅間町2-46",
    "prefecture": "埼玉県",
    "robots_txt_status": "実質許可(2026-09確認。他のカラーミー店舗と同一の記述。"
                          "/secure/・/cart/のみDisallow。AhrefsBot等一部ボットを"
                          "個別にDisallow: /、それ以外は制限なし)",
}

BASE_URL = "https://shop.kumagaicoffee.com"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "水出し", "ドリップパック", "セット", "の素", "保存袋",
    "大容量", "店舗受け取り専用",
]
COLORME_PATTERN = re.compile(r"var Colorme\s*=\s*(\{.*?\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_pid_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    urls = []
    for loc in soup.find_all("loc"):
        text = loc.get_text(strip=True)
        if "pid=" in text:
            urls.append(text)
    return urls


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    bean_variants = [v for v in variants if "豆のまま" in (v.get("option2_value") or "")]
    pool = bean_variants or variants
    # 理由: 一部商品に「20g(お試し1杯分 390円)」のような1杯分お試し
    # サイズが最小重量のオプションとして混在しており、これを代表と
    # すると通常サイズ(100g等)よりはるかに割高な単価に見える不自然な
    # 表示になることを実データで確認済み(超！スペシャルブレンド等)。
    # お試しサイズは除外し、通常サイズの中から最小重量を選ぶ。
    normal_pool = [v for v in pool if "お試し" not in (v.get("option1_value") or "")]
    pool = normal_pool or pool
    candidates = []
    for v in pool:
        m = WEIGHT_PATTERN.search(v.get("option1_value") or "")
        if not m:
            continue
        candidates.append((int(m.group(1)), v))
    if not candidates:
        return None
    return min(candidates, key=lambda c: c[0])[1]


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
    if not title:
        return None

    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)

    variants = product.get("variants") or []
    variant = pick_canonical_variant(variants)
    price = variant.get("option_price_including_tax") if variant else (
        product.get("sales_price_including_tax") or product.get("sales_price")
    )
    weight_g = None
    if variant:
        wm = WEIGHT_PATTERN.search(variant.get("option1_value") or "")
        weight_g = int(wm.group(1)) if wm else None

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
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price) if price is not None else None,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    """理由: 商品一覧がsitemap.xmlのURL列挙のみ(価格・在庫はおろか
    商品名すら含まない)で、豆/非豆の判定自体が詳細ページのColorme
    JSONを見ないとできないため、is_unchanged()による「詳細ページ取得
    前のショートカット」が効かず、結局全件を毎回fetchすることになる
    (アダチコーヒーと同じ理由)。差分判定は行わず、常に詳細ページから
    在庫状態を含めて再導出する。"""
    product_urls = fetch_pid_urls()

    records = []
    flavored_records = []
    for product_url in product_urls:
        try:
            soup = fetch_page(product_url)
            detail = build_record(soup, product_url)
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
        with open("data_kumagai.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_kumagai.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
