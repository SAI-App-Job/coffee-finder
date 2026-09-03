# -*- coding: utf-8 -*-
"""
scrape_azabukobo.py

麻布珈房(あざぶこうぼう、azabukobo.com、東京都港区麻布十番)の商品情報を取得する。
カラーミーショップ(shop-pro.jp)。scrape_kunikuni.pyと同じくパンくずリストの
「焙煎度から選ぶ」グループから8段階の正式なroast_levelを取得できるテーマ。

robots.txt確認済み(2026-09時点): User-agent: *は/secure/・/cart/のみ制限
(nericafe/kunikuni等と同一の記述)。

【対象カテゴリについて】
実データ確認済み: 「＜産地別＞シングルオリジン一覧」(2492517、116件)・
「オリジナルブレンド一覧」(2492851、27件)・「デカフェ一覧」(2543210、15件)の
3カテゴリがコーヒー豆単品を指す。「ドリップバッグ」(2522923、現状0件)・
「定期購入」(2527999)は対象外。シングルオリジンカテゴリはページネーション
(1ページ6件、最大20ページ程度)が必要。

【S/M/Lサイズについて】
実データ確認済み: 同じ銘柄でもS/M/Lサイズごとに別々の商品ページとして
掲載されている(GONZO CAFE&BEANSの重量バリエーション別ページと同じ構成)。
重量はパンくずリストの「サイズから選ぶ」グループのリンクテキストに
「Sサイズ( 生豆時125g、焙煎後 約100g)」のように明記されており、焙煎後の
実重量を正規表現(WEIGHT_ROASTED_PATTERN)で抽出する(生豆時の重量ではなく)。

【焙煎度について】
パンくずリストの「焙煎度から選ぶ」グループ(ミディアム/ハイ/シティ/フルシティ/
フレンチロースト等)がROAST_LEVELSの8段階表記とそのまま一致する店舗自身による
正式な分類であることをkunikuni.pyで確立済み。detect_roast_level_from_breadcrumb()
をそのまま踏襲する。

【商品説明について】
実データ確認済み: og:descriptionは【ラベル】形式ではなく自由記述の紹介文で、
産地情報は「インドネシアのスラウェシ島カロシ地区の豆です」のように文中に
埋め込まれている。構造化ラベルが無いため、産地・精選方法等はparse_product()
による商品名解析が主な情報源となる。

【在庫について】
var Colormeのinventory_controlが"none"、stock_numは常にnull
(kunikuni.pyと同じ運用)。構造化された在庫フラグが機能していないため、
商品名のテキストのみで在庫状態を判定する。
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
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "麻布珈房",
    "url": "https://www.azabukobo.com/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "東京都港区麻布十番",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-09確認。/secure/・/cart/のみ制限。"
                          "nericafe・kunikuni等と同一の記述)",
}

BASE_URL = "https://www.azabukobo.com"
# 理由はモジュールdocstring参照(コーヒー豆単品を指す3カテゴリ)
LIST_CATEGORIES = {
    "2492517": "シングルオリジン",
    "2492851": "オリジナルブレンド",
    "2543210": "デカフェ",
}
CRAWL_DELAY_SECONDS = 1
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*\});", re.DOTALL)
WEIGHT_ROASTED_PATTERN = re.compile(r"焙煎後\s*約\s*([\d.]+)\s*[gｇ]")

# 理由はkunikuni.py参照。「フルシティロースト」が「シティロースト」を
# 部分文字列として含むため、長い方を先に判定する
ROAST_GROUP_LABELS = ["フルシティロースト", "フレンチロースト", "ミディアムロースト", "ハイロースト", "シティロースト"]


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return BeautifulSoup(resp.text, "html.parser")


def extract_colorme_product(soup: BeautifulSoup) -> dict | None:
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        m = COLORME_JSON_PATTERN.search(text)
        if not m:
            continue
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return None
        return data.get("product")
    return None


def detect_roast_level_from_breadcrumb(soup: BeautifulSoup) -> str | None:
    for a in soup.select('ul.pankuzu_lists a[href*="mode=grp"]'):
        text = a.get_text(strip=True)
        for label in ROAST_GROUP_LABELS:
            if text.startswith(label) or label in text:
                return label
    return None


def detect_weight_from_breadcrumb(soup: BeautifulSoup) -> int | None:
    for a in soup.select('ul.pankuzu_lists a[href*="mode=grp"]'):
        text = a.get_text(strip=True)
        m = WEIGHT_ROASTED_PATTERN.search(text)
        if m:
            return int(float(m.group(1)))
    return None


def build_record(product_url: str, colorme_product: dict, roast_level: str | None,
                  weight_g: int | None, category_hint: str) -> dict:
    title = (colorme_product.get("name") or "").strip()
    parsed = parse_product(title)

    variant = colorme_product.get("variants") or [{}]
    price = colorme_product.get("sales_price_including_tax") or variant[0].get("option_price_including_tax")

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

    parsed = apply_category_hint_fallback(parsed, category_hint)
    stock_status = detect_stock_status(title)

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
        "roast_level": roast_level,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def parse_product_detail(url: str, category_hint: str = "") -> dict:
    soup = fetch_page(url)
    colorme_product = extract_colorme_product(soup)
    if not colorme_product:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": "",
            "non_bean": True,
            "product_url": url,
        }
    roast_level = detect_roast_level_from_breadcrumb(soup)
    weight_g = detect_weight_from_breadcrumb(soup)
    return build_record(url, colorme_product, roast_level, weight_g, category_hint)


def scrape_category_list_page(cid: str, page: int) -> list[dict]:
    url = f"{BASE_URL}/?mode=cate&cbid={cid}&csid=0"
    if page > 1:
        url += f"&page={page}"
    soup = fetch_page(url)
    results = []
    for item in soup.select("li.productlist_list"):
        title_el = item.select_one("span.item_name")
        link_el = item.select_one('a[href*="pid="]')
        if not title_el or not link_el:
            continue
        href = link_el.get("href", "")
        product_url = f"{BASE_URL}/{href}" if href.startswith("?") else href
        results.append({"raw_name": title_el.get_text(strip=True), "product_url": product_url})
    return results


def scrape_category_list(cid: str) -> list[dict]:
    all_items: dict[str, dict] = {}
    page = 1
    while True:
        items = scrape_category_list_page(cid, page)
        if not items:
            break
        for item in items:
            all_items[item["product_url"]] = item
        page += 1
        if page > 25:  # 安全弁(想定外の無限ループ防止)
            break
        time.sleep(CRAWL_DELAY_SECONDS)
    return list(all_items.values())


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    items_by_url: dict[str, dict] = {}
    for cid, category_hint in LIST_CATEGORIES.items():
        for item in scrape_category_list(cid):
            items_by_url.setdefault(item["product_url"], {**item, "category_hint": category_hint})

    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for product_url, item in items_by_url.items():
        prev = previous.get(product_url)
        if is_unchanged(prev, raw_name=item["raw_name"]):
            records.append(prev)
            continue

        try:
            detail = parse_product_detail(product_url, item["category_hint"])
            if detail.get("is_flavored"):
                flavored_records.append(detail)
            elif not detail.get("non_bean"):
                records.append(detail)
            time.sleep(CRAWL_DELAY_SECONDS)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")

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
        with open("data_azabukobo.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_azabukobo.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
