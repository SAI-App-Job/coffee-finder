# -*- coding: utf-8 -*-
"""
scrape_adachi.py

アダチコーヒー(www.adachicoffee.jp、千葉県、自家焙煎豆のオンライン
販売)の商品情報を取得する。おちゃのこネット(Ocnk)クリーンURLテーマ。

robots.txt確認済み(2026-09時点): GPTBot/Bytespider/TikTokSpider/
meta-externalagentのみ個別にDisallow: /、それ以外は制限なし。

【商品一覧の取得方法について】
実データ確認済み: sitemap.xmlに列挙された/product/N形式のURL(38件)を
起点とする。

【豆商品/非豆商品の判定について】
実データ確認済み: `<title>`タグが「商品名 [自家焙煎珈琲豆]」という
末尾ラベル付きの商品(28件、ブレンド・ストレート豆・デカフェ)と、
このラベルを持たない商品(10件、ギフトセット・ドリップバッグセット・
ギフトボックス・カフェオレベース)の2種に明確に分かれている。この
ラベルの有無を豆単品/非豆商品の判定に用いる(ラベルが無ければ除外)。

【重量・価格について】
実データ確認済み: 他のOcnk店舗(青海珈琲等)と異なり、重量セレクト
(`グラム数`ラベルの<select>)の各<option>テキストに重量と価格が直接
埋め込まれている(例:「100g／860円」「200g／1,634円（5%割引）」)ため、
正規表現で正確な重量別価格を取得できる。同じセレクト内にドリップ
バッグ加工のオプション(例:「100g（ドリップバッグ8個）200円加算／
1,060円」)も混在するため、これらは除外し、最小重量の素の豆オプション
(value="1"等)を代表として採用する。

【季節限定商品の販売休止表記について】
実データ確認済み: 季節限定ブレンド(春/秋/冬)が「【期間外のため現在
販売しておりません】」という接頭辞付きで表示される。この「販売して
おりません」という表現はdata/stock_status_synonyms.jsonの「一時的に
品切れ」に新規追加した(店舗を横断する一般的な表現のため)。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "アダチコーヒー",
    "url": "https://www.adachicoffee.jp/",
    "platform": "おちゃのこネット(Ocnk)",
    "address": "千葉県",
    "prefecture": "千葉県",
    "robots_txt_status": "実質許可(2026-09確認。GPTBot等AI系ボットのみ個別にDisallow: /、"
                          "それ以外は制限なし)",
}

BASE_URL = "https://www.adachicoffee.jp"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

BEAN_LABEL = " [自家焙煎珈琲豆]"
WEIGHT_PRICE_PATTERN = re.compile(r"^(\d+)g／([\d,]+)円")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_product_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    urls = []
    for loc in soup.find_all("loc"):
        text = loc.get_text(strip=True)
        if re.search(r"/product/\d+$", text):
            urls.append(text)
    return urls


def pick_canonical_variant(soup: BeautifulSoup) -> tuple[int | None, int | None]:
    """理由はモジュールdocstring参照。「グラム数」ラベルの<select>から
    ドリップバッグ加工でない素の豆オプションのうち最小重量を採用する。
    戻り値は(weight_g, price)。"""
    for item_box in soup.select("div.item_box"):
        label_el = item_box.select_one("span.variation_label")
        if not label_el or label_el.get_text(strip=True) != "グラム数":
            continue
        candidates = []
        for option in item_box.select("select option"):
            text = option.get_text(strip=True)
            if "ドリップバッグ" in text:
                continue
            m = WEIGHT_PRICE_PATTERN.match(text)
            if m:
                candidates.append((int(m.group(1)), int(m.group(2).replace(",", ""))))
        if candidates:
            return min(candidates, key=lambda c: c[0])
    return None, None


def build_record(url: str, soup: BeautifulSoup) -> dict | None:
    title_el = soup.select_one("title")
    raw_title = title_el.get_text(strip=True) if title_el else ""
    if not raw_title.endswith(BEAN_LABEL):
        return None
    title = raw_title[: -len(BEAN_LABEL)].strip()

    parsed = parse_product(title)
    weight_g, price = pick_canonical_variant(soup)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": url,
        }

    # 完全に在庫が無い商品はグラム数の<select>自体が非表示になり、代わりに
    # div.detail_section.stock.soldoutに「在庫なし」と表示される(実データ
    # 確認済み、夏ブレンドで発見。商品名自体には在庫状態を示す語が無いため、
    # この構造化フラグが無いと販売中と誤判定してしまう)。
    structural_out_of_stock = soup.select_one("div.detail_section.stock.soldout") is not None
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
        "product_url": url,
    }


def parse_product_detail(url: str) -> dict | None:
    return build_record(url, fetch_page(url))


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_product_urls()
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for product_url in product_urls:
        try:
            soup = fetch_page(product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue

        title_el = soup.select_one("title")
        raw_title = title_el.get_text(strip=True) if title_el else ""
        if not raw_title.endswith(BEAN_LABEL):
            continue

        title = raw_title[: -len(BEAN_LABEL)].strip()
        prev = previous.get(product_url)
        if is_unchanged(prev, raw_name=title):
            records.append(prev)
            continue

        detail = build_record(product_url, soup)
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) > 1:
        print(json.dumps(parse_product_detail(sys.argv[1]), ensure_ascii=False, indent=2))
    else:
        records, flavored_records = scrape_all_products()
        output = {
            "shop": SHOP_INFO,
            "products": records,
            "flavored_products_excluded": flavored_records,
        }
        with open("data_adachi.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_adachi.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
