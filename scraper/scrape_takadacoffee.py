# -*- coding: utf-8 -*-
"""
scrape_takadacoffee.py

SOU/ZAEMON by TAKADA COFFEE(たかだこーひー、takadacoffee.com、山口県下関市
長府侍町1丁目2番39号、自家焙煎豆のオンライン販売)の商品情報を取得する。
WordPress+Welcart(ECプラグイン)。

【店名・住所について】
「SOU/ZAEMON by TAKADA COFFEE」は候補リストにある店名だが、実データ確認の
結果これは運営会社TAKADA COFFEEの下関市長府(Chofu)にあるフラッグシップ
店舗・ロースタリー(公式サイトのshop-2/chofu/ページで「TAKADA COFFEE
FLAGSHIP STORE CHOFU ROASTERY」と確認)であり、オンラインショップ自体は
店舗専用ではなく会社全体で共通のtakadacoffee.com上で運営されている。公式
サイトのshop-2/chofu/ページで実データ確認済み(2026-09時点)の住所
「〒759-0978 山口県下関市長府侍町1-2-39」を採用する(候補リストの住所と
一致)。

robots.txt確認済み(2026-09時点): WordPress標準の記述で/wp-admin/のみ
Disallow(admin-ajax.phpは個別にAllow)。本スクレイパーが使う商品ページは
対象外。

【商品カタログの構成について】
実データ確認済み: 商品カテゴリ「豆(オンラインショップ)」
(/category/beans-online-shop/)配下に9商品が掲載されている。商品ページは
個別の固定URL(例: /bolivia-caranavi/)で、og:titleメタタグに商品名、
div.skuname(複数ある場合は重量違いの複数バリアント)に重量、
div.field_priceの次のp.tax_inc_block内に税込価格、div.zaikostatusに
在庫状態テキストが構造化されている。CHOCO BLEND(チョコブレンド)は
チョコレート風味のフレーバーコーヒーであり、coffee_parserのis_flavored
判定でフレーバー扱いとなる想定。非コーヒー豆商品(器具・雑貨等)は
このカテゴリには無かった。

【重量違いの重複について】
実データ確認済み: 一部商品(CHOCO/DECAF/KENYA/MILD/MOCHA/SPECIAL BLEND)が
200gと「お得な400g」の2バリアント、ゲイシャブレンドが100g/200gの2
バリアントを持つ(いずれも同一ページ内の複数skuform、別商品ではない)。
最初に現れる最小重量のバリアントを代表として採用する。

【flavor_notes(2026-09-21追記)】
実データ確認済み: div.item-infoに対象9件全てでテイスティング文・産地
背景が入っていることを確認した(ストレート豆は「生産国：」ラベル、
ブレンドは商品名見出しで始まる)。直後に重量選択UI(「200g」「挽き目」
「在庫状態」等)が地続きで続くため、最初の重量表記の直前で打ち切る。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "SOU/ZAEMON by TAKADA COFFEE",
    "url": "https://www.takadacoffee.com/",
    "platform": "WordPress(Welcart)",
    "address": "山口県下関市長府侍町1丁目2番39号",
    "prefecture": "山口県",
    "robots_txt_status": "実質許可(2026-09確認。WordPress標準の記述で/wp-admin/"
                          "のみDisallow、本スクレイパーが使う商品ページは対象外)",
}

BASE_URL = "https://www.takadacoffee.com"
BEANS_CATEGORY_URL = f"{BASE_URL}/category/beans-online-shop/"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 理由はモジュールdocstring参照: カテゴリページには会社概要・お問い合わせ等の
# 非商品ページへのリンクも混在するため、既知の非商品パスを除外する
NON_PRODUCT_PATH_KEYWORDS = [
    "/about/", "/contact/", "/onlineshop/", "/recruit/", "/shop-2/",
    "/usces-cart/", "/wholesale/", "/wp-json/", "/category/",
]

WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
PRICE_PATTERN = re.compile(r"tax_inc_block\">[^¥￥]*[¥￥]([\d,]+)")
STOCK_LABEL_PATTERN = re.compile(r"在庫状態\s*[:：]\s*([^\s<]+)")
FLAVOR_STOP_PATTERN = re.compile(r"\d+\s*[gｇ]")


def extract_flavor_notes(soup: BeautifulSoup) -> str | None:
    """理由はモジュールdocstring参照。"""
    el = soup.select_one("div.item-info")
    if not el:
        return None
    text = el.get_text("\n", strip=True)
    m = FLAVOR_STOP_PATTERN.search(text)
    if m:
        text = text[:m.start()]
    return text.strip() or None


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def fetch_product_urls() -> list[str]:
    soup = fetch_page(BEANS_CATEGORY_URL)
    urls: set[str] = set()
    for a in soup.select(f'a[href^="{BASE_URL}/"]'):
        href = a.get("href", "")
        if not re.match(rf"^{re.escape(BASE_URL)}/[a-z0-9-]+/$", href):
            continue
        if any(kw in href for kw in NON_PRODUCT_PATH_KEYWORDS):
            continue
        urls.add(href)
    return sorted(urls)


def build_record(html: str, product_url: str) -> dict | None:
    title_m = re.search(r'og:title" content="([^"]+)"', html)
    if not title_m:
        return None
    title = title_m.group(1).strip()
    if not title:
        return None

    parsed = parse_product(title)

    price_m = PRICE_PATTERN.search(html)
    price = int(price_m.group(1).replace(",", "")) if price_m else None

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

    # 理由: WEIGHT_PATTERNをHTML全体に適用すると、インライン画像のbase64データ
    # 中に偶然「数字+g」の並びが出現し誤検出することがある(実データ確認済み)。
    # div.skuname(重量選択肢)の中身に限定して検出する。
    soup = BeautifulSoup(html, "html.parser")
    skuname_els = soup.select("div.skuname")
    weight_g = None
    for el in skuname_els:
        m = WEIGHT_PATTERN.search(el.get_text())
        if m:
            weight_g = int(m.group(1))
            break

    stock_label_m = STOCK_LABEL_PATTERN.search(html)
    structural_out_of_stock = bool(stock_label_m) and "終了" in stock_label_m.group(1)
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
        "flavor_notes": extract_flavor_notes(soup),
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
            resp = requests.get(product_url, headers=REQUEST_HEADERS, timeout=20)
            resp.raise_for_status()
            if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
                resp.encoding = "utf-8"
            detail = build_record(resp.text, product_url)
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
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_takadacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_takadacoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
