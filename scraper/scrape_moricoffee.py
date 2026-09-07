# -*- coding: utf-8 -*-
"""
scrape_moricoffee.py

MORI COFFEE(www.moricoffee.jp、三重県松阪市矢津町1586、自家焙煎豆の
オンライン販売。松阪本店の他、津市にジェラート主体の姉妹店があるが
2拠点で11店舗未満のため対象)の商品情報を取得する。おちゃのこネット
(Ocnk、URL構造/product-list/・/product-group/・/product/Nから確認済み)。

robots.txt確認済み(2026-09時点): User-agent: *には制限なし
(GPTBot/Bytespider/TikTokSpider/meta-externalagentのみDisallow: /で
本スクレイパーは該当しない)。彩香房(scrape_saikaboo.py)と同じ状況。

【商品一覧の取得方法について】
実データ確認済み: 商品グループ・商品リストのカテゴリページ27個
(product-list/2,5,6,7,8,10,11,12,14,15,21,22,25,30,37,41,46,54,56,63,64,
80,81 と product-group/1,3,4,5)を巡回し、含まれるproduct/Nリンクを
和集合で収集する(彩香房・大和屋珈琲と同じ「まめぽっと」方式)。合計38件。

【商品情報の取得方法について】
実データ確認済み: この店舗の<title>タグは商品ごとの固有情報を含まない
定型文言(例:「mori coffee がお届けします」)のためタイトル取得には
使えない(彩香房等の他Ocnk店舗との相違点)。og:titleメタタグは商品ごとに
実際の商品名(例:「ほの香 200g」)が入っており利用可能。価格は
product:price:amountメタタグから取得する。在庫状態を示す構造化フラグは
実データ確認の範囲で見つからなかった(JS変数`pConf.soldOut`は全商品共通の
定型文言で個別の在庫状態を表さない)ため、商品名のテキストのみから
detect_stock_status()で判定する。

【非コーヒー豆商品の除外について】
実データ確認済み(全38件): 「モリコーヒーオリジナルコーヒーバッグ」
各種(1/2/3/6/12/18/24/36袋入り、ギフトセット含む)がドリップバッグ形式
→「コーヒーバッグ」、「カリタ　かんたんドリップ　10枚入」(器具+
フィルター)→「ドリップ」、「３種飲み比べセット」各ロースト×3件
(内容が固定されない飲み比べ用詰め合わせ)→「飲み比べセット」、
「ギフトBOX」(中身の無い箱単体)→「ギフトBOX」。残り24件
(シングルオリジン・オリジナルブレンド・デカフェ、いずれも100gまたは
200g)を対象とする。同一銘柄の焙煎度違い(例:コスタリカのシティロースト
版とハイロースト版)は商品名が異なる別商品として扱い、重量違いの重複
除去(weight-variant dedup)の対象にはしない(産地は同じでも焙煎度という
別の軸で意図的に作り分けられた別SKUのため)。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "MORI COFFEE",
    "url": "https://www.moricoffee.jp/",
    "platform": "おちゃのこネット",
    "address": "三重県松阪市矢津町1586",
    "prefecture": "三重県",
    "robots_txt_status": "実質許可(2026-09確認。User-agent: *には制限なし。"
                          "GPTBot等AI系クローラーのみDisallow: /で本スクレイパーは"
                          "該当しない)",
}

BASE_URL = "https://www.moricoffee.jp"
CATEGORY_PATHS = [
    "product-list/2", "product-list/5", "product-list/6", "product-list/7",
    "product-list/8", "product-list/10", "product-list/11", "product-list/12",
    "product-list/14", "product-list/15", "product-list/21", "product-list/22",
    "product-list/25", "product-list/30", "product-list/37", "product-list/41",
    "product-list/46", "product-list/54", "product-list/56", "product-list/63",
    "product-list/64", "product-list/80", "product-list/81",
    "product-group/1", "product-group/3", "product-group/4", "product-group/5",
]
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["コーヒーバッグ", "ドリップ", "飲み比べセット", "ギフトBOX"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_product_urls() -> list[str]:
    pids: set[str] = set()
    for path in CATEGORY_PATHS:
        soup = fetch_page(f"{BASE_URL}/{path}")
        for a in soup.select(f'a[href*="{BASE_URL}/product/"]'):
            m = re.search(r"/product/(\d+)", a.get("href", ""))
            if m:
                pids.add(m.group(1))
    return [f"{BASE_URL}/product/{pid}" for pid in pids]


def extract_fields(soup: BeautifulSoup) -> dict | None:
    title_el = soup.select_one('meta[property="og:title"]')
    if not title_el or not title_el.get("content"):
        return None
    title = title_el["content"].strip()
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None
    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None
    return {"title": title, "price": price}


def build_record(item: dict) -> dict | None:
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
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_product_urls()
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for product_url in product_urls:
        prev = previous.get(product_url)
        try:
            fields = extract_fields(fetch_page(product_url))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if not fields:
            continue
        if is_unchanged(prev, raw_name=fields["title"]):
            records.append(prev)
            continue

        detail = build_record({"title": fields["title"], "price": fields["price"], "url": product_url})
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
    with open("data_moricoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_moricoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
