# -*- coding: utf-8 -*-
"""
scrape_leafletter.py

LEAFLETTER(神奈川県川崎市幸区柳町)の商品情報を取得する。BASE
(leafletter.official.ec)、COFFEE ROASTERY MEGURO(scrape_meguro.py)と
同じCSSモジュール風の新しいBASEテーマ(実データ確認済み、2026-08時点。
一覧はitems-grid_itemTitleText_*、詳細ページはitem-detail_itemTitle_*/
item-detail_price_*/item-detail_description_*、いずれもハッシュ付き
クラス名だが構造はMEGUROと同一)。

robots.txt確認済み: NAGI COFFEEのTHE SHOP・COFFEE ROASTERY MEGUROのBASEと
同一の記述(`curl`/`python-requests`等を個別にDisallow: /、`User-agent: *`では
/items/を含め大部分がAllow)。

【対象商品の絞り込みについて】
sitemap.xml(https://leafletter.official.ec/sitemap.xml)を商品URL一覧の
情報源として使う(実データ確認済み: ホームページ・/items/allページの
商品数14件とsitemap.xmlの/items/件数14件が一致)。

【焙煎度・注文オプションについて】
商品名末尾に「※浅煎り」「※中深煎り」という焙煎度表記が固定で付与されており、
MEGUROと異なり焙煎度自体を選ぶ注文オプションは無い(挽き方(豆のまま/粉)の
選択肢のみ、実データ確認済み)。説明文中の「焙煎度：」ラベルからも同じ値を
確認できるが、ROAST_LEVELS(8段階のカタカナ表記)とは粒度が異なる簡易表記
(浅煎り/中深煎り)のためroast_hintとして保持しroast_levelは未設定とする。

【非コーヒー豆商品について】
「【水出しコーヒーバッグ】2バッグ入り」という水出し用ドリップバッグ商品が
1件確認できたため(実データ確認済み)、キーワードで除外する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    normalize_processing_method,
    detect_stock_status,
)
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "LEAFLETTER",
    "url": "https://leafletter.official.ec/",
    "platform": "BASE",
    "address": "神奈川県川崎市幸区柳町8-3 柳町ビル101",
    "prefecture": "神奈川県",
    "robots_txt_status": "実質許可(2026-08確認。COFFEE ROASTERY MEGURO等のBASEと同一の記述。"
                          "/cart/・/web_cart/・/shops/・/api/shops/以外はUser-agent: *でAllow)",
}

REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

SITEMAP_URL = "https://leafletter.official.ec/sitemap.xml"
LOC_PATTERN = re.compile(r"<loc>([^<]+)</loc>")

# 実データ確認済み(2026-08時点): コーヒー豆ではない商品(水出しドリップバッグ)
NON_BEAN_KEYWORDS = ["水出し", "バッグ入り"]

WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
LABEL_PATTERN = re.compile(r"(容量|焙煎度|精製処理|標高|品種|テイスティングノート|カフェイン除去法)：\s*([^\n]+)")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    return soup


def list_item_urls() -> list[str]:
    resp = requests.get(SITEMAP_URL, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    urls = LOC_PATTERN.findall(resp.text)
    return [u for u in urls if "/items/" in u]


def build_record(product_url: str, title: str, description_text: str, price: int | None,
                  sold_out: bool) -> dict:
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

    labels = {label: value.strip() for label, value in LABEL_PATTERN.findall(description_text or "")}

    if labels.get("精製処理") and not parsed["processing_method"]:
        parsed["processing_method"] = normalize_processing_method(labels["精製処理"])
    parsed = apply_category_hint_fallback(parsed, None)

    weight_g = None
    if labels.get("容量"):
        m = WEIGHT_PATTERN.search(labels["容量"])
        if m:
            weight_g = int(m.group(1))
    if weight_g is None:
        m = WEIGHT_PATTERN.search(title)
        if m:
            weight_g = int(m.group(1))

    farm_note_parts = []
    if labels.get("標高"):
        farm_note_parts.append(f"標高: {labels['標高']}")
    if labels.get("品種"):
        farm_note_parts.append(f"品種: {labels['品種']}")
    farm_note = "、".join(farm_note_parts) if farm_note_parts else None

    decaf_process = labels.get("カフェイン除去法")

    stock_status = detect_stock_status(title, sold_out)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": None,  # 「浅煎り/中深煎り」の簡易表記でROAST_LEVELSの8段階と粒度が異なるため未設定
        "roast_hint": labels.get("焙煎度"),
        "roast_selectable": False,  # 焙煎度は商品ごとに固定、注文時に選べるのは挽き方のみ(実データ確認済み)
        "post_processing_tags": parsed["post_processing_tags"],
        "farm_note": farm_note,
        "flavor_notes": labels.get("テイスティングノート"),
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

    sold_out = soup.select_one("[class*='item-detail_soldOut_']") is not None

    desc_el = soup.select_one("[class*='item-detail_description_']")
    description_text = desc_el.get_text() if desc_el else ""

    return build_record(url, title, description_text, price, sold_out)


def scrape_all_products() -> tuple[list[dict], list[dict], list[dict]]:
    item_urls = list_item_urls()

    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    non_bean_records = []
    for product_url in item_urls:
        prev = previous.get(product_url)
        # sitemap.xmlは商品名・価格を含まないため一覧段階での差分判定は行わず、
        # 全商品を毎回detail取得する(店舗規模が小さい=14件程度のため、コストは小さい)
        try:
            detail = parse_product_detail(product_url)
            title = detail.get("raw_name", "")
            if any(kw in title for kw in NON_BEAN_KEYWORDS):
                non_bean_records.append({
                    "shop_name": SHOP_INFO["name"],
                    "raw_name": title,
                    "non_bean": True,
                    "product_url": product_url,
                })
                continue
            detail["out_of_stock"] = detail.get("stock_status", "販売中") != "販売中"
            if detail.get("is_flavored"):
                flavored_records.append(detail)
            else:
                records.append(detail)
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
        with open("data_leafletter.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_leafletter.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件、"
              f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
