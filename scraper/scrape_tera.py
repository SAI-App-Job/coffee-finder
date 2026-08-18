# -*- coding: utf-8 -*-
"""
scrape_tera.py

TERA COFFEE and ROASTER(神奈川県横浜市港北区大倉山)の商品情報を取得する。
公式サイト(teracoffee.jp)自体は情報サイトで、実際の販売は別ドメインの
shop.teracoffee.jp(カラーミーショップ、独自ドメイン)上で行われている。

Mameya Roastery(scrape_mameya.py)と全く同じテーマ(実データ確認済み、2026-08時点:
一覧はli.c-item-list__item、詳細ページの説明文はdiv.p-product-explain__body)。
ただしMameyaと異なり、商品名自体が<br/>区切りの複数セグメント
(商品名<br/>(地域・農園)<br/>【焙煎タイプ】<br/>重量)になっているため
TSUKIKOYAのclean_name_segments()相当のセグメント分割が必要。

【焙煎度について】
Mameyaと異なり注文時選択のバリアントではなく、商品ごとに固定
(var Colorme のvariantsはoption1_value=挽き方のみ、option2_valueは常に空文字列、
実データ確認済み)。説明文中の「■ローストタイプ：ミディアムロースト（浅いり）」
という表記から、ROAST_LEVELS(8段階のカタカナ表記)の語をそのまま拾えるため、
roast_levelとして正規化して保持する(TSUKIKOYAの浅煎り/中煎り/深煎りのような
簡易表記ではなく、Mameyaと同じ「ライト/シナモン/…/イタリアン」表記のため)。
「フルシティ」が「シティ」を部分文字列として含むため、判定は文字列長の長い順に
試す(coffee_parser.ROAST_KEYWORDSの単純なfor-in部分一致だと「フルシティロースト」
が「シティ」に誤判定される問題が実データ確認前の設計検討で判明したため回避)。

【非コーヒー豆商品について】
カタログの約半数がタンブラー・ボトル・トートバッグ・ドリッパー・ミル・
コーヒーゼリー/プリン/ようかん/グラノーラ・ギフトセット等の非コーヒー豆商品
(実データ確認済み)。一覧段階でのキーワード除外に加え、詳細ページ側でも
「■」付きラベルが一切無く産地国も検出できずカテゴリがブレンドでない場合を
非コーヒー豆として除外する(TSUKIKOYA/405/Mameyaと同じ構造的フォールバック)。

【ブレンド商品の産地ラベルについて】
ストレート商品は「■生産国：コスタリカ」のように単一国名だが、ブレンド商品は
「■生豆生産国：エチオピアW、グアテマラ、ペルー」のように複数国のカンマ区切りで
ラベル名も異なる(実データ確認済み)。単一originCountryフィールドに複数国を
無理に押し込めないため、ブレンド商品ではこのラベル値をorigin_countryには
使わずfarm_noteに含めるに留める。
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
    detect_country_name,
    ROAST_KEYWORDS,
)
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "TERA COFFEE and ROASTER",
    "url": "https://teracoffee.jp/",
    "platform": "カラーミーショップ(shop-pro.jp、独自ドメイン)",
    "address": "神奈川県横浜市港北区大倉山1丁目3-20",
    "prefecture": "神奈川県",
    "robots_txt_status": "許可(2026-08確認。/secure/と/cart/以外は制限なし。"
                          "PHILOCOFFEA等と同一の記述)",
}

CRAWL_DELAY_SECONDS = 1
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

BASE_URL = "https://shop.teracoffee.jp/"
LIST_BASE_URL = "https://shop.teracoffee.jp/?mode=srh&keyword=&sort=n"

# 実データ確認済み(2026-08時点): コーヒー豆ではない商品(カップ・器具・スイーツ・ギフト等)
NON_BEAN_KEYWORDS = [
    "CERAMUG", "トートバッグ", "エコバッグ", "ドリッパー", "ミル", "グラインダー",
    "ゼリー", "プリン", "ようかん", "グラノーラ", "チョコレート",
    "ギフトセット", "ギフトボックス", "豆缶", "BOX", "リキッド",
    "ダンクバッグ", "水出し",  # 豆・粉ではなくドリップバッグ相当の別形態(実データ確認済み)
]

COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*\});", re.DOTALL)
IMG_TAG_PATTERN = re.compile(r"<img[^>]*/?>", re.IGNORECASE)
BR_TAG_PATTERN = re.compile(r"<br\s*/?>", re.IGNORECASE)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")
LABEL_PATTERN = re.compile(r"■(ローストタイプ|生産国|生豆生産国|地域|農地|標高|品種|精製)：\s*([^\n]+)")

ROAST_TERMS_BY_LENGTH = sorted(ROAST_KEYWORDS.keys(), key=len, reverse=True)


def normalize_roast_label(value: str | None) -> str | None:
    if not value:
        return None
    for term in ROAST_TERMS_BY_LENGTH:
        if term in value:
            return ROAST_KEYWORDS[term]
    return None


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


def clean_name_segments(raw_name_html: str) -> list[str]:
    without_img = IMG_TAG_PATTERN.sub("", raw_name_html or "")
    # 実データ確認済み: TERAのvar Colorme のproduct.nameは<br/>(スペース無し、
    # TSUKIKOYAで見られた<br>とは異なる自己終端表記)区切り。BR_TAG_PATTERNで
    # 表記ゆれを吸収する
    normalized = BR_TAG_PATTERN.sub("\n", without_img).replace("\r", "")
    segments = [seg.strip() for seg in normalized.split("\n")]
    return [seg for seg in segments if seg]


def parse_description(description_text: str) -> dict:
    labels = {label: value.strip() for label, value in LABEL_PATTERN.findall(description_text or "")}
    return labels


def build_record(product_url: str, colorme_product: dict, description_text: str) -> dict:
    segments = clean_name_segments(colorme_product.get("name") or "")
    display_name = segments[0] if segments else ""
    full_text = " ".join(segments)

    weight_m = WEIGHT_PATTERN.search(full_text)
    weight_g = int(weight_m.group(1)) if weight_m else None
    if weight_g:
        display_name = f"{display_name} ({weight_g}g)"

    parsed = parse_product(full_text)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": display_name,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": colorme_product.get("sales_price_including_tax"),
            "product_url": product_url,
        }

    labels = parse_description(description_text)

    if labels.get("精製"):
        parsed["processing_method"] = normalize_processing_method(labels["精製"])

    country_label = labels.get("生産国") or labels.get("生豆生産国")
    if country_label and parsed["category"] != "ブレンド" and not parsed["origin_country"]:
        country = detect_country_name(country_label)
        if country:
            parsed["origin_country"] = country
            parsed["origin_source"] = "product_description"
    parsed = apply_category_hint_fallback(parsed, None)

    non_bean_check_failed = (
        not labels and not parsed.get("origin_country") and parsed.get("category") != "ブレンド"
    )
    if non_bean_check_failed:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": display_name,
            "non_bean": True,
            "product_url": product_url,
        }

    farm_note_parts = []
    if country_label and parsed["category"] == "ブレンド":
        farm_note_parts.append(f"生豆生産国: {country_label}")
    if labels.get("地域"):
        farm_note_parts.append(f"地域: {labels['地域']}")
    if labels.get("農地"):
        farm_note_parts.append(f"農地: {labels['農地']}")
    if labels.get("標高"):
        farm_note_parts.append(f"標高: {labels['標高']}")
    if labels.get("品種"):
        farm_note_parts.append(f"品種: {labels['品種']}")
    farm_note = "、".join(farm_note_parts) if farm_note_parts else None

    roast_level = normalize_roast_label(labels.get("ローストタイプ"))

    decaf_process = "デカフェ(除去方法の詳細記載なし)" if "デカフェ" in full_text else None

    stock_num = colorme_product.get("stock_num")
    structural_out_of_stock = isinstance(stock_num, int) and stock_num <= 0
    stock_status = detect_stock_status(display_name, structural_out_of_stock)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": display_name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_hint": labels.get("ローストタイプ"),
        "roast_selectable": False,  # 焙煎度は商品ごとに固定、注文時に選べるのは挽き方のみ(実データ確認済み)
        "post_processing_tags": parsed["post_processing_tags"],
        "farm_note": farm_note,
        "flavor_notes": None,
        "blend_components": [],
        "decaf_process": decaf_process,
        "price": colorme_product.get("sales_price_including_tax"),
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

    body_el = soup.select_one("div.p-product-explain__body")
    description_text = body_el.get_text() if body_el else ""

    return build_record(url, colorme_product, description_text)


def scrape_product_list_page(page: int) -> list[dict]:
    url = LIST_BASE_URL if page == 1 else f"{LIST_BASE_URL}&page={page}"
    soup = fetch_page(url)
    items = soup.select("li.c-item-list__item")

    results = []
    for item in items:
        ttl_el = item.select_one("div.c-item-list__ttl a")
        price_el = item.select_one("div.c-item-list__price")
        if not ttl_el:
            continue

        segments = clean_name_segments(ttl_el.get_text())
        display_name = segments[0] if segments else ""
        full_text = " ".join(segments)
        if any(kw in full_text for kw in NON_BEAN_KEYWORDS):
            continue

        href = ttl_el.get("href", "")
        product_url = f"{BASE_URL}{href}" if href.startswith("?") else href

        price = None
        sold_out = False
        if price_el:
            price_text = price_el.get_text()
            price_match = re.search(r"([\d,]+)円", price_text)
            if price_match:
                price = int(price_match.group(1).replace(",", ""))
            sold_out = "売り切れ" in price_text

        stock_status = detect_stock_status(display_name, sold_out)

        results.append({
            "raw_name": display_name,
            "product_url": product_url,
            "price": price,
            "stock_status": stock_status,
        })
    return results


def scrape_all_products() -> tuple[list[dict], list[dict], list[dict]]:
    all_list_items = []
    page = 1
    while True:
        items = scrape_product_list_page(page)
        if not items:
            break
        all_list_items.extend(items)
        page += 1
        time.sleep(CRAWL_DELAY_SECONDS)

    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    non_bean_records = []
    for item in all_list_items:
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
        with open("data_tera.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_tera.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件、"
              f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
