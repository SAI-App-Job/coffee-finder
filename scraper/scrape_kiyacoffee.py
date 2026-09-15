# -*- coding: utf-8 -*-
"""
scrape_kiyacoffee.py

木家珈琲倶楽部(kiyacoffee.shop-pro.jp、〒869-0503 熊本県宇城市松橋町きらら
3丁目3-8、自家焙煎豆のオンライン販売)の商品情報を取得する。カラーミー
ショップ(shop-pro.jp)。

【住所について】
特定商取引法ページ(https://kiyacoffee.shop-pro.jp/?mode=sk)で実データ確認済み
(2026-09時点): 「住所」欄に「熊本県宇城市松橋町きらら3丁目3-8」との記載を
確認。候補リストの住所と一致。運営統括責任者名:井上隆一。

robots.txt確認済み(2026-09時点): 他のカラーミー店舗と同一の記述
(User-agent: *はDisallow: /secure/, /cart/のみ。AhrefsBot等の特定クローラー
のみDisallow: /)。本スクレイパーは識別可能な独自User-Agentを使用する。

【文字コード】EUC-JP(実データ確認済み、Content-Type: text/html;
charset=EUC-JP)。他のカラーミー店舗と同じくresp.encodingを明示する。

【対象カテゴリについて】
実データ確認済み(2026-09時点): 「限定珈琲」(cbid=2202962)・「ストレート」
(cbid=1575545)・「ブレンド」(cbid=1575546)の3カテゴリが焙煎豆の対象。
「ドリップバッグ・カフェオレベース・リキッドコーヒー」(cbid=2202221)・
「ギフト」(cbid=1575548)は非対象(ドリップバッグ・詰め合わせセット等)の
ため除外する。各カテゴリとも1ページに収まる件数(34件以下)でページネーション
は無い。

【重量について】
実データ確認済み: 商品名に重量表記が無く、variants配列のtitle
(例:「100g　×　豆のまま」)に挽き方と重量が両方含まれる。product自体の
sales_price_including_taxは最小重量バリアントの価格と一致するため、
wadacoffee.pyと同じ方式(最小価格帯の中から最小重量のバリアントを採用)で
重量を取得する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "木家珈琲倶楽部",
    "url": "https://kiyacoffee.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "熊本県宇城市松橋町きらら3丁目3-8",
    "prefecture": "熊本県",
    "robots_txt_status": "実質許可(2026-09確認。他のカラーミー店舗と同一の"
                          "標準的な記述。User-agent: *はDisallow: /secure/, "
                          "/cart/のみ)",
}

BASE_URL = "https://kiyacoffee.shop-pro.jp"
BEAN_CATEGORY_IDS = ["2202962", "1575545", "1575546"]  # 限定珈琲, ストレート, ブレンド
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["セット", "ドリップバッグ", "ドリップバック", "ギフト", "アソート", "詰め合わせ"]
COLORME_PATTERN = re.compile(r"var Colorme\s*=\s*(\{.*?\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]|(\d+)\s*[Kk][gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-jp"  # 実データ確認済み(Content-Type: text/html; charset=EUC-JP)
    return BeautifulSoup(resp.text, "html.parser")


def scrape_category_list(cid: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    soup = fetch_page(f"{BASE_URL}/?mode=cate&cbid={cid}&csid=0")
    for link in soup.select('a[href*="pid="]'):
        href = link.get("href", "")
        m = re.search(r"pid=(\d+)", href)
        if not m:
            continue
        product_url = f"{BASE_URL}/?pid={m.group(1)}"
        if product_url not in seen:
            seen.add(product_url)
            urls.append(product_url)
    return urls


def extract_colorme_product(soup: BeautifulSoup) -> dict | None:
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        m = COLORME_PATTERN.search(text)
        if not m:
            continue
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return None
        return data.get("product")
    return None


def _weight_from_title(title: str) -> int | None:
    m = re.search(r"(\d+)\s*[Kk][gｇ]", title)
    if m:
        return int(m.group(1)) * 1000
    m = re.search(r"(\d+)\s*[gｇ]", title)
    return int(m.group(1)) if m else None


def pick_min_price_weight(product: dict, price: int | None) -> int | None:
    variants = product.get("variants") or []
    candidates = [v for v in variants if v.get("option_price_including_tax") == price]
    pool = candidates or variants
    if not pool:
        return None
    variant = min(pool, key=lambda v: v.get("option_price_including_tax") or float("inf"))
    return _weight_from_title(variant.get("title") or "")


def build_record(product_url: str, product: dict) -> dict | None:
    title = (product.get("name") or "").strip()
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)
    price = product.get("sales_price_including_tax")

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

    weight_g = pick_min_price_weight(product, price)
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
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def parse_product_detail(url: str) -> dict | None:
    soup = fetch_page(url)
    colorme_product = extract_colorme_product(soup)
    if not colorme_product:
        return None
    return build_record(url, colorme_product)


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls: list[str] = []
    seen: set[str] = set()
    for cid in BEAN_CATEGORY_IDS:
        for url in scrape_category_list(cid):
            if url not in seen:
                seen.add(url)
                product_urls.append(url)

    records = []
    flavored_records = []
    for product_url in product_urls:
        try:
            detail = parse_product_detail(product_url)
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
    import json as json_module

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_kiyacoffee.json", "w", encoding="utf-8") as f:
        json_module.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kiyacoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
