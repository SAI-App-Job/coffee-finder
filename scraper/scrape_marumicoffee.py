# -*- coding: utf-8 -*-
"""
scrape_marumicoffee.py

丸美珈琲店(marumi-coffee.com、札幌市中央区南15条西5丁目3-10、MakeShop)の
商品情報を取得する。

【対象商品の絞り込みについて】
実データ確認済み: 「すべての商品」(/shopbrand/all_items/、全68件・6ページ)を
対象に、以下のキーワードを含む商品を非コーヒー豆として除外する。
「ドリップカフェ」(個包装ドリップバッグ、量り売りの豆ではない)、「ギフト」
「セット」(複数銘柄の詰め合わせ)、「ゼリー」(デザート)、「定期便」(商品名では
なく頒布会形式)、「手提げ袋」「紙袋」(包装資材)、「ボトル」(ボトル入り
アイスコーヒー飲料)、「珈福便」(福袋形式の頒布会)。除外後26件が単一銘柄の
ストレート/ブレンドのコーヒー豆(200g)。

【一覧ページの情報量について】
実データ確認済み: 一覧ページ(div.innerBox)の時点で商品名(p.name a)・価格
(p.price em.price)に加え、div.else内のli要素に「原産地：ペルー」のように
産地情報が構造化されている。詳細ページへの追加アクセスを行わず、一覧のみで
必要な情報が揃うため、本スクレイパーは詳細ページを取得しない。

【産地の適用について】
「原産地」欄はブレンド商品では「グアテマラ、コスタリカ、ホンジュラス、他」の
ように複数国がカンマ区切りで列挙される。単一原産地の商品(カンマなし)のみ
origin_countryの補完に使い、ブレンド商品には適用しない
(parse_product側のカテゴリ判定・商品名からの産地抽出に委ねる)。

【重量について】
実データ確認済み: div.content内の自由記述テキストに「内容量：200ｇ」のように
埋め込まれている(ラベル間の区切り文字が無く「標　 高：1,744m内容量：200ｇ」
のように連結されるため、内容量ラベルの直後の数値のみを正規表現で抜き出す)。

robots.txt確認済み(2026-09時点): robots.txt自体が存在しない(404、独自404
ページが返る)。制限の明示的な記述が無いため実質許可とみなす。

【flavor_notes(テイスティングノート)について(2026-09-20追記)】
実データ確認済み: 一覧ページのdiv.contentには構造化された産地ラベルのみで
風味の記述は無いが、詳細ページには<p class="addTxt">要素が複数あり、
1つ目は「＜このコーヒーについて＞」という見出しに続く農園の来歴・
買い付けエピソード、2つ目は「ローズヒップティや紅茶のような華やかな
印象」「アプリコットやオレンジを思わせる果実感ある味わい」のような
2行程度の短いテイスティングノート専用の記述になっている(サンプル6件
全件で確認、3つ目・4つ目は常に空)。この2つ目の要素をflavor_notesとして
採用するため、一覧のみで完結していた設計を変更し、各商品の詳細ページも
取得するようにした(その分の負荷を考慮しCRAWL_DELAY_SECONDSを設定)。
"""

import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_stock_status, detect_country_name

SHOP_INFO = {
    "name": "丸美珈琲店",
    "url": "https://www.marumi-coffee.com/",
    "platform": "MakeShop",
    "address": "北海道札幌市中央区南15条西5丁目3-10",
    "prefecture": "北海道",
    "robots_txt_status": "実質許可とみなす(2026-09確認。robots.txt自体が存在しない"
                          "=404で独自404ページが返る。制限の明示的な記述なし)",
}

BASE_URL = "https://www.marumi-coffee.com"
LIST_PAGES = [f"{BASE_URL}/shopbrand/all_items/"] + [
    f"{BASE_URL}/shopbrand/all_items/page{n}/" for n in range(2, 7)
]
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "ドリップカフェ", "ギフト", "セット", "ゼリー", "定期便", "手提げ袋", "紙袋", "ボトル", "珈福便",
]
WEIGHT_PATTERN = re.compile(r"内容量[：:]\s*(\d+)\s*[gｇ]")
PRICE_PATTERN = re.compile(r"([\d,]+)\s*円")
CRAWL_DELAY_SECONDS = 1


def extract_flavor_notes(product_url: str) -> str | None:
    """理由はモジュールdocstring参照。"""
    try:
        soup = fetch_page(product_url)
    except requests.RequestException as e:
        print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
        return None
    blocks = [b.get_text(" ", strip=True) for b in soup.select("p.addTxt")]
    non_empty = [b for b in blocks if b]
    if not non_empty:
        return None
    return non_empty[1] if len(non_empty) > 1 else non_empty[0]


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-jp"  # 実データ確認済み(Content-Type: text/html; charset=EUC-JP)
    return BeautifulSoup(resp.text, "html.parser")


def build_record(box) -> dict | None:
    name_el = box.select_one("p.name a")
    if not name_el:
        return None
    title = name_el.get_text(strip=True)
    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    href = name_el.get("href", "")
    product_url = f"{BASE_URL}{href}" if href.startswith("/") else href

    price_el = box.select_one("p.price em.price")
    price = None
    if price_el:
        m = PRICE_PATTERN.search(price_el.get_text())
        if m:
            price = int(m.group(1).replace(",", ""))

    origin_text = None
    for li in box.select("div.else li"):
        li_text = li.get_text(strip=True)
        if li_text.startswith("原産地"):
            origin_text = li_text.split("：", 1)[-1].strip()
            break

    content_el = box.select_one("div.content")
    weight_g = None
    if content_el:
        m = WEIGHT_PATTERN.search(content_el.get_text())
        if m:
            weight_g = int(m.group(1))

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

    # 単一原産地(カンマ無し)の場合のみ「原産地」欄を採用する(理由はdocstring参照)
    if origin_text and "、" not in origin_text and not parsed["origin_country"]:
        country = detect_country_name(origin_text)
        if country:
            parsed["origin_country"] = country
            parsed["origin_source"] = "product_description"
    parsed = apply_category_hint_fallback(parsed, None)

    stock_status = detect_stock_status(title)

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
        "flavor_notes": extract_flavor_notes(product_url),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    records = []
    flavored_records = []
    for url in LIST_PAGES:
        try:
            soup = fetch_page(url)
        except requests.RequestException as e:
            print(f"[warn] 一覧ページ取得失敗: {url} ({e})")
            continue
        for box in soup.select("div.innerBox"):
            detail = build_record(box)
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
    with open("data_marumicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_marumicoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
