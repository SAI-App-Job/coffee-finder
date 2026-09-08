# -*- coding: utf-8 -*-
"""
scrape_hareruyacoffee.py

晴天屋珈琲焙煎所(hareruya-coffee.com、実店舗のオンラインストアは
hareruya-coffee.shop-pro.jp、兵庫県尼崎市武庫之荘5-13-5、自家焙煎豆の
オンライン販売)の商品情報を取得する。カラーミーショップ/Shop-Proファミリー
(旧ブランドのshop-pro.jpドメイン)。

robots.txt確認済み(2026-09時点): 他のカラーミー店舗と同一の記述。
User-agent: *に対し/secure/・/cart/のみDisallow。AhrefsBot等一部
ボットを個別にDisallow: /、それ以外は制限なし。

【文字コードについて】
実データ確認済み: 本サイトはEUC-JPでエンコードされている(他のカラーミー
店舗はUTF-8が多いが、HTTPヘッダのContent-Type: text/html; charset=EUC-JPを
requestsが正しく読み取り自動デコードするため、明示的な文字コード指定は
不要)。

【重量・グラインド違いの重複について】
実データ確認済み: 全24件のうち豆商品は「豆のまま/粗挽き/中挽き/細挽き」
×「100g/250g/500g」の12バリアントを持つ。product直下のsales_price_
including_taxは常に「豆のまま×100g」バリアントの価格と一致することを
確認済みのため、variants配列から「豆のまま」かつ最小重量(100g)の
バリアントを明示的に選んで採用する(basecoffeeclassicと同じ方式)。

【非コーヒー豆商品の除外について】
実データ確認済み: 全24件のうち「お得な定期購入」(銘柄非依存の定期便)・
「晴天猫魔法堂のドリップバッグ」「ドリップバッグ「旅人のお気に入り」
（大容量15g入）」「Diamond ドリップバッグ」「ドリップバッグ「麒麟」
（大容量15g入）」「晴天屋一周年記念　６０％OFF チャーム付 ワイン
バレルエイジド ドリップバッグ１０個入」(ドリップバッグ各種)が非対象。
NON_BEAN_KEYWORDSで除外する。残り18件(デカフェ・ロカフェインブレンド・
コールドブリューブレンドを含む)を対象とする。
"""

import json
import re

import requests

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "晴天屋珈琲焙煎所",
    "url": "https://hareruya-coffee.com/",
    "platform": "カラーミーショップ(Shop-Pro)",
    "address": "兵庫県尼崎市武庫之荘5-13-5",
    "prefecture": "兵庫県",
    "robots_txt_status": "実質許可(2026-09確認。他のカラーミー店舗と同一の記述。"
                          "/secure/・/cart/のみDisallow。AhrefsBot等一部ボットを"
                          "個別にDisallow: /、それ以外は制限なし)",
}

BASE_URL = "https://hareruya-coffee.shop-pro.jp"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["定期購入", "ドリップバッグ"]
COLORME_PATTERN = re.compile(r"var Colorme\s*=\s*(\{.*?\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> requests.Response:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp


def fetch_pid_urls() -> list[str]:
    resp = fetch_page(f"{BASE_URL}/sitemap.xml")
    urls = re.findall(r"<loc>([^<]*pid=[^<]*)</loc>", resp.text)
    return [u.replace("&amp;", "&") for u in urls]


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    if not variants:
        return None

    def weight_key(v):
        m = WEIGHT_PATTERN.search(v.get("option2_value") or "")
        return int(m.group(1)) if m else float("inf")

    def is_whole_bean(v):
        return "豆のまま" in (v.get("option1_value") or "")

    whole_bean = [v for v in variants if is_whole_bean(v)] or variants
    return min(whole_bean, key=weight_key)


def build_record(resp: requests.Response, product_url: str) -> dict | None:
    m = COLORME_PATTERN.search(resp.text)
    if not m:
        return None
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

    variant = pick_canonical_variant(product.get("variants") or [])
    weight_g = None
    if variant:
        wm = WEIGHT_PATTERN.search(variant.get("option2_value") or "")
        weight_g = int(wm.group(1)) if wm else None
        variant_price = variant.get("option_price_including_tax") or variant.get("option_price")
        if variant_price is not None:
            price = variant_price

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
    with open("data_hareruyacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_hareruyacoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
