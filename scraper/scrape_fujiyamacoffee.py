# -*- coding: utf-8 -*-
"""
scrape_fujiyamacoffee.py

フジヤマコーヒーロースターズ(Fujiyama Coffee Roasters、
fujiyamacoffeeroasters.com、山口県柳井市柳井4827-2、自家焙煎豆のオンライン
販売)の商品情報を取得する。カラーミーショップ(独自ドメインだが実体は
fujiyamacoffee.shop-pro.jpのカラーミーショップ。ページ内のcart/proxy/basket
リンクのshop_id=PA01444079で確認)。

【住所について】
候補リストの住所はgBiz等の検索スニペットに基づくものだったが、本ショップ
自体のtokushoho相当ページに住所記載を確認できなかったため、複数の独立した
第三者情報源(食べログ・柳井市観光協会公式サイト)で一致していた本店住所
(柳井市柳井4827-2)を採用する。

robots.txt確認済み(2026-09時点): 他のカラーミー店舗と同一の記述。
User-agent: *に対し/secure/・/cart/のみDisallow。それ以外は制限なし。

【対象カテゴリについて】
実データ確認済み: このショップはラッキーバッグ・水出しアイスコーヒー
バッグ・ドリップバッグ各種・リキッドコーヒー・コーヒーギフト・コーヒー
器具・食材・冷凍食品(ジェラート)・雑貨(縁起豆シリーズ)等の多数の非コーヒー
豆カテゴリを持つため、「レギュラーコーヒー」カテゴリ(豆売り)のみを
クロール対象とする。

【商品名と産地について】
実データ確認済み(2026-09時点、全12件): 商品名は「【焙煎度】『愛称』
～キャッチコピー～　産地情報」の構成。紅白珈琲(2件)・金魚ちょうちん
ブレンド(2件)・カフェインレス(1件)・産地情報が商品名に無い2件はいずれも
ブレンドで、coffee_parserのブレンド判定キーワード(「ブレンド」等)を含まない
場合はorigin_country・categoryとも既定のストレート寄り判定になる可能性が
あるため断定しない(実データのまま出力する)。ブラジル・グアテマラ・
ニカラグア・エチオピアの産地名を含む4件はストレート判定される。

【重量について】
実データ確認済み: 全12件が単一バリアント(200g、グラム数はoption1_valueの
「200ｇ（2808円）」のような表記に含まれる)。挽き方違いのみでバリアントが
分かれるため、最初のバリアントを代表として使う。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "フジヤマコーヒーロースターズ",
    "url": "https://fujiyamacoffeeroasters.com/",
    "platform": "カラーミーショップ",
    "address": "山口県柳井市柳井4827-2",
    "prefecture": "山口県",
    "robots_txt_status": "実質許可(2026-09確認。他のカラーミー店舗と同一の記述。"
                          "/secure/・/cart/のみDisallow、それ以外は制限なし)",
}

BASE_URL = "https://fujiyamacoffeeroasters.com"
COFFEE_CATEGORY_URL = f"{BASE_URL}/?mode=cate&cbid=2587668&csid=0"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

COLORME_PATTERN = re.compile(r"var Colorme\s*=\s*(\{.*?\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


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
    if not title:
        return None

    parsed = parse_product(title)

    variants = product.get("variants") or []
    price = product.get("sales_price_including_tax") or product.get("sales_price")
    weight_g = None
    if variants:
        normalized = unicodedata.normalize("NFKC", variants[0].get("option1_value") or "")
        weight_m = WEIGHT_PATTERN.search(normalized)
        weight_g = int(weight_m.group(1)) if weight_m else None
        variant_price = variants[0].get("option_price_including_tax") or variants[0].get("option_price")
        if variant_price is not None:
            price = variant_price

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
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_fujiyamacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_fujiyamacoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
