# -*- coding: utf-8 -*-
"""
scrape_gitanes.py

カフェ・デ・ジターヌ(store.cafe-gitanes.com、青森県青森市篠田3-3-9、
自家焙煎豆のオンライン販売)の商品情報を取得する。カラーミーショップ
(shop-pro.jp、独自ドメイン)。

【住所について】
候補リストの住所は「青森県青森市古沢3-3-9」だったが、特定商取引法相当
ページ(https://store.cafe-gitanes.com/?mode=sk)を実データ確認したところ
「住所」欄に「青森市篠田3-3-9」との記載を確認した(2026-09時点)。
丁目・番地(3-3-9)は候補リストと一致するが町名が異なる(古沢→篠田)。
本プロジェクトの一次情報優先の方針に基づき、公式ストア自身のtokushoho
記載である「青森市篠田3-3-9」を採用する(候補リストの町名は誤りと判断)。

robots.txt未確認のため、他のカラーミー店舗と同様に実質許可とみなす。

【文字コード】EUC-JP(実データ確認済み)。他のカラーミー店舗と同じく
resp.encodingを明示する。

【対象カテゴリについて】
実データ確認済み: 「コーヒー豆」大カテゴリ(cbid=375652)自体には直接商品が
無く、8個のサブカテゴリ(csid)に分かれている。うち「オリジナルブレンド
コーヒー」(csid=1)・「中煎りのストレート」(csid=4)・「中深煎りのストレート
コーヒー」(csid=6)・「深煎りのストレートコーヒー」(csid=8)・
「カフェインレス」(csid=9)・「季節のコーヒー」(csid=16)の6サブカテゴリが
対象。「カップオンコーヒー」(csid=11、ドリップバッグ形式)・「水出し
コーヒー」(csid=13、水出し専用パック)は非対象のため巡回しない。

【重量について】
実データ確認済み: 大半の商品はvariants配列のtitle(例:「豆　×　100g
パック」)に重量が入っている。一部の季節限定商品(SUMMER TIME COFFEE 2026)
はvariantsに重量表記が無く、代わりに商品名自体に「＜ネコポス対応１５０g
パック＞」のように重量入り注記が付いた別pidとして登録されている(同一
銘柄の容量違いバリエーション)。このため(1)variantsから重量を取得、
(2)見つからなければ商品名(NFKC正規化後)から重量を取得、を順に試み、
その後全商品を対象に商品名から重量注記を除いた基準名でグルーピングして
最小重量を代表として採用する(重量不明の商品は無限大として扱われ、
重量が判明した方が優先される)。

【非コーヒー豆商品の除外について】
実データ確認済み: 「カフェラテベース」(濃縮リキッド)・「水出しコーヒー
カップパック」「水出しコーヒーパック」(水出し専用パック)が非対象。
NON_BEAN_KEYWORDSで除外する。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "カフェ・デ・ジターヌ",
    "url": "https://store.cafe-gitanes.com/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "青森県青森市篠田3-3-9",
    "prefecture": "青森県",
    "robots_txt_status": "実質許可とみなす(2026-09確認。他のカラーミー店舗と同一の"
                          "標準的な記述と推定)",
}

BASE_URL = "https://store.cafe-gitanes.com"
# 理由はモジュールdocstring参照(コーヒー豆大カテゴリ配下のうち、コーヒー豆
# 単品を扱う6サブカテゴリのみが対象)
BEAN_SUBCATEGORY_IDS = ["1", "4", "6", "8", "9", "16"]
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["カフェラテベース", "水出し"]
COLORME_PATTERN = re.compile(r"var Colorme\s*=\s*(\{.*?\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
# 理由: SUMMER TIME COFFEE 2026のように、同一銘柄の容量違いが
# 「＜ネコポス対応１５０gパック＞」のような注記付きで商品名に埋め込まれる
# ケースがあるため、重量を含む山括弧・丸括弧の注記ごと除去してから基準名を
# 比較する(単に重量の数字だけを除去すると注記の残りの文字列が基準名に
# 残ってしまい、同一銘柄なのに別グループとして扱われてしまう)。
WEIGHT_BRACKET_PATTERN = re.compile(r"[<＜(（][^<＜(（>＞)）]*\d+\s*[gｇ][^<＜(（>＞)）]*[>＞)）]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-jp"  # 実データ確認済み(Content-Type: text/html; charset=EUC-JP)
    return BeautifulSoup(resp.text, "html.parser")


def scrape_bean_category_pids() -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for csid in BEAN_SUBCATEGORY_IDS:
        soup = fetch_page(f"{BASE_URL}/?mode=cate&cbid=375652&csid={csid}")
        for link in soup.select('a[href*="pid="]'):
            href = link.get("href", "")
            m = re.search(r"pid=(\d+)", href)
            if not m:
                continue
            product_url = f"{BASE_URL}/?pid={m.group(1)}"
            if product_url not in seen:
                seen.add(product_url)
                urls.append(product_url)
    return urls


def extract_colorme_product(soup: BeautifulSoup) -> dict | None:
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        m = COLORME_PATTERN.search(text)
        if not m:
            continue
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return None
        return data.get("product")
    return None


def detect_weight(product: dict, title: str, price: int | None) -> int | None:
    variants = product.get("variants") or []
    candidates = [v for v in variants if v.get("option_price_including_tax") == price]
    pool = candidates or variants
    if pool:
        variant = min(pool, key=lambda v: v.get("option_price_including_tax") or float("inf"))
        m = WEIGHT_PATTERN.search(unicodedata.normalize("NFKC", variant.get("title") or ""))
        if m:
            return int(m.group(1))
    m = WEIGHT_PATTERN.search(unicodedata.normalize("NFKC", title))
    return int(m.group(1)) if m else None


def build_item(product_url: str, product: dict) -> dict | None:
    title = (product.get("name") or "").strip()
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    price = product.get("sales_price_including_tax")
    weight_g = detect_weight(product, title, price)
    structural_out_of_stock = product.get("stock_num") == 0

    return {
        "title": title,
        "price": price,
        "weight_g": weight_g,
        "url": product_url,
        "structural_out_of_stock": structural_out_of_stock,
    }


def pick_canonical_items(items: list[dict]) -> list[dict]:
    by_base_name: dict[str, dict] = {}
    for item in items:
        normalized_title = unicodedata.normalize("NFKC", item["title"])
        base_name = WEIGHT_BRACKET_PATTERN.sub("", normalized_title)
        base_name = WEIGHT_PATTERN.sub("", base_name)
        base_name = re.sub(r"[<＜>＞（）()]", "", base_name)
        base_name = re.sub(r"\s+", " ", base_name).strip()
        weight_key = item["weight_g"] if item["weight_g"] is not None else float("inf")
        existing = by_base_name.get(base_name)
        existing_weight_key = existing["weight_g"] if existing and existing["weight_g"] is not None else float("inf")
        if existing is None or weight_key < existing_weight_key:
            by_base_name[base_name] = item
    return list(by_base_name.values())


def build_record(item: dict) -> dict | None:
    title = item["title"]
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

    stock_status = detect_stock_status(title, item["structural_out_of_stock"])

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
        "price": item["price"],
        "weight_g": item["weight_g"],
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = scrape_bean_category_pids()

    all_items = []
    for product_url in product_urls:
        try:
            soup = fetch_page(product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        product = extract_colorme_product(soup)
        if not product:
            continue
        item = build_item(product_url, product)
        if item is not None:
            all_items.append(item)

    canonical_items = pick_canonical_items(all_items)

    records = []
    flavored_records = []
    for item in canonical_items:
        detail = build_record(item)
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


if __name__ == "__main__":
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_gitanes.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_gitanes.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
