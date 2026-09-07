# -*- coding: utf-8 -*-
"""
scrape_mamezocoffee.py

自家焙煎 豆蔵(mamezocoffee.com、愛知県岡崎市細川町字長根38－4、自家焙煎豆の
オンライン販売)の商品情報を取得する。

【プラットフォームについて】
実データ確認済み(2026-09時点): robots.txt自体が存在しない(404)ため、Disallow
指定は無く実質許可。ショップ自体はBASE/カラーミー/Shopify/MakeShop/Ocnk/
EC-CUBE/WooCommerceのいずれでもなく、商品購入ページ(item.html)が静的HTMLの
自作ページになっており、購入ボタンのフォームだけが外部カートCGIサービス
「cart.ec-sites.jp」に投げる方式(es_item_id等の隠しinputを持つ<form>)。
一覧・商品情報の取得自体はこのCGIサービスに一切アクセスせず、item.html本体
(静的HTML、JSレンダリング不要)をrequests+BeautifulSoupで読むだけで完結する。
FC2/STORES/Wix/Jimdoのような対象外プラットフォームではなく、単なる自社
静的HTMLページのため実装対象とする。

【商品情報の取得方法について】
実データ確認済み: item.htmlに「商品詳細」テーブル(class="item_des"、商品名・
煎り・コメントの3列)と、直後に続く「商品購入」テーブル(class="buy_area"、
100g/200g/500gの重量と価格を<th>に列挙)がペアで並ぶ構造。全14件(カップ
オブエクセレンス受賞豆1件+ブレンド7件+ストレート6件)を確認済みで、ギフト・
ドリップバッグ・器具等の非コーヒー豆商品は混在していない(NON_BEAN_KEYWORDS
は将来の混入に備えた空の安全弁として保持)。

【重量について】
実データ確認済み: 全14件が100g/200g/500gの3サイズを1商品ページ内に併記して
おり(kamecoffee等のような重量違いの複数ページ分割ではない)、最小の100gを
代表として採用する。

【焙煎度について】
「商品詳細」テーブルの「煎り」列は「深煎り」「中煎り」「やや深煎り」という
粗い表記で、coffee_parser.ROAST_KEYWORDS(プロ向け8段階のカタカナ表記)とは
粒度が異なるため、roast_hintとして保持しroast_levelには反映しない
(marutake珈琲・tsukikoya等と同じ方針)。「コメント」列はflavor_notesとして
原文のまま保持する。

【product_urlについて】
商品ごとの個別詳細ページが無く単一のitem.htmlに全商品が並ぶ構造のため、
各商品の100g/豆(粒のまま)バリアントに対応するes_item_id(カート投入用の
隠しinput、商品ごとに一意)をクエリパラメータとして付与し一意なURLを作る。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "自家焙煎 豆蔵",
    "url": "https://mamezocoffee.com/",
    "platform": "独自静的HTML(購入ボタンのみ外部カートサービスcart.ec-sites.jpへフォーム送信)",
    "address": "愛知県岡崎市細川町字長根38－4",
    "prefecture": "愛知県",
    "robots_txt_status": "実質許可(2026-09確認。robots.txt自体が存在しない(404)ため制限なし)",
}

BASE_URL = "https://mamezocoffee.com"
ITEM_PAGE_URL = f"{BASE_URL}/item.html"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 理由はモジュールdocstring参照(現時点の全14件にギフト・ドリップバッグ・
# 器具等の混入は無いが、将来の商品追加に備えた安全弁として保持)
NON_BEAN_KEYWORDS = []

WEIGHT_PRICE_PATTERN = re.compile(r"(\d+)\s*[gｇ]\s*/\s*([\d,]+)\s*円")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def parse_weight_price_pairs(buy_area_table) -> list[tuple[int, int]]:
    text = buy_area_table.get_text(" ", strip=True)
    pairs = []
    for m in WEIGHT_PRICE_PATTERN.finditer(text):
        weight_g = int(m.group(1))
        price = int(m.group(2).replace(",", ""))
        pairs.append((weight_g, price))
    return pairs


def build_record(item_des_table, buy_area_table) -> dict | None:
    cells = item_des_table.find_all("td")
    if len(cells) < 3:
        return None
    name = cells[0].get_text(strip=True)
    roast_hint = cells[1].get_text(strip=True) or None
    flavor_notes = cells[2].get_text(strip=True) or None

    if not name or any(kw in name for kw in NON_BEAN_KEYWORDS):
        return None

    pairs = parse_weight_price_pairs(buy_area_table)
    if not pairs:
        return None
    weight_g, price = min(pairs, key=lambda p: p[0])

    # 理由はモジュールdocstring参照(100g/豆のままバリアントのes_item_idで
    # 商品ごとに一意なURLを作る。buy_area内で最初に出現するes_item_idが
    # 常に最小重量(100g)×豆のままの組み合わせに対応する)。
    # 実装注意: str(buy_area_table)に対する正規表現ではなく、パース済みDOMから
    # <input name="es_item_id">要素のvalue属性を直接読む。BeautifulSoup
    # (html.parser)はタグを再シリアライズする際に属性をアルファベット順に
    # 並べ替える(実データ確認済み: 元HTMLの`type="hidden" name="es_item_id"
    # value="..."`が`name=... type=... value=...`の順になる)ため、
    # `name="es_item_id"\s+value="..."`のような文字列正規表現は属性順序に
    # 依存してしまい常にマッチしない不具合があった。
    item_id_input = buy_area_table.find("input", attrs={"name": "es_item_id"})
    item_id = item_id_input.get("value") if item_id_input else None
    product_url = f"{ITEM_PAGE_URL}?item_id={item_id}" if item_id else ITEM_PAGE_URL

    parsed = parse_product(name)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": product_url,
        }

    stock_status = detect_stock_status(name)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": None,  # 理由はモジュールdocstring参照(粗い焙煎度表記のためroast_hintに保持)
        "roast_hint": roast_hint,
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
    soup = fetch_page(ITEM_PAGE_URL)

    records = []
    flavored_records = []
    for item_des_table in soup.select("table.item_des"):
        buy_area_table = item_des_table.find_next_sibling("table", class_="buy_area")
        if buy_area_table is None:
            continue
        detail = build_record(item_des_table, buy_area_table)
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


if __name__ == "__main__":
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_mamezocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mamezocoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
