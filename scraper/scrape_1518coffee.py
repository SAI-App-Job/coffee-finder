# -*- coding: utf-8 -*-
"""
scrape_1518coffee.py

1518珈琲(www.coffee1518.com、〒700-0822 岡山県岡山市北区中山下1丁目5番33号、
自家焙煎豆のオンライン販売。運営会社「珈琲館1518岡山」)の商品情報を取得する。
MakeShop。

【住所について】
候補リストでは「岡山市北区」までの市レベルの情報のみだったが、公式ストアの
特定商取引法ページ(https://www.coffee1518.com/html/ordercontract.html)で
実データ確認したところ「岡山県岡山市北区中山下1丁目5番33号」(事業者名:
珈琲館1518岡山)であることを確認した(2026-09時点)。一部の第三者店舗情報
サイトには「岡山市北区奉還町2-5-26」という別の住所(実店舗/カフェ機能を
指すと思われる)が掲載されているが、本プロジェクトの方針に従い公式サイトの
特定商取引法ページの記載を正式な通販事業者の所在地として採用する。

【自家焙煎の実態について】
実データ確認済み: トップページ・各商品ページに「自家焙煎」の表記が
繰り返し使われているのに加え、実際の商品カテゴリにブラジル・ホンジュラス・
ニカラグア等のストレート銘柄が農園名付きで多数登録されており、価格帯も
250gあたり2,000円台の一般的なブレンドから、希少単一農園ロット(イエメン・
東ティモール等、実データ確認済みで250gあたり6,000円台)まで一貫した価格
構造を持つことを確認した。単なる転売品の詰め合わせではなく実店舗で自家
焙煎を行う専門店と判断した。

robots.txt確認済み(2026-09時点): https://www.coffee1518.com/robots.txtは
カスタム404ページが返る(実質存在しない)。クロール制限の記述が無いため
実質無制限と判断した。

【商品一覧の取得方法について】
実データ確認済み: 「自家焙煎豆２５０ｇ」(shopbrand/002/X/、全24件、3ページ)
と「自家焙煎豆１５０ｇ」(shopbrand/003/X/、全24件、3ページ)がこの店の
主要な2つの重量別カテゴリで、ブレンド・ストレート・希少単一農園ロットが
横断的に含まれる。「カフェインレスコーヒー」(shopbrand/ct106/、全5件、
1ページ)は上記2カテゴリと一部重複するデカフェ豆を含む別カテゴリのため
追加で対象にする。「珈琲器具類」「ダンク式コーヒーバッグ」「1518珈琲各種
お試しセット」(複数銘柄詰め合わせ)は非対象。カフェインレスコーヒー
カテゴリ内にも「カフェインレスダンク式珈琲バッグ」(通常の焙煎豆ではなく
1杯用ダンク式ドリップバッグの形態)が2件混在しているため、
NON_BEAN_KEYWORDSで除外する。

【価格の取得方法について】
実データ確認済み: 商品詳細ページの価格表示は
`価格 : <input value="6,696" class="m_price">円（税抜<input
value="6,200" class="m_price">円)`のように、税込価格(price2)が先に
表示され、括弧内に税抜参考価格(price1)が続く。税込価格であるprice2の
inputのvalue属性を採用する。

【重量表記の全角数字について】
実データ確認済み: 商品名は「イエメン＜ハラーズ：バニ　ナヒム＞２５０ｇ」
のように重量を含め全角数字で表記されている。unicodedata.normalize
("NFKC", ...)で正規化してから重量抽出・基準名グルーピングを行う。

【重量違いの重複について】
実データ確認済み: 「自家焙煎豆２５０ｇ」「自家焙煎豆１５０ｇ」の2カテゴリ
に同一銘柄が別商品ページとして重複登録されている。商品名末尾の重量表記を
除いた基準名でグルーピングし、最小重量(150g)を代表として採用する。

【既知の残存重複について】
実データ確認済み: 「イエメン」(150g版は"バニ・ナヒム"、250g版は
"バニ:ナヒム"と区切り文字が異なる)と「東ティモール」(150g版の商品ページ
titleタグに全角ラテン文字"ｙ"を含む誤記"レブドｙ"があり、250g版の正しい
"レブドウ"と一致しない)の2銘柄は、店側の入力ゆれにより基準名が完全一致
せず、150g/250gの両方が別商品として出力される(軽微な既知の残存重複)。

【flavor_notes・farm_note構成要素について(2026-09-19追記)】
実データ確認済み(2商品): 単一農園商品はdiv.detailTxt要素に「品種・
イエメニア」(この1ラベルのみ「・」区切り、他は「：」区切り)「生産者：/
所在：/標高：/精製：」というラベル：値の行に続けて、品種の由来解説等の
長い自由記述があり、末尾(空行区切りの最後の段落)に「シナモンを思わせる
香り、フルーティな味が特徴」という具体的な風味描写がある。一方ブレンド
商品はラベルが無く、「まろやかなコクと甘味があります。」のような単一
段落の風味描写のみ(空行区切りの最後の段落もこれと同じ)。このため
「空行区切りの最後の段落」を採用することで両パターンに対応できる。
"""

import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status, normalize_processing_method

SHOP_INFO = {
    "name": "1518珈琲",
    "url": "https://www.coffee1518.com/",
    "platform": "MakeShop",
    "address": "岡山県岡山市北区中山下1丁目5番33号",
    "prefecture": "岡山県",
    "robots_txt_status": "実質許可(2026-09確認。robots.txtはカスタム404ページが返り、"
                          "実質的な制限記述が無い)",
}

BASE_URL = "https://www.coffee1518.com"
CATEGORY_PATHS = [
    "shopbrand/002/X/", "shopbrand/002/X/page2/order/", "shopbrand/002/X/page3/order/",
    "shopbrand/003/X/", "shopbrand/003/X/page2/order/", "shopbrand/003/X/page3/order/",
    "shopbrand/ct106/",
]
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["ダンク式", "コーヒーバッグ"]
DETAIL_ID_PATTERN = re.compile(r"/shopdetail/([0-9]{12})/")
TITLE_SUFFIX_PATTERN = re.compile(r"\s*\|.*$")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
TRAILING_WEIGHT_PATTERN = re.compile(r"[\s　]*\d+\s*[gｇ]\s*$")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return BeautifulSoup(resp.text, "html.parser")


def fetch_product_ids() -> set[str]:
    ids: set[str] = set()
    for path in CATEGORY_PATHS:
        try:
            soup = fetch_page(f"{BASE_URL}/{path}")
        except requests.RequestException as e:
            print(f"[warn] カテゴリ取得失敗: {path} ({e})")
            continue
        for a in soup.select('a[href*="/shopdetail/"]'):
            m = DETAIL_ID_PATTERN.search(a.get("href", ""))
            if m:
                ids.add(m.group(1))
    return ids


def extract_fields(soup: BeautifulSoup) -> dict | None:
    title_el = soup.select_one("title")
    if not title_el:
        return None
    title = unicodedata.normalize("NFKC", title_el.get_text())
    title = TITLE_SUFFIX_PATTERN.sub("", title).strip()
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    price = None
    price_input = soup.select_one('input#M_price2.m_price, input[name="price2"].m_price')
    if price_input and price_input.get("value"):
        try:
            price = int(price_input["value"].replace(",", ""))
        except ValueError:
            price = None

    return {"title": title, "price": price}


DESC_LABEL_PATTERN = re.compile(r"^([^:：・\n]{1,6})[：:・]\s*(.+)$")
DESC_LABEL_TO_FIELD = {
    "品種": "variety_note",
    "生産者": "producer_name",
    "所在": "region_detail",
    "標高": "altitude_note",
    "精製": "processing_method",
}


def parse_description_details(product_url: str) -> tuple[dict, str | None]:
    """理由はモジュールdocstring参照(div.detailTxt。ラベル行は位置を問わず
    抽出し、flavor_notesは空行区切りの最後の段落を採用する。単一農園商品は
    ラベル→品種の歴史解説→末尾の風味描写という構成、ブレンド商品は単一の
    風味描写段落のみという構成で、いずれも最後の段落を取ることで対応
    できる)。"""
    soup = fetch_page(product_url)
    el = soup.select_one("div.detailTxt")
    if not el:
        return {}, None
    text = el.get_text(separator="\n")

    fields: dict[str, str] = {}
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        m = DESC_LABEL_PATTERN.match(line)
        if not m:
            continue
        label = "".join(m.group(1).split())
        field = DESC_LABEL_TO_FIELD.get(label)
        if field:
            fields.setdefault(field, m.group(2).strip())

    paragraphs: list[list[str]] = []
    current: list[str] = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            if current:
                paragraphs.append(current)
                current = []
            continue
        current.append(line)
    if current:
        paragraphs.append(current)
    flavor_notes = "".join(paragraphs[-1]) if paragraphs else None
    return fields, flavor_notes


def pick_canonical_items(items: list[dict]) -> list[dict]:
    by_base_name: dict[str, dict] = {}
    for item in items:
        weight_m = WEIGHT_PATTERN.search(item["title"])
        weight_g = int(weight_m.group(1)) if weight_m else None
        base = TRAILING_WEIGHT_PATTERN.sub("", item["title"]).strip()
        item = {**item, "base_name": base, "weight_g": weight_g}
        weight_key = weight_g if weight_g is not None else float("inf")
        existing = by_base_name.get(base)
        existing_weight = existing["weight_g"] if existing and existing["weight_g"] is not None else float("inf")
        if existing is None or weight_key < existing_weight:
            by_base_name[base] = item
    return list(by_base_name.values())


def build_record(item: dict) -> dict | None:
    title = item["base_name"]
    if not title:
        return None
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

    stock_status = detect_stock_status(title)
    desc_fields, flavor_notes = parse_description_details(item["url"])
    processing_method = desc_fields.get("processing_method")
    processing_method = normalize_processing_method(processing_method) if processing_method else parsed["processing_method"]

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing_method,
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "post_processing_tags": parsed["post_processing_tags"],
        "producer_name": desc_fields.get("producer_name"),
        "region_detail": desc_fields.get("region_detail"),
        "altitude_note": desc_fields.get("altitude_note"),
        "variety_note": desc_fields.get("variety_note"),
        "blend_components": [],
        "flavor_notes": flavor_notes,
        "price": item["price"],
        "weight_g": item["weight_g"],
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_ids = fetch_product_ids()

    items = []
    for product_id in sorted(product_ids):
        product_url = f"{BASE_URL}/shopdetail/{product_id}/"
        try:
            soup = fetch_page(product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        fields = extract_fields(soup)
        if not fields:
            continue
        items.append({**fields, "url": product_url})

    canonical_items = pick_canonical_items(items)

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
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_1518coffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_1518coffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
