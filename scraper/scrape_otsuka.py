# -*- coding: utf-8 -*-
"""
scrape_otsuka.py

珈琲豆のおおつか(otsuka-coffee.raku-uru.jp、千葉県船橋市)の商品情報を
取得する。らくうるカート(ヤマトホールディングス系のEC-ASPプラット
フォーム。「楽天」とは無関係)。このプロジェクト初対応のプラットフォーム。

robots.txt確認済み(2026-09時点): /robots.txtへのアクセスがトップページ
(SPA的なフォールバック)を返すのみで、robots.txt自体が存在しない。
実質全面許可(Mui・CAFE FACON等のShopServeで確立した「robots.txtが
無い=全面許可」判断基準と同じ)。

【カテゴリ構造について】
実データ確認済み: 親カテゴリ「自家焙煎珈琲豆」(categoryId=30205)自体は
「【猛暑対策】送料は珈琲豆のおおつかが負担する珈琲豆」という送料
キャンペーン告知の1件のみを保持し、実際の商品は「ブレンド」(36362)・
「中米」(36317)・「南米」(36318)・「アフリカ」(36319)・「アジア・
太平洋」(36316)・「カフェインレス【デカフェ】」(105383)の6サブ
カテゴリにのみ存在する(親カテゴリには重複掲載されない、Daphneの
「新入荷」とは逆のパターン)。そのため6サブカテゴリの和集合を対象と
する(実データ確認済み: 計48件、URL単位で自然に重複なし)。
「ドリップバッグ」「クイックコーヒーバッグ」「アイスコーヒー【水出し・
リキッド】」「おためし4セット」「ギフトセット」「夏ギフト」「フィルター・
器具関連」「カスカラ関連商品」「お菓子ほか」「ギフトBOX・ラッピング」は
対象外カテゴリのため触れていない。

【半角カタカナの正規化について】
実データ確認済み: 商品名の産地表記が半角カタカナ(例:「ｸﾞｱﾃﾏﾗ」「ﾌﾞﾗｼﾞﾙ」)
で入力されている商品が多数ある。coffee_parser.pyのORIGIN_COUNTRY
マスタは全角カタカナ表記(「グアテマラ」等)のため、正規化しないと
産地判定が一切ヒットしない。unicodedata.normalize("NFKC", ...)で
全角に正規化してからparse_product()に渡す(表示用raw_nameも同様に
正規化する。半角カタカナは店舗側の入力上の癖であり、意図的な表記では
ないと判断した)。

【重量・価格について】
実データ確認済み: 商品によって2種類の構造がある。(1)
`select[name="variationId"]`が複数の重量×挽き方オプション(例:「100g
(生豆時)　豆」)を持つ通常商品と、(2)重量は固定で`select[name=
"attrValues"]`が挽き方のみを持つ大容量パック商品(「VPn」型番、
例:「1kgパック(生豆時)」とタイトルに明記)。(1)の場合はデフォルトで
選択されている`<option selected>`のテキストから重量を取得し(価格も
このデフォルト選択に対応する表示価格を使うため、重量と価格の対応が
確実に一致する)、(2)の場合はタイトル中の重量表記(「1kgパック」等)から
補完する。重量はいずれも「生豆時」(焙煎前の生豆重量)であり、焙煎後の
正確な重量は開示されていない(たまじ珈琲・神楽坂珈琲焙煎所と同様の
状況)。価格は`b.raku-item-vari-price-num`(常にデフォルト選択に対応する
1つのみが静的HTMLに含まれる、他の挽き方/重量の価格はJS/Ajaxでの
再計算のため取得できない)。
"""

import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "珈琲豆のおおつか",
    "url": "https://otsuka-coffee.raku-uru.jp/",
    "platform": "らくうるカート",
    "address": "千葉県船橋市",
    "prefecture": "千葉県",
    "robots_txt_status": "実質許可(2026-09確認。robots.txt自体が存在せず、"
                          "/robots.txtアクセス時はトップページが返る)",
}

BASE_URL = "https://otsuka-coffee.raku-uru.jp"
# 理由はモジュールdocstring参照
LIST_CATEGORIES = ["36362", "36317", "36318", "36319", "36316", "105383"]
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

LIST_ITEM_PATTERN = re.compile(
    r'href="(/item-detail/\d+)"[\s\S]{0,400}?class="item-name"><a[^>]*>([^<]*)</a>'
)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*kg", re.IGNORECASE)
WEIGHT_G_PATTERN = re.compile(r"(\d+)\s*[gｇ](?!\w)")
PRICE_PATTERN = re.compile(r"([\d,]+)\s*円")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "")


def scrape_category_list(cid: str) -> list[dict]:
    resp = requests.get(f"{BASE_URL}/item-list", params={"categoryId": cid},
                         headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    results = []
    for href, title in LIST_ITEM_PATTERN.findall(resp.text):
        results.append({
            "raw_name": normalize(title.strip()),
            "product_url": f"{BASE_URL}{href}",
        })
    return results


def extract_weight_g(text: str) -> int | None:
    kg_match = WEIGHT_PATTERN.search(text)
    if kg_match:
        return int(kg_match.group(1)) * 1000
    g_match = WEIGHT_G_PATTERN.search(text)
    return int(g_match.group(1)) if g_match else None


def parse_price_weight(soup: BeautifulSoup, title: str) -> tuple[int | None, int | None]:
    price_el = soup.select_one("b.raku-item-vari-price-num")
    price = None
    if price_el:
        m = PRICE_PATTERN.search(price_el.get_text())
        if m:
            price = int(m.group(1).replace(",", ""))

    weight_g = None
    variation_select = soup.select_one('select[name="variationId"]')
    if variation_select:
        selected_option = variation_select.select_one("option[selected]") or variation_select.select_one("option")
        if selected_option:
            weight_g = extract_weight_g(normalize(selected_option.get_text()))

    if weight_g is None:
        weight_g = extract_weight_g(normalize(title))

    return price, weight_g


def build_record(url: str, soup: BeautifulSoup, raw_title: str) -> dict:
    title = normalize(raw_title)
    parsed = parse_product(title)
    price, weight_g = parse_price_weight(soup, title)

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
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": url,
    }


def parse_product_detail(url: str) -> dict:
    soup = fetch_page(url)
    title_el = soup.select_one("title")
    raw_title = title_el.get_text(strip=True).split(" | ")[0] if title_el else ""
    return build_record(url, soup, raw_title)


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    items_by_url: dict[str, dict] = {}
    for cid in LIST_CATEGORIES:
        for item in scrape_category_list(cid):
            items_by_url.setdefault(item["product_url"], item)

    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for product_url, item in items_by_url.items():
        prev = previous.get(product_url)
        if is_unchanged(prev, raw_name=item["raw_name"]):
            records.append(prev)
            continue

        try:
            soup = fetch_page(product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue

        detail = build_record(product_url, soup, item["raw_name"])
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
        with open("data_otsuka.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_otsuka.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
