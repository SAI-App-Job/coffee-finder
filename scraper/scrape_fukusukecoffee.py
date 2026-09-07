# -*- coding: utf-8 -*-
"""
scrape_fukusukecoffee.py

FUKUSUKE COFFEE ROASTERY(fukusukecoffee.jp、愛知県安城市、自家焙煎豆の
オンライン販売)の商品情報を取得する。MakeShop。

【テーマ違いについて】
実データ確認済み(2026-09時点): カフェコーデ(大和屋珈琲と同じ旧テーマ、
`/SHOP/<id>/list.html`+schema.org ProductGroup形式のJSON-LD)とは異なる
新しいMakeShopテーマを採用しており、URL構造が`/view/category/<slug>`
(カテゴリ)・`/view/item/<商品コード>`(商品詳細)になっている。商品詳細
ページにJSON-LDは存在せず(`application/ld+json`は0件)、商品名は
`<h2 class="product-name">`、価格は`data-id="makeshop-item-price:N">`
のspan要素(ページ読み込み時点でのデフォルト組み合わせ=最小重量の価格を
反映)から取得する。

robots.txt確認済み(2026-09時点): robots.txt自体が存在しない(404、旧EUC-JP
の404ページが返る)ため、Disallow指定は無く実質許可。

【対象カテゴリについて】
実データ確認済み: 「coffeebeans」カテゴリ(48件)が「singleorigin」
(29件)+「blendedcoffee」(19件)の和集合と完全一致しており、コーヒー豆
単品を指す唯一のカテゴリであることを確認済み。「icedcoffee」カテゴリ
(4件)は水出し珈琲パック(液体)のみでcoffeebeansと重複が無く対象外、
「decaf_beans」カテゴリ(1件)はcoffeebeansの部分集合のため別途巡回不要。
「dripbag」「gift」「goods」「coffeeset」等は焙煎豆単品を含まないため
対象外。

【重量について】
実データ確認済み: 商品バリエーション(容量を選ぶ<select>)の選択肢に
「150g」(基準)と「1kg（30%OFF）（+X円）」のような重量帯があり、
`makeshop-item-price:N`が表示するデフォルト価格は常に最小重量(150g)に
対応する。商品ごとにカスタムオプションのラベル・並び順が異なる
(旧テーマ由来のoption1/2/3 と 新テーマ由来のCS0000XXカスタムオプションが
混在)ため、<select>の並び順には依存せず、ページ全体の<option>要素群から
重量表記を検出し最小値を採用する方式にした。

【非コーヒー豆商品の除外について】
実データ確認済み(coffeebeans全48件): 「オープン記念 スペシャルな
シングルオリジン 100g+150gセット」「オープン記念 優勝ブレンド
150g×2種セット」(いずれも複数銘柄の詰め合わせ)・「コーヒー豆福袋-
まん"福" 100g×4種」「コーヒー豆福袋-浅煎り 100g×2種」「コーヒー豆福袋-
深煎り 100g×2種」(福袋、複数銘柄の福袋詰め合わせ)が非対象。
NON_BEAN_KEYWORDSで除外する。残り43件を対象とする。

【焙煎度について】
実データ確認済み: 一部商品(Brazil Inacio Urban Mordan Anaerobic Natural
深煎り、Myanmar U ag win 中煎り等)は商品名末尾に浅煎り/中煎り/深煎り等の
粗い表記が付く。coffee_parser.ROAST_KEYWORDS(プロ向け8段階のカタカナ
表記)とは粒度が異なるため、roast_hintとして保持しroast_levelには反映
しない。

【在庫状態について】
実データ確認済み: 品切れ商品には`<span class="detail-sold-out">SOLD
OUT</span>`が埋め込まれる(在庫あり商品には出現しない)ため、これを
structural_out_of_stockとしてdetect_stock_status()に渡す。

【品切れ商品の重量について】
実データ確認済み(2026-09再確認、全43件): 品切れ商品のページには容量を
選ぶ`<select>`自体が描画されず(在庫あり商品のみ<option>群が存在)、
extract_min_option_weight_g()がNoneを返す。在庫あり全商品(コーヒー豆
カテゴリ全体)の最小重量が例外なく150gだったため、品切れでNoneになった
場合はSOLD_OUT_FALLBACK_WEIGHT_G(150)にフォールバックする。
"""

import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "FUKUSUKE COFFEE ROASTERY",
    "url": "https://www.fukusukecoffee.jp/",
    "platform": "MakeShop",
    "address": "愛知県安城市小川町的場101-7",
    "prefecture": "愛知県",
    "robots_txt_status": "実質許可(2026-09確認。robots.txt自体が存在しない(404)ため制限なし)",
}

BASE_URL = "https://www.fukusukecoffee.jp"
CATEGORY_PATH = "coffeebeans"
CRAWL_DELAY_SECONDS = 1.0
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["福袋", "セット"]
ITEM_ID_PATTERN = re.compile(r"/view/item/(\d+)")
PRICE_PATTERN = re.compile(r'data-id="makeshop-item-price:\d+">\s*([\d,]+)\s*<')
OPTION_TEXT_PATTERN = re.compile(r"<option[^>]*>([^<]*)</option>")
WEIGHT_G_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
WEIGHT_KG_PATTERN = re.compile(r"(\d+)\s*[kKｋＫ][gｇ]")
ROAST_HINT_TERMS = ["中深煎り", "中浅煎り", "極深煎り", "浅煎り", "中煎り", "深煎り"]
# 理由はモジュールdocstring参照(品切れ商品は<option>群が描画されず
# extract_min_option_weight_gがNoneを返すため、在庫あり全43件で共通して
# 確認された基準重量150gにフォールバックする)
SOLD_OUT_FALLBACK_WEIGHT_G = 150


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.text


def fetch_category_item_ids() -> list[str]:
    html = fetch_html(f"{BASE_URL}/view/category/{CATEGORY_PATH}")
    return sorted(set(ITEM_ID_PATTERN.findall(html)))


def extract_min_option_weight_g(html: str) -> int | None:
    """理由はモジュールdocstring参照(<select>の並び順が商品ごとに異なる
    ため、ページ全体から重量表記を検出し最小値を採用する)。品切れ商品は
    <option>群自体が描画されないため、この場合はNoneを返しbuild_record側の
    フォールバック(SOLD_OUT_FALLBACK_WEIGHT_G)に処理を委ねる。"""
    weights = []
    for m in OPTION_TEXT_PATTERN.finditer(html):
        text = m.group(1)
        km = WEIGHT_KG_PATTERN.search(text)
        if km:
            weights.append(int(km.group(1)) * 1000)
            continue
        gm = WEIGHT_G_PATTERN.search(text)
        if gm:
            weights.append(int(gm.group(1)))
    return min(weights) if weights else None


def extract_roast_hint(title: str) -> str | None:
    for term in ROAST_HINT_TERMS:
        if term in title:
            return term
    return None


def build_record(item_id: str, html: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    name_el = soup.select_one("h2.product-name")
    name = name_el.get_text(strip=True) if name_el else ""
    if not name or any(kw in name for kw in NON_BEAN_KEYWORDS):
        return None

    product_url = f"{BASE_URL}/view/item/{item_id}"
    parsed = parse_product(name)

    if parsed["is_flavored"]:
        price_m = PRICE_PATTERN.search(html)
        price = int(price_m.group(1).replace(",", "")) if price_m else None
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": product_url,
        }

    price_m = PRICE_PATTERN.search(html)
    price = int(price_m.group(1).replace(",", "")) if price_m else None
    weight_g = extract_min_option_weight_g(html)
    structural_out_of_stock = "detail-sold-out" in html
    if weight_g is None and structural_out_of_stock:
        # 理由はモジュールdocstring参照(品切れ商品は<option>群が描画されない)
        weight_g = SOLD_OUT_FALLBACK_WEIGHT_G
    stock_status = detect_stock_status(name, structural_out_of_stock)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": None,  # 理由はモジュールdocstring参照(粗い焙煎度表記のためroast_hintに保持)
        "roast_hint": extract_roast_hint(name),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    item_ids = fetch_category_item_ids()

    records = []
    flavored_records = []
    for item_id in item_ids:
        product_url = f"{BASE_URL}/view/item/{item_id}"
        try:
            html = fetch_html(product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue

        detail = build_record(item_id, html)
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
    with open("data_fukusukecoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_fukusukecoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
