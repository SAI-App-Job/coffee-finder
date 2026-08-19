# -*- coding: utf-8 -*-
"""
scrape_shibacoffee.py

SHIBACOFFEE(神奈川県川崎市中原区新丸子東)の商品情報を取得する。
カラーミーショップ(shop-pro.jp)。一覧のテーマは405 COFFEE ROASTERSと同じ
prd_lst_unit/prd_lst_name/prd_lst_price系(実データ確認済み、2026-08時点)。

【一覧ページのみで完結する設計について】
scrape_philocoffea.py系(詳細ページを個別取得して商品説明から産地・精選方法等を
抽出する設計)をテンプレートとして検討したが、実データ調査の結果、この店舗は
商品名自体に「《マーケティング文》国名 地域 農園【品種等】 200g〈ロースト表記/
簡易表記〉」という形で産地・地域・農園・品種・重量・焙煎度がすべて詰め込まれて
おり、詳細ページの説明文(div.product_exp)は構造化ラベルを一切持たない自由な
マーケティング文のみ(実データ確認済み)だった。そのため詳細ページを個別取得する
価値が薄く、一覧ページ(2ページ、実データ確認済み: 全34商品)だけで商品情報が
完結する設計にしている(店舗サーバーへのリクエスト数も抑えられる)。

【焙煎度について】
商品名末尾の〈...〉に「シティロースト/中深煎り」のようにROAST_LEVELS
(8段階のカタカナ表記)相当の語と簡易表記が併記されている。カタカナ表記の方は
coffee_parser.ROAST_KEYWORDSでそのまま正規化できるが、「フルシティ」が「シティ」
を部分文字列として含む問題があるため、既知の語を文字列長の長い順に照合する
(scrape_tera.pyと同じ対策)。

【非コーヒー豆商品について】
リキッドコーヒー(ボトル飲料)、KONO式ペーパーフィルター、コーヒーバッグ
(ドリップバッグ形式)、ギフト用手提げ紙袋、ギフトBOX、コーヒー豆ギフトセット
(複数種類の詰め合わせ)、お試しセットが実データで確認できたため、
一覧段階でキーワード除外する。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    detect_stock_status,
    ROAST_KEYWORDS,
)

SHOP_INFO = {
    "name": "SHIBACOFFEE",
    "url": "https://shibacoffee.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "神奈川県川崎市中原区新丸子東1-826 シャトレKOYO 1階",
    "prefecture": "神奈川県",
    "robots_txt_status": "許可(2026-08確認。/secure/と/cart/以外は制限なし。"
                          "PHILOCOFFEA等と同一の記述)",
}

CRAWL_DELAY_SECONDS = 1
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

BASE_URL = "https://shibacoffee.shop-pro.jp/"
LIST_BASE_URL = "https://shibacoffee.shop-pro.jp/?mode=srh&keyword=&sort=n"

# 実データ確認済み(2026-08時点): コーヒー豆ではない商品(飲料・器具・ギフト等)
NON_BEAN_KEYWORDS = [
    "リキッドコーヒー", "ペーパーフィルター", "コーヒーバッグ", "紙袋",
    "ギフトBOX", "ギフトセット", "お試しセット",
]

IMG_TAG_PATTERN = re.compile(r"<img[^>]*/?>", re.IGNORECASE)
MARKETING_PREFIX_PATTERN = re.compile(r"^(?:《[^》]*》|★[^★]*★|【[^】]*】)\s*")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
ROAST_BRACKET_PATTERN = re.compile(r"〈([^〉]+)〉")
FEATURE_BRACKET_PATTERN = re.compile(r"【([^】]+)】")

ROAST_TERMS_BY_LENGTH = sorted(ROAST_KEYWORDS.keys(), key=len, reverse=True)


def normalize_roast_bracket(value: str | None) -> str | None:
    if not value:
        return None
    for term in ROAST_TERMS_BY_LENGTH:
        if term in value:
            return ROAST_KEYWORDS[term]
    return None


def clean_title(raw_title: str) -> str:
    without_img = IMG_TAG_PATTERN.sub("", raw_title or "")
    without_prefix = MARKETING_PREFIX_PATTERN.sub("", without_img.strip())
    return without_prefix.strip()


def build_record(product_url: str, title: str, price: int | None) -> dict:
    roast_m = ROAST_BRACKET_PATTERN.search(title)
    roast_bracket = roast_m.group(1) if roast_m else None
    title_wo_roast = ROAST_BRACKET_PATTERN.sub("", title).strip()

    parsed = parse_product(title_wo_roast)

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

    parsed = apply_category_hint_fallback(parsed, None)

    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None

    features = FEATURE_BRACKET_PATTERN.findall(title_wo_roast)
    farm_note = f"特徴: {'、'.join(features)}" if features else None

    decaf_process = "デカフェ(除去方法の詳細記載なし)" if ("ディカフェ" in title or "カフェインレス" in title) else None

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
        "roast_level": normalize_roast_bracket(roast_bracket),
        "roast_hint": roast_bracket,
        "roast_selectable": False,  # 焙煎度は商品ごとに固定、注文時に選べるのは挽き方のみ(実データ確認済み)
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


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-jp"  # 実データ確認済み(Content-Type: text/html; charset=EUC-JP)
    return BeautifulSoup(resp.text, "html.parser")


def scrape_product_list_page(page: int) -> list[dict]:
    url = LIST_BASE_URL if page == 1 else f"{LIST_BASE_URL}&page={page}"
    soup = fetch_page(url)
    items = soup.select("li.prd_lst_unit")

    results = []
    for item in items:
        name_el = item.select_one("span.prd_lst_name a")
        price_el = item.select_one("span.prd_lst_price")
        if not name_el:
            continue

        title = clean_title(name_el.get_text())
        if any(kw in title for kw in NON_BEAN_KEYWORDS):
            continue

        href = name_el.get("href", "")
        product_url = f"{BASE_URL}{href}" if href.startswith("?") else href

        price = None
        if price_el:
            price_match = re.search(r"([\d,]+)円", price_el.get_text())
            if price_match:
                price = int(price_match.group(1).replace(",", ""))

        results.append(build_record(product_url, title, price))
    return results


def scrape_all_products() -> tuple[list[dict], list[dict], list[dict]]:
    records = []
    flavored_records = []
    non_bean_records = []

    page = 1
    while True:
        items = scrape_product_list_page(page)
        if not items:
            break
        for detail in items:
            if detail.get("non_bean"):
                non_bean_records.append(detail)
            elif detail.get("is_flavored"):
                flavored_records.append(detail)
            else:
                records.append(detail)
        page += 1
        time.sleep(CRAWL_DELAY_SECONDS)

    return records, flavored_records, non_bean_records


if __name__ == "__main__":
    records, flavored_records, non_bean_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
        "non_bean_products_excluded": non_bean_records,
    }
    with open("data_shibacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_shibacoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件、"
          f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
