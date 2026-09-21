# -*- coding: utf-8 -*-
"""
scrape_romancoffee.py

尾道浪漫珈琲(romancoffee.shop-pro.jp、〒722-0034 広島県尾道市十四日元町
4-1、自家焙煎豆のオンライン販売)の商品情報を取得する。カラーミーショップ
(shop-pro.jp)。

【住所について】
特定商取引法ページ(https://romancoffee.shop-pro.jp/?mode=sk)を実データ
確認したところ、販売業者「株式会社浪漫珈琲」の住所は「〒722-0034 広島県
尾道市十四日元町4-1」であることを確認した(2026-09時点、郵便番号は候補
リストと一致するが町名が異なっていたため実データを採用)。

robots.txt確認済み(2026-09時点): shop-pro.jp標準のrobots.txtで、本
スクレイパーが使う商品一覧・詳細ページ(?mode=cate, ?pid=)は制限対象外。

【対象カテゴリについて】
実データ確認済み: 商品カテゴリは「期間限定焙煎豆(cbid=2726403、確認時点
では出品0件=ページ自体404)」「オリジナルブレンド(cbid=2726805、3件)」
「シングルオリジン(cbid=2726806、6件)」「オリジナルギフト(cbid=2726807)」
「PB 尾道浪漫珈琲オリジナル商品(cbid=2726808、12件)」「その他
(cbid=2726809)」の6種類。PBカテゴリの実データを確認したところ全件が
ドリップバッグ・アイスコーヒー(瓶入り完成品)・珈琲羊羹などコーヒー豆
単品ではない商品だったため非対象。オリジナルギフト・その他も同様の
性質と判断し非対象。オリジナルブレンド・シングルオリジンの2カテゴリの
みを対象とする。

【商品情報の取得方法について】
実データ確認済み: 各カテゴリの一覧ページ(li.productlist-list__unit)に
商品名(span.product-list__name)・価格(span.product-list__price、税込
表示をそのまま使用)が静的HTMLで直接出力されている。商品名末尾に重量
(例:「200ｇ」)が付与されている。

【在庫状況について】
実データ確認済み: 一覧ページに売り切れを示す構造化されたバッジ・
クラスは見つからなかった(2026-09時点で確認した9件は全件购入可能)ため、
商品名のテキストのみから判定する。

【flavor_notes(2026-09-21追記)】
実データ確認済み: og:description/Descriptionメタタグは100文字程度で
切り詰められているため使用しない。代わりに商品詳細ページのdiv.product-
explainを使うと、対象9件全てでスペック情報+テイスティング文(単一銘柄
商品は「香味の特徴」という見出し付き)が入っていることを確認した。末尾に
「＜取り扱い注意事項＞」(ブレンド商品)または「※コーヒー豆の画像は」
(単一銘柄商品)で始まる保存方法/画像注記の定型文が続く場合があるため
打ち切る。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "尾道浪漫珈琲",
    "url": "https://romancoffee.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "広島県尾道市十四日元町4-1",
    "prefecture": "広島県",
    "robots_txt_status": "実質許可(2026-09確認。shop-pro.jp標準のrobots.txtで、本スクレイパーが"
                          "使う商品一覧・詳細ページは制限対象外)",
}

BASE_URL = "https://romancoffee.shop-pro.jp"
CATEGORY_IDS = [2726805, 2726806]  # オリジナルブレンド, シングルオリジン(理由はモジュールdocstring参照)
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
PRICE_PATTERN = re.compile(r"([\d,]+)\s*円")
FLAVOR_STOP_PATTERN = re.compile(r"※コーヒー豆の画像は|＜取り扱い注意事項＞")


def extract_flavor_notes(soup: BeautifulSoup) -> str | None:
    """理由はモジュールdocstring参照。"""
    el = soup.select_one("div.product-explain")
    if not el:
        return None
    text = el.get_text("\n", strip=True)
    m = FLAVOR_STOP_PATTERN.search(text)
    text = text[:m.start()] if m else text
    return text.strip() or None


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return BeautifulSoup(resp.text, "html.parser")


def scrape_category(cbid: int) -> list[dict]:
    url = f"{BASE_URL}/?mode=cate&cbid={cbid}&csid=0"
    soup = fetch_page(url)
    items = []
    for li in soup.select("li.productlist-list__unit"):
        name_el = li.select_one("span.product-list__name")
        price_el = li.select_one("span.product-list__price")
        link_el = li.select_one('a[href^="?pid="]')
        if not name_el or not link_el:
            continue
        title = name_el.get_text(strip=True)
        title = re.sub(r"\s+", " ", title)
        price = None
        if price_el:
            m = PRICE_PATTERN.search(price_el.get_text())
            if m:
                price = int(m.group(1).replace(",", ""))
        product_url = BASE_URL + "/" + link_el["href"]
        items.append({"title": title, "price": price, "url": product_url})
    return items


def build_record(item: dict) -> dict | None:
    title = item["title"]
    if not title:
        return None
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": item["price"],
            "product_url": item["url"],
        }

    stock_status = detect_stock_status(title)
    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None

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
        "flavor_notes": item.get("flavor_notes"),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    all_items: dict[str, dict] = {}
    for cbid in CATEGORY_IDS:
        try:
            items = scrape_category(cbid)
        except requests.RequestException as e:
            print(f"[warn] カテゴリ取得失敗: cbid={cbid} ({e})")
            continue
        for item in items:
            all_items[item["url"]] = item

    records = []
    flavored_records = []
    for item in all_items.values():
        try:
            item["flavor_notes"] = extract_flavor_notes(fetch_page(item["url"]))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['url']} ({e})")

        detail = build_record(item)
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
    with open("data_romancoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_romancoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
