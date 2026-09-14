# -*- coding: utf-8 -*-
"""
scrape_lotuscoffee.py

自家焙煎コーヒー豆屋〜ろーたす〜(lotuscoffee.shop-pro.jp、福島県福島市、
自家焙煎豆のオンライン販売。運営者:曳地)の商品情報を取得する。カラーミーショップ
(shop-pro.jp)。

【所在都道府県について】
候補リスト作成時点では山形県か福島県か不明だったが、実データ確認(2026-09時点):
トップページのタイトルに「福島市にある自家焙煎コーヒー豆屋　〜ろーたす〜」、
metaキーワードに「福島市コーヒー豆」と明記されている。福島市のため本バッチ
(宮城・山形・福島)の対象に含めた。住所の号地番までは公開ページから確認できな
かったため、市レベルの表記に留める。

【文字コード】EUC-JP(実データ確認済み)。

【商品一覧の取得方法について】
実データ確認済み(2026-09時点): ?mode=srh&keyword=&sort=nで11件がヒットするが、
このテーマは405coffee.py等の「prd_lst_unit」系とは異なる「top_frame」テーブル
レイアウトで、`<a href="?pid=XXX">商品名</a><br />販売価格:XXX円(税込)`という
行が並ぶ。全11件が1ページに収まる(ページネーション未検出)。

【非コーヒー豆商品の除外について】
実データ確認済み: 11件中5件がご贈答用の化粧箱・豆入れ袋・V60サーバーといった
コーヒー豆以外の商品(ご贈答用-A/B/Cのクラフトケース・豆入れガゼット袋・V60
コーヒーサーバー2種)で、キーワード除外(NON_BEAN_KEYWORDS)に加え、産地情報も
ブレンド判定も無ければ除外する構造的チェックも保険として適用する(405coffee.py
と同じ方針)。

【商品詳細ページの■ラベル構造について】
実データ確認済み: div.detail_text内に「■生産国　　エチオピア」のような
「■ラベル(全角スペース区切り)値」の行が<br>区切りで並ぶ(405coffee.pyのタブ区切り
とは異なる独自形式)。重量表記は見当たらず(実データ確認済み、全商品共通で単一
重量のみの販売と推測されるが商品名にも重量記載が無いためweight_gは常にnull)。

【在庫について】var Colorme のinventory_controlが"none"(実データ確認済み、
405coffee.py等と同じ)で、stock_numは常にnull。商品名のテキストのみで在庫状態を
判定する。

robots.txt確認済み(2026-09時点): PHILOCOFFEA等と同一の記述(User-agent: *は
/secure/と/cart/のみ制限)。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    normalize_processing_method,
    detect_stock_status,
    detect_country_name,
)
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "自家焙煎コーヒー豆屋〜ろーたす〜",
    "url": "https://lotuscoffee.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "福島県福島市",
    "prefecture": "福島県",
    "robots_txt_status": "許可(2026-09確認。/secure/と/cart/以外は制限なし。"
                          "PHILOCOFFEA等と同一の記述)",
}

BASE_URL = "https://lotuscoffee.shop-pro.jp/"
LIST_URL = "https://lotuscoffee.shop-pro.jp/?mode=srh&keyword=&sort=n"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 実データ確認済み(2026-09時点): ご贈答用の化粧箱・豆入れ袋・コーヒーサーバー等
NON_BEAN_KEYWORDS = ["ご贈答用", "クラフトケース", "クラフト化粧箱", "豆入れ", "コーヒーサーバー", "V60"]

LIST_ITEM_PATTERN = re.compile(
    r'pid=(\d+)">(?:<img[^>]*/>)?([^<]+)</a><br />\s*販売価格[：:](\d+)円', re.DOTALL
)
COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*\});", re.DOTALL)
DETAIL_LABEL_PATTERN = re.compile(r"■\s*([^\s　]+)[\s　]+(.+)")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    soup = BeautifulSoup(resp.text, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    return soup


def scrape_list_items() -> list[dict]:
    resp = requests.get(LIST_URL, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-jp"

    items = []
    for m in LIST_ITEM_PATTERN.finditer(resp.text):
        pid, raw_name, price = m.group(1), m.group(2).strip(), int(m.group(3))
        items.append({"pid": pid, "raw_name": raw_name, "price": price})
    return items


def extract_colorme_product(soup: BeautifulSoup) -> dict | None:
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        m = COLORME_JSON_PATTERN.search(text)
        if not m:
            continue
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return None
        return data.get("product")
    return None


def parse_detail_labels(soup: BeautifulSoup) -> dict:
    detail_el = soup.select_one("div.detail_text")
    if not detail_el:
        return {}
    text = detail_el.get_text()
    labels = {}
    for line in text.split("\n"):
        m = DETAIL_LABEL_PATTERN.match(line.strip())
        if m:
            labels[m.group(1).strip()] = m.group(2).strip()
    return labels


def build_record(item: dict) -> dict:
    title = item["raw_name"]
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

    detail_url = item["url"]
    soup = fetch_page(detail_url)
    product = extract_colorme_product(soup)
    labels = parse_detail_labels(soup)

    if labels.get("生産国"):
        country = detect_country_name(labels["生産国"])
        if country:
            parsed["origin_country"] = country
            parsed["origin_source"] = "product_description"
    parsed = apply_category_hint_fallback(parsed, None)

    if labels.get("精製方法"):
        parsed["processing_method"] = normalize_processing_method(labels["精製方法"])

    if (
        not labels
        and not parsed.get("origin_country")
        and parsed.get("category") != "ブレンド"
    ):
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "non_bean": True,
            "product_url": detail_url,
        }

    farm_note_parts = []
    if labels.get("産地"):
        farm_note_parts.append(f"産地: {labels['産地']}")
    if labels.get("生産者"):
        farm_note_parts.append(f"生産者: {labels['生産者']}")
    if labels.get("品種"):
        farm_note_parts.append(f"品種: {labels['品種']}")
    if labels.get("標高"):
        farm_note_parts.append(f"標高: {labels['標高']}")
    farm_note = "、".join(farm_note_parts) if farm_note_parts else None

    stock_num = product.get("stock_num") if product else None
    structural_out_of_stock = isinstance(stock_num, int) and stock_num <= 0
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
        "farm_note": farm_note,
        "blend_components": [],
        "price": item["price"],
        "weight_g": None,  # 理由はモジュールdocstring参照(商品名・説明文に重量表記が無い)
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": detail_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict], list[dict]]:
    list_items = scrape_list_items()
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    non_bean_records = []
    for item in list_items:
        raw_name = item["raw_name"]
        if any(kw in raw_name for kw in NON_BEAN_KEYWORDS):
            continue

        product_url = f"{BASE_URL}?pid={item['pid']}"
        prev = previous.get(product_url)
        if is_unchanged(prev, raw_name=raw_name, price=item["price"]):
            records.append(prev)
            continue

        try:
            detail = build_record({**item, "url": product_url})
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue

        if detail.get("non_bean"):
            non_bean_records.append(detail)
        elif detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records, non_bean_records


if __name__ == "__main__":
    records, flavored_records, non_bean_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
        "non_bean_products_excluded": non_bean_records,
    }
    with open("data_lotuscoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_lotuscoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件、"
          f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
