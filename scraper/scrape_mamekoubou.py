# -*- coding: utf-8 -*-
"""
scrape_mamekoubou.py

豆工房タカハシ(www.mamekoubou-takahasi.com、岩手県花巻市桜台2-32-6、
自家焙煎豆のオンライン販売)の商品情報を取得する。独自ドメイン・独自PHP
カート(shop/index.php?item=N形式)。本プロジェクトで初めて対応する
独自カートCMS(BASE/カラーミー/Shopify/Yahoo!ショッピングのいずれでもない)。

【住所について】
トップページのヘッダー部分で実データ確認済み(2026-09時点):
「〒025-0064　岩手県花巻市桜台2-32-6」との記載を確認。候補リストの住所と
一致。

【robots.txtについて】
robots.txtは存在しない(404、サイト独自の404ページが返る)。制限の明示的な
記述が無いため実質許可とみなす。

【文字コード】UTF-8(実データ確認済み、Content-Type: text/html;
charset=UTF-8。`<meta charset="UTF-8">`とも一致)。

【商品一覧の取得方法について】
実データ確認済み: shop/index.php(カテゴリ一覧、page=1〜2)にリンクされる
item=N形式の商品詳細ページを全件クロールする方式を採る(全17件、
item=6,7,8,9,10,12,15,16,18,19,20,21,22,23,25,26,27)。カテゴリ一覧
ページ自体には価格・在庫等の詳細情報が無いため、個別ページを1件ずつ
取得する必要がある。

【商品名・価格の取得方法について】
実データ確認済み: 個別ページにOGPメタタグやJSON埋め込みが無く、
`<p class="statusText">商品名：◯◯◯</p>`という独自のラベル付きテキストから
商品名を取得する。価格は同ページ内の価格テーブル(挽き方バリアント×4:
豆のまま/細挽き/中挽き/粗挽き)から取得するが、実データ確認の結果、全17件
とも挽き方に関わらず同一価格だったため、テーブル内の最初の価格をそのまま
採用する。

【在庫について】
実データ確認済み: 価格テーブルの各行末に在庫記号(◎=在庫あり)がある。
調査時点では全17件が全バリアントで◎だったため、記号が1つも見つからない
場合のみ構造的な品切れとして扱う(実際に品切れの表示例は未確認のため、
念のためのフォールバック)。

【対象商品について】
実データ確認済み(全17件): 全件が単一銘柄のコーヒー豆(100g)で、非対象商品
(ギフトセット・詰め合わせ等)は無かった。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "豆工房タカハシ",
    "url": "https://www.mamekoubou-takahasi.com/",
    "platform": "独自EC(PHPカート)",
    "address": "岩手県花巻市桜台2-32-6",
    "prefecture": "岩手県",
    "robots_txt_status": "実質許可とみなす(2026-09確認。robots.txtが存在しない"
                          "=404で独自404ページが返る。制限の明示的な記述なし)",
}

BASE_URL = "https://www.mamekoubou-takahasi.com/shop/index.php"
# 理由はモジュールdocstring参照(カテゴリ一覧ページから実データ確認済みの全17件)
ITEM_IDS = [6, 7, 8, 9, 10, 12, 15, 16, 18, 19, 20, 21, 22, 23, 25, 26, 27]
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
PRICE_PATTERN = re.compile(r"(\d+)\s*円")
STOCK_MARK_PATTERN = re.compile(r"◎|○")


def fetch_page(item_id: int) -> BeautifulSoup:
    resp = requests.get(BASE_URL, params={"item": item_id}, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def extract_fields(soup: BeautifulSoup) -> dict | None:
    title = None
    for el in soup.select(".statusText"):
        text = el.get_text(strip=True)
        if text.startswith("商品名"):
            title = re.sub(r"^商品名[：:]\s*", "", text).strip()
            break
    if not title:
        return None

    table = soup.find("table")
    table_text = table.get_text(" ", strip=True) if table else ""
    price_m = PRICE_PATTERN.search(table_text)
    price = int(price_m.group(1)) if price_m else None
    has_stock_mark = bool(STOCK_MARK_PATTERN.search(table_text))

    return {"title": title, "price": price, "has_stock_mark": has_stock_mark}


def build_record(item: dict, product_url: str) -> dict | None:
    title = item["title"]
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": item["price"],
            "product_url": product_url,
        }

    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None
    structural_out_of_stock = not item["has_stock_mark"]
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
        "price": item["price"],
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    records = []
    flavored_records = []
    for item_id in ITEM_IDS:
        product_url = f"{BASE_URL}?item={item_id}"
        try:
            soup = fetch_page(item_id)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        fields = extract_fields(soup)
        if not fields:
            print(f"[warn] 商品情報が見つかりません: {product_url}")
            continue
        detail = build_record(fields, product_url)
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
    with open("data_mamekoubou.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mamekoubou.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
