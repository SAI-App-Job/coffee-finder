# -*- coding: utf-8 -*-
"""
scrape_nagoyabeans.py

なごやビーンズ(nagoyabeans.com、愛知県名古屋市昭和区長池町1-13〈有限会社
シエスタ〉、注文後焙煎の自家焙煎豆のオンライン販売)の商品情報を取得する。
カラーミーショップ。

robots.txt確認済み(2026-09時点): 他のカラーミー店舗と同一の記述。
User-agent: *に対し/secure/・/cart/のみDisallow。AhrefsBot等一部
ボットを個別にDisallow: /、それ以外は制限なし。

【商品一覧の取得方法について】
実データ確認済み: sitemap.xmlにはカテゴリページ(mode=cate)のリンクのみで
個別商品(pid=)へのリンクが含まれていない。商品ページから、対象4カテゴリ
(シングル/ブレンド/アイスコーヒー豆/デカフェ)へのリンクへ辿り、含まれる
pidリンクを和集合で収集する方式を採る:
・シングル（ストレート豆）: mode=cate&cbid=2005708
・ブレンド豆: mode=cate&cbid=2005710
・アイスコーヒー豆: mode=grp&gid=1233696(氷出し・水出し用に焙煎豆単品。
  同名の"アイスコーヒー"(cbid=2912830、瓶入りの完成品ドリンク「1本」)とは
  別物で、そちらは焙煎豆単品ではないため対象外)
・デカフェ（カフェインレス豆）: mode=grp&gid=1233704
上記4カテゴリ間には重複が多い(デカフェ産地別の豆はシングルにも重複掲載、
アイスブレンドはブレンドにも重複掲載等)。pidの和集合を取ることで重複を
自然に解消する。ギフト(cbid=2006112)・ドリップパック(cbid=2414948/
gid=2379989)・フィルター等器具(cbid=2780388)・瓶入り完成品アイスコーヒー
(cbid=2912830)は対象外のため巡回しない。

【商品情報の取得方法について】
実データ確認済み: 各商品ページに埋め込まれた`var Colorme = {...}`の
JSONから商品名・価格(sales_price_including_tax)・在庫数(stock_num)を
取得する(三澤珈琲・SANTOSと同じ方式)。挽き方(3段階)×焙煎度(9段階)の
組み合わせがvariantsとして存在するが、全variantで価格は同一(挽き方・
焙煎度は無料で選べる注文後焙煎方式のため)なので商品自体のsales_priceを
そのまま使う。

【重量について】
実データ確認済み: 全商品ページに内容量(g)の記載が無く(「ご利用案内」
ページにも「販売数量は商品により異なります。お問い合わせ下さい」との
記載のみ)、注文後焙煎・グラム単位の重量非公開の販売方式と判断される。
重量情報が一切取得できないため、本スクレイパーのweight_gは常にNoneと
なる。

【在庫状況について】
実データ確認済み: 大半の商品はstock_numがnull(在庫数管理なし=都度焙煎)
だが、コンペ産地の少量ロット等一部商品にはstock_num(残数)が設定されて
おり、0の場合は完売と判定できる(三澤珈琲と同じ方式)。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "なごやビーンズ",
    "url": "https://nagoyabeans.com/",
    "platform": "カラーミーショップ",
    "address": "愛知県名古屋市昭和区長池町1-13",
    "prefecture": "愛知県",
    "robots_txt_status": "実質許可(2026-09確認。他のカラーミー店舗と同一の記述。"
                          "/secure/・/cart/のみDisallow。AhrefsBot等一部ボットを"
                          "個別にDisallow: /、それ以外は制限なし)",
}

BASE_URL = "https://nagoyabeans.com"
CATEGORY_URLS = [
    f"{BASE_URL}/?mode=cate&cbid=2005708&csid=0",  # シングル（ストレート豆）
    f"{BASE_URL}/?mode=cate&cbid=2005710&csid=0",  # ブレンド豆
    f"{BASE_URL}/?mode=grp&gid=1233696",  # アイスコーヒー豆
    f"{BASE_URL}/?mode=grp&gid=1233704",  # デカフェ（カフェインレス豆）
]
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

COLORME_PATTERN = re.compile(r"var Colorme\s*=\s*(\{.*?\});", re.DOTALL)


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "EUC-JP"
    return BeautifulSoup(resp.text, "html.parser")


def fetch_pids() -> list[str]:
    pids: set[str] = set()
    for url in CATEGORY_URLS:
        soup = fetch_page(url)
        for a in soup.find_all("a", href=True):
            m = re.search(r"[?&]pid=(\d+)", a["href"])
            if m:
                pids.add(m.group(1))
    return sorted(pids, key=int)


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
        "weight_g": None,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    pids = fetch_pids()

    records = []
    flavored_records = []
    for pid in pids:
        product_url = f"{BASE_URL}/?pid={pid}"
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
    with open("data_nagoyabeans.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_nagoyabeans.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
