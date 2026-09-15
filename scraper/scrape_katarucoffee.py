# -*- coding: utf-8 -*-
"""
scrape_katarucoffee.py

KATARU COFFEE(カタルコーヒー、www.katarucoffee.com、〒866-0824 熊本県八代市
上日置町4443-1、自家焙煎豆のオンライン販売)の商品情報を取得する。Wix。

【候補リストのドメインについて】
実データ確認済み(2026-09時点): 候補リストの「kataru-coffee.com」はDNS未解決
で接続できない。正しい公式ドメインは「katarucoffee.com」(ハイフン無し)。
本スクレイパーは全リクエストをこちらのURLに送信する。

【営業状況について】
実データ確認済み(2026-09時点): トップページに「一杯から、またはじめよう。
KATARU COFFEEの「RESTART」が始まります」との告知があり、2025年8月から
再起動(RESTART)中であることを確認。2拠点(COFFEE STAND 新八代
〒866-0824熊本県八代市上日置町4443-1、Cafe & Roaster 千丁
〒869-4704熊本県八代市千丁町古閑出704-1)とも現在も掲載されており、
営業自体は継続している(廃業ではない)と判断した。候補リストの住所と一致。

【商品データの取得方法について】
実データ確認済み: Wix Stores標準のstore-products-sitemap.xmlから全商品
ページURLを取得し、各商品ページに埋め込まれたJSON-LD(application/ld+json、
@type: Product)のname・offers.price・offers.availabilityから商品名・価格・
在庫状況を取得する(MiLL Coffeeで採用しているdata-hook属性方式と異なり、
本サイトのテーマではdata-hook要素が確認できなかったため、より安定した
JSON-LD構造化データを採用した)。

【対象商品について】
実データ確認済み(全5件): store-products-sitemap.xmlの5件のうち、実際の
焙煎豆単品は「ダークローストブレンド｜DARK ROAST BREND（深煎り）200g」
(コロンビア・ブラジルのブレンド)の1件のみ。他4件はRESTART GIFT
BOX(オリジナルドリップバッグ×10袋/×5袋)・ドリップバッグコーヒー
【ポスト便】10袋セット・WEB限定KATARUコーヒーセット【ポスト便】(100g×3種/
200g×2種のおまかせセレクト、単一銘柄を特定できない詰め合わせ)のため非対象。
NON_BEAN_KEYWORDSで除外する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "KATARU COFFEE",
    "url": "https://www.katarucoffee.com/",
    "platform": "Wix",
    "address": "熊本県八代市上日置町4443-1",
    "prefecture": "熊本県",
    "robots_txt_status": "許可(2026-09確認。User-agent: *にAllow: /"
                          "[lightboxクエリのみ除外]。一般クローラーへの制限なし)",
}

BASE_URL = "https://www.katarucoffee.com"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["GIFT BOX", "ドリップバッグ", "コーヒーセット", "ポスト便"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
JSONLD_PATTERN = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL)


def fetch_page(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def fetch_product_urls() -> list[str]:
    resp = requests.get(f"{BASE_URL}/store-products-sitemap.xml", headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc")]


def extract_product_jsonld(html: str) -> dict | None:
    for match in JSONLD_PATTERN.finditer(html):
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if data.get("@type") == "Product":
            return data
    return None


def build_record(product_url: str, data: dict) -> dict | None:
    title = (data.get("name") or "").strip()
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    offers = data.get("offers") or {}
    price = None
    if offers.get("price") is not None:
        try:
            price = int(float(offers["price"]))
        except (TypeError, ValueError):
            price = None
    availability = (offers.get("availability") or "").rstrip("/").split("/")[-1]
    structural_out_of_stock = availability not in ("InStock", "")

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

    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None
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


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_product_urls()

    records = []
    flavored_records = []
    for product_url in product_urls:
        try:
            html = fetch_page(product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        data = extract_product_jsonld(html)
        if not data:
            continue
        detail = build_record(product_url, data)
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
    with open("data_katarucoffee.json", "w", encoding="utf-8") as f:
        json_module.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_katarucoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
