# -*- coding: utf-8 -*-
"""
scrape_tomitaya.py

珈琲の富田屋(やまとの珈琲屋 富田屋、tomitaya.cc、奈良県橿原市今井町1丁目10-17、
注文後焙煎(ロースト・トゥ・オーダー)のオンライン専業自家焙煎豆販売店)の
商品情報を取得する。

プラットフォームについて: 本プロジェクトの確立済み6パターン(BASE/カラーミー/
Shopify/Ocnk/WooCommerce/EC-CUBE)のいずれにも該当しない。実データ確認の
結果、商品カタログ自体はWordPress(独自のitem投稿タイプ、/item/<5桁ID>/形式)
で構成されており、購入(カート)機能のみ外部の「たまごリピート」系カート
サービス(cart.ec-sites.jp、shop.tomitaya.cc)に委譲する構成だった。依頼側の
指示(「may be custom/proprietary — only implement if you find a reliable
low-risk extraction method」)に従い、商品ページ自体は標準的なOGPメタタグと
一貫した価格表示マークアップを持つ低リスクな抽出方法が確認できたため実装
する。

抽出方法について: 各商品ページの<meta property="og:title">から商品名を、
価格表示ブロック(<span class="red_t">￥N</span> /100g（税込）)から100gあたり
単価を取得する。品切れの場合は<p class="soldout_text">完売しました</p>が
価格表示の代わりに出るため、これを構造的な品切れフラグとして扱う。

【100gあたり単価表示について】
実データ確認済み: この店舗は注文後に焙煎するロースト・トゥ・オーダー方式で、
定量パック売り(100g/200g等の固定サイズ)ではなく「800g未満のご購入」
(￥980/100g等)と「800g以上のご購入」(￥840/100g等、まとめ買い割引)の
2段階の100gあたり単価で販売している。本スクレイパーは店舗の基準単価である
800g未満のご購入時(定期購入ではなく通常購入)の単価を採用し、weight_g=100
(100gあたりの代表単位)として1商品1レコードで出力する。

robots.txt確認済み(2026-09時点): 標準的なWordPressのrobots.txtで/wp-admin/
のみDisallow(/item/配下は制限なし)。

【商品一覧の取得方法について】
実データ確認済み: サイト自身のitem-sitemap.xmlには年代物の終売済み商品を
含む245件のURLが列挙されており、現在の実販売ラインナップとは大きく乖離
しているため使わない。代わりに現行商品一覧ページ(/item/、ページネーション
/item/page/N/)を巡回し、そこに列挙された商品(2026-09時点で全18件、2ページ)
を対象とする。

【非コーヒー豆商品の除外について】
実データ確認済み: 全18件のうち「水出しコーヒーバッグ」2件・「ドリップ
バッグ：○○」4件(いずれも粉を個包装したインスタント的な商品で生豆売りの
コーヒー豆とは別カテゴリ)が非対象。NON_BEAN_KEYWORDSで除外する。残り12件
(ストレート11種(うちカフェインレス1種)+ブレンド1種、うち2種は完売中)を
対象とする。

【重量違いの重複について】
該当なし。この店舗の商品ページは1商品1URLで、100gあたり単価のみが掲載
される構成のため、他店舗のような同一銘柄の複数重量商品(200g/500g等の
別URL)への重複排除処理は不要。
"""

import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "珈琲の富田屋",
    "url": "https://tomitaya.cc/",
    "platform": "WordPress独自item投稿タイプ + 外部カート連携"
                "(house未確立パターン。OGPメタタグと価格表示マークアップを情報源として使用)",
    "address": "奈良県橿原市今井町1丁目10-17",
    "prefecture": "奈良県",
    "robots_txt_status": "実質許可(2026-09確認。標準的なWordPressのrobots.txtで"
                          "/wp-admin/のみDisallow、/item/配下は制限なし)",
}

BASE_URL = "https://tomitaya.cc"
CRAWL_DELAY_SECONDS = 0.8
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["ドリップバッグ", "水出しコーヒーバッグ"]
ITEM_URL_PATTERN = re.compile(r"https://tomitaya\.cc/item/\d{5}/")
PRICE_PATTERN = re.compile(r'class="red_t">￥(\d+)</span>\s*/100g')
SOLDOUT_PATTERN = re.compile(r'class="soldout_text">\s*完売しました\s*</p>')
UNIT_WEIGHT_G = 100  # 理由はモジュールdocstring参照(100gあたり単価表示)


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.text


def fetch_all_item_urls() -> list[str]:
    urls = set()
    page = 1
    while True:
        page_url = f"{BASE_URL}/item/" if page == 1 else f"{BASE_URL}/item/page/{page}/"
        html = fetch_html(page_url)
        page_urls = set(ITEM_URL_PATTERN.findall(html))
        if not page_urls or page_urls <= urls:
            break
        urls |= page_urls
        page += 1
        time.sleep(CRAWL_DELAY_SECONDS)
    return sorted(urls)


def build_record(product_url: str) -> dict | None:
    html = fetch_html(product_url)

    title_m = re.search(r'<meta property="og:title" content="([^"]*)"', html)
    if not title_m:
        return None
    title = title_m.group(1).split(" | ")[0].strip()
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)
    price_matches = PRICE_PATTERN.findall(html)
    price = int(price_matches[0]) if price_matches else None
    structural_out_of_stock = bool(SOLDOUT_PATTERN.search(html)) or price is None

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
        "weight_g": UNIT_WEIGHT_G,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_all_item_urls()

    records = []
    flavored_records = []
    for product_url in product_urls:
        try:
            detail = build_record(product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)
        time.sleep(CRAWL_DELAY_SECONDS)

    return records, flavored_records


if __name__ == "__main__":
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_tomitaya.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_tomitaya.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
