# -*- coding: utf-8 -*-
"""
scrape_terminal.py

COFFEE TERMINAL(神奈川県横浜市都筑区)の商品情報を取得する。「?mode=f3」という
見慣れないURL(ユーザー提示)はColorMe(カラーミーショップ)の「フリーページ」
機能(mode=f1/f2/f3...という連番の静的コンテンツページ)であり、特別な別
プラットフォームではない(実データ確認済み、2026-08時点。colorme_ATID/
colorme_PHPSESSIDのcookie、robots.txtの記述ともにこれまでのカラーミー
ショップ店舗と同一)。ただしテーマはこれまでのどの店舗(TSUKIKOYA/Mameya/405/
TERA/PHILOCOFFEA/Roast Design/Rhizomag)とも異なる(実データ確認済み: 一覧は
a.itemWrap/p.itemName/p.itemPrice、詳細ページの説明文はdiv.product_description)。

【注文オプションの構造】
variantsのoption1_valueは「焙煎名＋挽き方」を1つの文字列に連結したもの
(例:「ビターロースト　エスプレッソ用（極細挽き）」)、option2_valueは
「重量：価格」を1つの文字列に連結したもの(例:「100ｇ：950円（税込）」、
まとめ買い割引が重量ごとに異なる)。焙煎名は実データ確認済みで商品名自体にも
「ビター」「ソフト」「ライト」という接尾辞として含まれているため(例:
「グァテマラ SHBビター」「アロマブレンド（ソフト テイスト）」)、option1_value
のパースはせず商品名からroast_hintを判定する。重量・価格はoption2_valueの
うち最小重量(=最も基本的な単位)を正規表現で抽出する。

【一覧ページのJSプレースホルダーについて】
一覧ページの一部商品(実データ確認済み、原因不明・関連商品ウィジェット等の
未置換テンプレートと推測される)で商品名が literal な「' + name + '」という
JavaScriptテンプレート文字列のまま出力されていることがある。空文字列や
このプレースホルダーはスキップする。

【非コーヒー豆商品について】
HARIO製ミル・フィルター・サーバー・ドリッパー・ケトル等の器具、オリジナル
手ぬぐい、ドリップパック・コールドブリュー等の別形態、ギフトセット/ギフトBOX
商品が実データで確認できたため、一覧段階でキーワード除外する。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    normalize_processing_method,
    detect_stock_status,
)
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "COFFEE TERMINAL",
    "url": "https://www.coffee-terminal.net/",
    "platform": "カラーミーショップ(shop-pro.jp、独自ドメイン)",
    "address": "神奈川県横浜市都筑区葛が谷14-7",
    "prefecture": "神奈川県",
    "robots_txt_status": "許可(2026-08確認。/secure/と/cart/以外は制限なし。"
                          "PHILOCOFFEA等と同一の記述)",
}

CRAWL_DELAY_SECONDS = 1
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

BASE_URL = "https://www.coffee-terminal.net/"
LIST_BASE_URL = "https://www.coffee-terminal.net/?mode=srh&keyword=&sort=n"

# 実データ確認済み(2026-08時点): コーヒー豆ではない商品(器具・グッズ・別形態・ギフト等)
NON_BEAN_KEYWORDS = [
    "HARIO", "ハリオ", "手ぬぐい", "ドリップパック", "COLD BREW", "COLDBREW",
    "ギフト", "GIFT", "セット", "お試しパック",
]

COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*\});", re.DOTALL)
IMG_TAG_PATTERN = re.compile(r"<img[^>]*/?>", re.IGNORECASE)
WEIGHT_PRICE_PATTERN = re.compile(r"(\d+)\s*[gｇ]\s*[:：]\s*([\d,]+)\s*円")
LABEL_PATTERN = re.compile(r"(生産地|標高|品種|精選方法)：\s*([^\n]+)")
ROAST_HINT_TERMS = ["ビター", "ソフト", "ライト"]


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-jp"  # 実データ確認済み(Content-Type: text/html; charset=EUC-JP)
    soup = BeautifulSoup(resp.text, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    return soup


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


def clean_title(raw_title: str) -> str:
    without_img = IMG_TAG_PATTERN.sub("", raw_title or "")
    return without_img.strip()


def smallest_weight_price(colorme_product: dict) -> tuple[int | None, int | None]:
    best = None  # (weight_g, price)
    for variant in colorme_product.get("variants", []):
        m = WEIGHT_PRICE_PATTERN.search(variant.get("option2_value") or "")
        if not m:
            continue
        weight_g = int(m.group(1))
        price = int(m.group(2).replace(",", ""))
        if best is None or weight_g < best[0]:
            best = (weight_g, price)
    return best if best else (None, colorme_product.get("sales_price_including_tax"))


def build_record(product_url: str, colorme_product: dict, description_text: str) -> dict:
    title = clean_title(colorme_product.get("name") or "")
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": colorme_product.get("sales_price_including_tax"),
            "product_url": product_url,
        }

    labels = {label: value.strip() for label, value in LABEL_PATTERN.findall(description_text or "")}
    if labels.get("精選方法") and not parsed["processing_method"]:
        parsed["processing_method"] = normalize_processing_method(labels["精選方法"])
    parsed = apply_category_hint_fallback(parsed, None)

    non_bean_check_failed = (
        not labels and not parsed.get("origin_country") and parsed.get("category") != "ブレンド"
    )
    if non_bean_check_failed:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "non_bean": True,
            "product_url": product_url,
        }

    farm_note_parts = []
    if labels.get("生産地"):
        farm_note_parts.append(f"生産地: {labels['生産地']}")
    if labels.get("標高"):
        farm_note_parts.append(f"標高: {labels['標高']}")
    if labels.get("品種"):
        farm_note_parts.append(f"品種: {labels['品種']}")
    farm_note = "、".join(farm_note_parts) if farm_note_parts else None

    roast_hint = next((term for term in ROAST_HINT_TERMS if term in title), None)

    decaf_process = "デカフェ(除去方法の詳細記載なし)" if "カフェインレス" in title or "デカフェ" in title else None

    weight_g, price = smallest_weight_price(colorme_product)

    stock_num = colorme_product.get("stock_num")
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
        "roast_level": None,  # 「ビター/ソフト/ライト」独自表記でROAST_LEVELSの8段階と粒度が異なるため未設定
        "roast_hint": roast_hint,
        "roast_selectable": False,  # 焙煎は商品ごとに固定、注文時に選べるのは挽き方のみ(実データ確認済み)
        "post_processing_tags": parsed["post_processing_tags"],
        "farm_note": farm_note,
        "flavor_notes": None,
        "blend_components": [],
        "decaf_process": decaf_process,
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def parse_product_detail(url: str) -> dict:
    soup = fetch_page(url)
    colorme_product = extract_colorme_product(soup)
    if not colorme_product:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": "",
            "non_bean": True,
            "product_url": url,
        }

    body_el = soup.select_one("div.product_description")
    description_text = body_el.get_text() if body_el else ""

    return build_record(url, colorme_product, description_text)


def scrape_product_list_page(page: int) -> list[dict]:
    url = LIST_BASE_URL if page == 1 else f"{LIST_BASE_URL}&page={page}"
    soup = fetch_page(url)
    items = soup.select("a.itemWrap")

    results = []
    for item in items:
        name_el = item.select_one("p.itemName")
        price_el = item.select_one("p.itemPrice")
        if not name_el:
            continue

        title = clean_title(name_el.get_text())
        # JSテンプレートの未置換プレースホルダー、または空文字列をスキップ(実データ確認済み)
        if not title or "' + name + '" in title:
            continue
        if any(kw in title for kw in NON_BEAN_KEYWORDS):
            continue

        href = item.get("href", "")
        product_url = f"{BASE_URL}{href}" if href.startswith("?") else href

        price = None
        if price_el:
            price_match = re.search(r"([\d,]+)円", price_el.get_text())
            if price_match:
                price = int(price_match.group(1).replace(",", ""))

        stock_status = detect_stock_status(title)

        results.append({
            "raw_name": title,
            "product_url": product_url,
            "price": price,
            "stock_status": stock_status,
        })
    return results


def scrape_all_products() -> tuple[list[dict], list[dict], list[dict]]:
    all_list_items = {}
    page = 1
    while True:
        items = scrape_product_list_page(page)
        if not items:
            break
        for item in items:
            all_list_items[item["product_url"]] = item
        page += 1
        time.sleep(CRAWL_DELAY_SECONDS)

    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    non_bean_records = []
    for item in all_list_items.values():
        prev = previous.get(item["product_url"])
        if is_unchanged(
            prev,
            raw_name=item["raw_name"],
            price=item.get("price"),
            stock_status=item["stock_status"],
        ):
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
        with open("data_terminal.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_terminal.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件、"
              f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
