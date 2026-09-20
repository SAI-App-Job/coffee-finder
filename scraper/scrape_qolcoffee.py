# -*- coding: utf-8 -*-
"""
scrape_qolcoffee.py

Q.O.L.COFFEE(qolcoffee.com、愛知県名古屋市中区丸の内3-5-1、自家焙煎豆の
オンライン販売。本店+BREWERS PARCOの2店舗を展開)の商品情報を取得する。
WordPress+WooCommerce。

robots.txt確認済み(2026-09時点): User-agent: *に対し/wp-admin/等の管理系
パスのみDisallow(admin-ajax.phpは個別にAllow)。本スクレイパーが使う
エンドポイントは制限対象外。

【Store APIのエンドポイントについて】
実データ確認済み: 他店(dots Coffee Roasters・ひつじ珈琲)と異なり、本店の
WooCommerceバージョンではStore APIのルートに"v1"segmentが無く、
`/wp-json/wc/store/products`(v1無し)が正しいエンドポイントである
(`/wp-json/wc/store/v1/products`は404になる)。`/wp-json/`のnamespaces一覧
で実際に登録されているルートを確認して判明した。

【重量バリエーションについて】
実データ確認済み: 焙煎豆商品は全て「内容量(pa_g: 100g/200g/500g)」×
「豆の状態(pa_jyoutai: mame=豆のまま/kona=粉)」のWooCommerce変動
商品(variable product)であり、Store APIの商品一覧(`/wc/store/products`)
ではprices.priceに既に最小重量(100g)の代表価格が入っている(=一覧の値を
そのまま使って良い)が、重量(g)自体は一覧レスポンスに含まれないため、
各商品の通常ページHTMLに埋め込まれたWooCommerce標準の
`data-product_variations`属性(HTMLエンティティ化されたJSON)を別途取得し、
attribute_pa_g(重量)・attribute_pa_jyoutai(豆/粉)から在庫があるバリアント
の中で最小重量かつ「豆のまま(mame)」を優先して代表を選ぶ。

【非コーヒー豆商品の除外について】
実データ確認済み: 全80商品のうち、実際の焙煎豆単品は23件程度で、残りは
以下の非対象カテゴリ:
・業務用1kgサイズ(通常サイズと重複する別商品、14件、「業務用」で除外)
・HARIO/KINTO/CAFEC/ORIGAMI/AEROPRESS/Abaca等の器具
・PRANA CHAI・MINOR FIGURES BARISTA OAT・アーモンド効果・Bonsoy(チャイ・
  オーツミルク・アーモンドミルク・豆乳、コーヒー豆ではない)
・カフェオレベース(液体)
・COLD BREW COFFEE(水出しコーヒー用の抽出パック、粗挽き豆をパック
  詰めした単回抽出用製品でドリップバッグと同種のため対象外)
・ドリップバッグ全種
・Q.O.L. MUG/タンブラー/Tシャツ/缶バッジ/ステッカー/手ぬぐい等のグッズ
・GIFT BOX各種(詰め合わせ)
・スペシャルティコーヒーお試しセット(複数銘柄の詰め合わせ)
・センサリーカリブレーションセミナー(トレーニングイベントの参加券)
NON_BEAN_KEYWORDSで除外する。「ICED COFFEE BLEND」はアイス抽出用の
ブレンド豆(粉ではなく豆/粉選択式の通常商品)であることを商品ページで
確認済みのため対象に含める。

【flavor_notes(2026-09-20追記)】
実データ確認済み: 詳細ページのdd.c-detail-data__desc内は<p>要素単位で
段落が分かれており、多くの商品は最初の1〜2段落に実際のテイスティング文が
入っている。その後に「農園」「地域」「品種」「精製」「標高」「カップ」や
英語版「Producer」「Origin」「Area」「Variety」等の構造化ラベルで始まる
段落が続く(日本語/英語ラベルが混在し、コロン付き・スペース区切りいずれも
ある)。これらのラベルパターンに最初に一致した段落の直前までを結合して
flavor_notesとして採用する。詳細ページは重量バリエーション取得(data-
product_variations属性)と同じHTML取得を再利用するため追加のHTTPアクセス
は不要。
"""

import html
import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "Q.O.L.COFFEE",
    "url": "https://qolcoffee.com/",
    "platform": "WooCommerce",
    "address": "愛知県名古屋市中区丸の内3-5-1",
    "prefecture": "愛知県",
    "robots_txt_status": "実質許可(2026-09確認。/wp-admin/等の管理系パスのみ"
                          "Disallow。本スクレイパーが使うエンドポイントは制限対象外)",
}

API_URL = "https://qolcoffee.com/wp-json/wc/store/products"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "業務用", "セミナー", "HARIO", "KINTO", "CAFEC", "ORIGAMI", "AERO PRESS", "Abaca",
    "MUG", "タンブラー", "T-shirt", "Tシャツ", "ロゴT", "缶バッジ", "ステッカー", "手ぬぐい",
    "シロップ", "PRANA CHAI", "BARISTA OAT", "アーモンド効果", "Bonsoy", "カフェオレベース",
    "COLD BREW", "ドリップバッグ", "GIFT BOX", "お試しセット", "招待状",
]
FLAVOR_LABEL_PARAGRAPH_PATTERN = re.compile(
    r"^(?:[\-—]?\s*(?:ORIGIN|TASTE\s*NOTE)\s*[\-—]?"
    r"|国|地\s*域|農\s*園(?:主)?|生産者|生産地|品\s*種|精\s*製方?法?|標\s*高|カップ|発\s*酵"
    r"|プロデューサー|輸入元|輸入業者|輸出|栽培面積"
    r"|Producer|Origin|Area|Farm|Variety|Processing|Drying|Crop\s*year|Harvest\s*Period"
    r"|Altitude|Score|Cup|Exporter|Inporter|Dry\s*mill|Sensory\s*profile|Moisture|Density"
    r"|Date\s*of\s*arrival|Elevation|Process)\s*[:：\s]",
    re.IGNORECASE,
)
WEIGHT_ATTR_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
VARIATIONS_PATTERN = re.compile(r'data-product_variations="([^"]*)"')


def fetch_all_products() -> list[dict]:
    products = []
    page = 1
    while True:
        resp = requests.get(
            API_URL, headers=REQUEST_HEADERS, params={"per_page": 100, "page": page}, timeout=20
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        products.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return products


def fetch_detail_page(permalink: str) -> tuple[list[dict], BeautifulSoup]:
    resp = requests.get(permalink, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    variations = []
    m = VARIATIONS_PATTERN.search(resp.text)
    if m:
        try:
            variations = json.loads(html.unescape(m.group(1)))
        except json.JSONDecodeError:
            variations = []
    return variations, BeautifulSoup(resp.text, "html.parser")


def extract_flavor_notes(soup: BeautifulSoup) -> str | None:
    """理由はモジュールdocstring参照。"""
    el = soup.select_one("dd.c-detail-data__desc")
    if not el:
        return None
    kept = []
    for p in el.find_all("p"):
        text = p.get_text(" ", strip=True)
        if not text:
            continue
        if FLAVOR_LABEL_PARAGRAPH_PATTERN.match(text):
            break
        kept.append(text)
    return " ".join(kept) if kept else None


def pick_canonical_variation(variations: list[dict]) -> tuple[dict | None, int | None]:
    if not variations:
        return None, None

    def weight_of(v):
        m = WEIGHT_ATTR_PATTERN.search(v.get("attributes", {}).get("attribute_pa_g") or "")
        return int(m.group(1)) if m else float("inf")

    def is_whole_bean(v):
        return v.get("attributes", {}).get("attribute_pa_jyoutai") == "mame"

    in_stock = [v for v in variations if v.get("is_in_stock")]
    pool = in_stock or variations
    whole_bean_pool = [v for v in pool if is_whole_bean(v)] or pool
    variation = min(whole_bean_pool, key=weight_of)
    weight = weight_of(variation)
    return variation, (weight if weight != float("inf") else None)


def build_record(product: dict) -> dict | None:
    title = (product.get("name") or "").strip()
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)
    product_url = product.get("permalink")
    price = product.get("prices", {}).get("price")
    price = int(price) if price is not None else None

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

    weight_g = None
    flavor_notes = None
    structural_out_of_stock = not product.get("is_in_stock", True)
    if product.get("has_options") and product_url:
        try:
            variations, soup = fetch_detail_page(product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            variations, soup = [], None
        variation, weight_g = pick_canonical_variation(variations)
        if variation is not None:
            structural_out_of_stock = not bool(variations) or not any(
                v.get("is_in_stock") for v in variations
            )
            if variation.get("display_price") is not None:
                price = int(variation["display_price"])
        if soup is not None:
            flavor_notes = extract_flavor_notes(soup)

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
        "flavor_notes": flavor_notes,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    products = fetch_all_products()

    records = []
    flavored_records = []
    for product in products:
        detail = build_record(product)
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
    with open("data_qolcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_qolcoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
