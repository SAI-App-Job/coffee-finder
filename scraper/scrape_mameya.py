# -*- coding: utf-8 -*-
"""
scrape_mameya.py

Mameya Roastery(coffee-mameya.co.jp、独自ドメインで運用されているカラーミー
ショップ)の商品情報を取得する。神奈川県横浜市中区伊勢佐木町。

scrape_tsukikoya.pyをテンプレートに実装しているが、このテーマは
TSUKIKOYA/PHILOCOFFEA/Roast Design Coffee/Rhizomag/405いずれとも異なる
(実データ確認済み、2026-08時点。一覧は li.c-item-list__item / div.c-item-list__ttl
/ div.c-item-list__price、詳細ページの説明文は div.p-product-explain__body)。

【文字コード】EUC-JP(実データ確認済み)。resp.encodingを明示的に設定する必要がある。

【一覧ページの商品名について】
一部商品(新着マーク付き)は<a class="c-item-list__ttl">の中に
`<img class='new_mark_img1' .../>`という「NEW」バッジ画像がリテラルに
埋め込まれており、商品名テキストの前に混入する。IMG_TAG_PATTERNで除去する。

【焙煎度について】
variantsのoption1_valueが焙煎度(おまかせ/ライト(極浅煎り)〜イタリアン(超極深煎り)/
こだわり)、option2_valueが挽き方という並びで全商品共通(TSUKIKOYAと異なり
スロットの入れ替わりは無い、実データ確認済み)。ほぼ全商品が同じ10択(標準8段階
+おまかせ+こだわり)を持つため、実質的に「どの商品も焙煎度は注文時選択」という
運用になっている。ROAST_LEVELS(8段階のカタカナ表記)と語彙は一致するが、
「注文時に選べる」という性質上roast_levelとしては固定できないためNoneのままにし、
商品説明文中の「おすすめのロースト：」というラベル(店舗のおすすめ焙煎度、例:
「ミディアムハイロースト」のようにROAST_LEVELSの8段階と厳密には一致しない
表記も実データで確認済み)をそのままroast_hintとして保持する。

【非コーヒー豆商品について】
商品説明文(div.p-product-explain__body)に「おすすめのロースト：」「内容量：」等の
ラベルが一切無く、産地国名も商品名から検出できず、カテゴリもブレンドでない場合を
非コーヒー豆として除外する(実データ確認済み: リキッドアイスコーヒー、キャンバス
トート、Tシャツの3商品がこのパターンに該当)。なお「【白黒別注】バーチカル
ブレンド」という商品は説明文が空(「※こちらは業者専用ページです」とのみ記載)だが、
商品名に「ブレンド」を含みカテゴリがブレンドと判定されるため上記の除外条件には
かからず、情報が乏しいまま通常商品として扱われる(業者専用の卸売ページと思われるが、
実在するコーヒー豆商品であることは確からしいため、あえて特別扱いの除外はしない)。
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
)
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "Mameya Roastery",
    "url": "https://www.coffee-mameya.co.jp/",
    "platform": "カラーミーショップ(shop-pro.jp、独自ドメイン)",
    "address": "神奈川県横浜市中区伊勢佐木町5-126",
    "prefecture": "神奈川県",
    "robots_txt_status": "許可(2026-08確認。/secure/と/cart/以外は制限なし。"
                          "PHILOCOFFEA等と同一の記述)",
}

CRAWL_DELAY_SECONDS = 1
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

BASE_URL = "https://www.coffee-mameya.co.jp/"
LIST_BASE_URL = "https://www.coffee-mameya.co.jp/?mode=srh&keyword=&sort=n"

# 実データ確認済み(2026-08時点): コーヒー豆ではない商品
NON_BEAN_KEYWORDS = ["リキッドアイスコーヒー", "トート", "Tシャツ"]

COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*\});", re.DOTALL)
IMG_TAG_PATTERN = re.compile(r"<img[^>]*/?>", re.IGNORECASE)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")
LABEL_PATTERN = re.compile(r"(おすすめのロースト|プロセシング|栽培品種|内容量)：\s*([^\n]+)")


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
    """NEWバッジ画像タグの混入除去+前後空白のトリム(実データ確認済み)。"""
    without_img = IMG_TAG_PATTERN.sub("", raw_title or "")
    return without_img.strip()


def parse_description(description_text: str) -> dict:
    labels = {label: value.strip() for label, value in LABEL_PATTERN.findall(description_text or "")}
    return labels


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

    labels = parse_description(description_text)

    if labels.get("プロセシング"):
        parsed["processing_method"] = normalize_processing_method(labels["プロセシング"])
    if not parsed["origin_country"]:
        country = detect_country_name(title)
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
            "raw_name": title,
            "non_bean": True,
            "product_url": product_url,
        }

    farm_note = f"品種: {labels['栽培品種']}" if labels.get("栽培品種") else None

    weight_g = None
    if labels.get("内容量"):
        m = WEIGHT_PATTERN.search(labels["内容量"])
        if m:
            weight_g = int(m.group(1))

    variants = colorme_product.get("variants", [])
    roast_options = sorted({v.get("option1_value") for v in variants if v.get("option1_value")})
    roast_selectable = len(roast_options) > 1

    decaf_process = None
    if "カフェインレス" in title or "デカフェ" in title:
        decaf_process = (
            f"{labels['プロセシング']}によりカフェインを除去" if labels.get("プロセシング")
            else "デカフェ(除去方法の詳細記載なし)"
        )

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
        "roast_level": None,  # 注文時にほぼ全商品で焙煎度を選択できる運用のため固定できない
        "roast_hint": labels.get("おすすめのロースト"),
        "roast_selectable": roast_selectable,
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

        title = clean_title(ttl_el.get_text())
        if any(kw in title for kw in NON_BEAN_KEYWORDS):
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

        stock_status = detect_stock_status(title, sold_out)

        results.append({
            "raw_name": title,
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
        with open("data_mameya.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_mameya.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件、"
              f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
