# -*- coding: utf-8 -*-
"""
scrape_forest.py

フォレスト自家焙煎コーヒー豆店(nsforest.com)の商品情報を取得する。
神奈川県横浜市泉区緑園。

これまでのカラーミーショップ系のスクレイパーと異なり、WordPress + Welcart
(ウェルカートショッピングカート、クラス名に"usces"/"ss_"接頭辞)というこの
プロジェクト初のプラットフォーム(実データ確認済み、2026-08時点)。robots.txtは
標準的なWordPressの/wp-admin/除外のみで、実質全面許可。

【カテゴリ構造による非コーヒー豆の除外】
サイト側で商品を「allcoffee(コーヒー豆全体)」「asairi(浅煎り)」「fukairi(深煎り)」
「icecoffee」「itemreco(おすすめ)」「sonota(その他=ギフトセット・ドリップバッグ・
フィルター等の器具)」というタクソノミーで分類しており、"allcoffee"タクソノミーが
既にコーヒー豆商品のみに絞られていることを実データで確認済み(sonotaにギフト
セット・ドリップバッグ・フィルターが分離されている)。そのためこのスクレイパーは
"allcoffee"の一覧ページのみを対象とし、キーワードベースの非コーヒー豆除外ロジックは
持たない(該当カテゴリに属する時点で除外不要と判断できるため)。

【商品説明の構造】
div.accordion-body.item-description(entry-content、WordPress標準の本文)は
自由記述の段落(<p>)の並びで、店舗ごとの構造化ラベル(th/td形式)は無い。ただし
実データ調査で、産地情報のみ"■産地"という見出し行の後に複数行(国名、
地域+農園名、「規格：」「品種：」「標高：」「Qグレード認証：」等のラベル付き行が
混在)で記載されるパターンを確認したため、この見出し以降の連続する行を
farm_noteとしてまとめて保持する(店舗ごとの表記ゆれが大きく、個別ラベルへの
精密な分解は行わない)。ブレンド商品(例:「モカマイルド」)にはこの"■産地"
セクション自体が無いことも多く、その場合farm_noteはNoneのままになる。

【焙煎度について】
TSUKIKOYA/Mameya等と異なり、焙煎度は商品ごとに固定(「○○ 浅煎り」「深煎り ○○」
のように商品名に焙煎度が直書きされ、注文時に選べるバリアントではない。実データ
確認済み: dl.item-optionは「挽き方」のみで焙煎度の選択肢は無い)。ROAST_LEVELS
(8段階のカタカナ表記)とは粒度が異なる2段階表記(浅煎り/深煎り)のため、
roast_levelには入れずroast_hintとして保持する。

【重量・価格について】
dl.item-skuの重量セレクタ(100g/150g/200g/300g/500g/1kg/1.5kg)はどの商品も
共通の並びで、デフォルト選択(先頭のoption)が常に100g(実データ確認済み)。
価格はspan.sell_price.ss_price(構造化データ、デフォルト選択=100gの価格)を
採用する。
"""

import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    detect_colombia_grade,
    detect_processing_method,
    detect_stock_status,
)
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "フォレスト自家焙煎コーヒー豆店",
    "url": "https://www.nsforest.com/",
    "platform": "WordPress + Welcart",
    "address": "神奈川県横浜市泉区緑園6-1-27",
    "prefecture": "神奈川県",
    "robots_txt_status": "許可(2026-08確認。/wp-admin/以外は制限なし、標準的なWordPress設定)",
}

CRAWL_DELAY_SECONDS = 1
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

BASE_URL = "https://www.nsforest.com/"
LIST_URL = "https://www.nsforest.com/category/item/itemgenre/allcoffee/"

WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")
# get_text("\n")は段落(<p>)境界も<br />境界も同じ単一の"\n"区切りに均してしまう
# (実データ確認済み: 段落間に空行は残らない)ため、次の既知セクション見出しが
# 現れる直前までを非貪欲にキャプチャする(「■産地」ブロックの直後には
# 「賞味期限：」または「保存方法：」が続くパターンを実データで確認済み)。
ORIGIN_SECTION_PATTERN = re.compile(r"■産地\n(.*?)(?=\n賞味期限：|\n保存方法：|\Z)", re.DOTALL)
GRADE_LABEL_PATTERN = re.compile(r"規格：([^\n]+)")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def parse_description(description_text: str) -> dict:
    text = description_text or ""
    origin_match = ORIGIN_SECTION_PATTERN.search(text)
    farm_note = None
    if origin_match:
        lines = [ln.strip() for ln in origin_match.group(1).split("\n") if ln.strip()]
        farm_note = "、".join(lines) if lines else None

    grade_match = GRADE_LABEL_PATTERN.search(text)
    grade = grade_match.group(1).strip() if grade_match else None

    return {"farm_note": farm_note, "grade": grade}


def build_record(product_url: str, title: str, description_text: str, price: int | None, weight_g: int | None,
                  stock_text: str | None) -> dict:
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

    desc = parse_description(description_text)
    if desc["grade"]:
        # 「規格：」欄はコロンビア産の場合サブグレード名(「スプレモ」等)が単独で
        # 書かれており、parse_product()と同じくFNCの「エクセルソ+サブ名」複合語に
        # 正規化する(正規化できなければ、情報を失わないよう元の表記のまま使う)。
        if parsed["origin_country"] == "コロンビア":
            parsed["grade"] = detect_colombia_grade(desc["grade"]) or desc["grade"]
        else:
            parsed["grade"] = desc["grade"]
    if not parsed["processing_method"]:
        parsed["processing_method"] = detect_processing_method(description_text)
    parsed = apply_category_hint_fallback(parsed, None)

    roast_hint = None
    if "浅煎り" in title:
        roast_hint = "浅煎り"
    elif "深煎り" in title:
        roast_hint = "深煎り"

    structural_out_of_stock = bool(stock_text) and "販売中" not in stock_text
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
        "roast_level": None,  # 2段階(浅煎り/深煎り)でROAST_LEVELSの8段階と粒度が異なるため未設定
        "roast_hint": roast_hint,
        "roast_selectable": False,  # 焙煎度は商品ごとに固定、注文時に選べるのは挽き方のみ(実データ確認済み)
        "post_processing_tags": parsed["post_processing_tags"],
        "farm_note": desc["farm_note"],
        "flavor_notes": None,
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def parse_product_detail(url: str) -> dict:
    soup = fetch_page(url)

    title_el = soup.select_one("h1.item-name")
    title = title_el.get_text(strip=True) if title_el else ""

    desc_el = soup.select_one("div.item-description")
    description_text = desc_el.get_text("\n") if desc_el else ""

    price_el = soup.select_one("span.sell_price")
    price = None
    if price_el:
        price_match = re.search(r"([\d,]+)", price_el.get_text())
        if price_match:
            price = int(price_match.group(1).replace(",", ""))

    weight_g = None
    weight_option = soup.select_one("dl.item-sku option[selected]")
    if weight_option:
        m = WEIGHT_PATTERN.search(weight_option.get_text())
        if m:
            weight_g = int(m.group(1))

    stock_el = soup.select_one("span.ss_stockstatus")
    stock_text = stock_el.get_text(strip=True) if stock_el else None

    return build_record(url, title, description_text, price, weight_g, stock_text)


def scrape_product_list_page() -> list[dict]:
    soup = fetch_page(LIST_URL)
    items = soup.select("article.g-col-6")

    results = []
    for item in items:
        link_el = item.select_one("a[href]")
        title_el = item.select_one("h3.card-title.item-name")
        price_el = item.select_one("div.card-text.item-price")
        if not link_el or not title_el:
            continue

        title = title_el.get_text(strip=True)
        product_url = link_el.get("href", "")

        price = None
        if price_el:
            price_match = re.search(r"([\d,]+)", price_el.get_text())
            if price_match:
                price = int(price_match.group(1).replace(",", ""))

        results.append({"raw_name": title, "product_url": product_url, "price": price})
    return results


def scrape_all_products() -> tuple[list[dict], list[dict], list[dict]]:
    all_list_items = scrape_product_list_page()

    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    non_bean_records = []
    for item in all_list_items:
        prev = previous.get(item["product_url"])
        if is_unchanged(prev, raw_name=item["raw_name"], price=item.get("price")):
            records.append(prev)
            continue

        try:
            detail = parse_product_detail(item["product_url"])
            detail["out_of_stock"] = detail.get("stock_status", "販売中") != "販売中"
            if detail.get("non_bean"):
                non_bean_records.append(detail)
            elif detail.get("is_flavored"):
                flavored_records.append(detail)
            else:
                records.append(detail)
            time.sleep(CRAWL_DELAY_SECONDS)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['product_url']} ({e})")

    return records, flavored_records, non_bean_records


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) > 1:
        result = parse_product_detail(sys.argv[1])
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        records, flavored_records, non_bean_records = scrape_all_products()
        output = {
            "shop": SHOP_INFO,
            "products": records,
            "flavored_products_excluded": flavored_records,
            "non_bean_products_excluded": non_bean_records,
        }
        with open("data_forest.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_forest.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件、"
              f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
