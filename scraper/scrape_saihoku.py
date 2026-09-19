# -*- coding: utf-8 -*-
"""
scrape_saihoku.py

さいほく珈琲(saihoku.ocnk.net、〒097-0027 北海道稚内市富士見5-1835、
自家焙煎豆のオンライン販売)の商品情報を取得する。おちゃのこネット(Ocnk)。

robots.txt確認済み(2026-09時点): GPTBot/Bytespider/TikTokSpider/
meta-externalagentのみ個別にDisallow: /、それ以外は制限なし。

住所は/infoページ(特定商取引法に基づく表記)にて実データ確認済み:
「北海道稚内市富士見５-１８３５」(全角数字表記)。

【商品一覧の取得方法について】
実データ確認済み(2026-09時点): sitemap.xmlに335件のproduct URLが列挙されて
いるが、これは焙煎豆・生豆・ドリップバッグ・コーヒー器具・セット商品・
水出しアイスパック・野菜(行者ニンニク等)を全て含む。トップページの
カテゴリ構成(焙煎豆/生豆/ドリップバッグ/コーヒー器具/セット商品等)確認済み。

【対象商品の絞り込みについて】
実データ確認済み: 焙煎豆商品は例外なくタイトルが「〈焙煎豆XXXg〉」で
始まる(例:「〈焙煎豆100g〉ブラジル・サントアントニオ・プレミアム
ショコラ」)。生豆は「〈生豆XXXg〉」、ドリップバッグ・器具・セット商品・
野菜等はこれと異なるタイトル形式のため、「〈焙煎豆」で始まる商品のみを
対象とする単純な絞り込みが最も確実(除外キーワード列挙より誤りが少ない)。
「XXXg×N個セット」形式の複数個セットは単品と重量表記が重複し正しい
単価判定ができないため、NON_BEAN_KEYWORDSで別途除外する。

【重量違いの重複について】
実データ確認済み: 同一銘柄が100g〜1000g等の複数重量で個別商品登録されて
いる。商品名から重量表記を取り除いた基準名でグルーピングし、最小重量を
代表として採用する(あさみ珈琲豆店と同じ考え方)。

【Unicode正規化について】
実データ確認済み(product/1とproduct/3): 同一銘柄「...プレミアムショコラ」
でも、「プ」の表記がNFC(合成済みプ)とNFD(基底文字フ+結合半濁点
゚)で商品ごとに揺れており、正規化しないと文字列比較で別銘柄と誤認識
され重複排除に失敗することを確認した(登録時期・入力環境の違いによるもの
と推測)。NFKC正規化してから基準名を計算することで解消する。

【価格・重量の取得方法について】
実データ確認済み: 商品名の先頭〈焙煎豆XXXg〉に重量が明記され、価格は
OGPメタタグ(product:price:amount、税込)から取得できる。

【flavor_notes・farm_note構成要素について(2026-09-19追記)】
実データ確認済み(product/1): div.item_desc_text.custom_desc要素に
「ブラジルらしいナッツフレーバーと甘味、チョコレートのようなフレーバーが
魅力です。」という風味描写(冒頭の自由記述)に続けて「生産国 ：/生産地 ：/
品　種 ：/精選方法：/規　格 ：」というラベル：値の行が並ぶ(ラベルと
コロンの間に全角スペースでの桁揃えが入る)。その後の「【味わい】」見出しは
焙煎度ごとの風味描写(浅煎り/中煎り/中深煎り/深煎り別)のため、単一の
flavor_notesとしては採用せず、ラベル行が始まる前の冒頭自由記述のみを
flavor_notesとして採用する。以前は商品一覧取得時にタイトル・価格のみ
取得しており、この要素自体を一切読んでいなかった(canonical商品選定後に
改めて詳細ページを取得する)。
"""

import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status, normalize_processing_method
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "さいほく珈琲",
    "url": "https://saihoku.ocnk.net/",
    "platform": "おちゃのこネット(Ocnk)",
    "address": "北海道稚内市富士見5-1835",
    "prefecture": "北海道",
    "robots_txt_status": "実質許可(2026-09確認。GPTBot等AI系ボットのみ個別にDisallow: /、"
                          "それ以外は制限なし)",
}

BASE_URL = "https://saihoku.ocnk.net"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 理由はモジュールdocstring参照。「〈焙煎豆」始まりのみ対象とし、その中でも
# 複数個セット表記は単価が不明瞭になるため除外する。
ROASTED_BEAN_PREFIX_PATTERN = re.compile(r"^〈焙煎豆(\d+)g")
NON_BEAN_KEYWORDS = ["個セット"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
WEIGHT_TOKEN_PATTERN = re.compile(r"^〈焙煎豆\d+g〉")

# 理由はモジュールdocstring参照
DESC_LABEL_PATTERN = re.compile(r"^([^:：\n]{1,10})[：:]\s*(.+)$")
DESC_LABEL_TO_FIELD = {
    "生産地": "region_detail",
    "品種": "variety_note",
    "精選方法": "processing_method",
    "規格": "grade",
}


def parse_description_details(product_url: str) -> tuple[dict, str | None]:
    """理由はモジュールdocstring参照(ラベル行が始まる前の自由記述を
    flavor_notesとして採用し、【味わい】以降の焙煎度別描写は対象としない)。"""
    soup = fetch_page(product_url)
    el = soup.select_one("div.item_desc_text.custom_desc")
    if not el:
        return {}, None
    fields: dict[str, str] = {}
    intro_lines: list[str] = []
    seen_label = False
    for raw_line in el.get_text(separator="\n").split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        m = DESC_LABEL_PATTERN.match(line)
        if m:
            label = "".join(m.group(1).split())
            field = DESC_LABEL_TO_FIELD.get(label)
            if field:
                fields.setdefault(field, m.group(2).strip())
            seen_label = True
            continue
        if not seen_label:
            intro_lines.append(line)
    flavor_notes = "".join(intro_lines) if intro_lines else None
    return fields, flavor_notes


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def fetch_product_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    urls = []
    for loc in soup.find_all("loc"):
        text = loc.get_text(strip=True)
        if re.search(r"/product/\d+$", text):
            urls.append(text)
    return urls


def extract_fields(soup: BeautifulSoup) -> dict | None:
    title_el = soup.select_one("title")
    if not title_el:
        return None
    raw_title = title_el.get_text(strip=True).split(" - ")[0].strip()
    title = unicodedata.normalize("NFKC", raw_title)
    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None
    return {"title": title, "price": price}


def pick_canonical_items(items: list[dict]) -> list[dict]:
    by_base_name: dict[str, dict] = {}
    for item in items:
        base_name = WEIGHT_TOKEN_PATTERN.sub("", item["title"]).strip()
        weight_m = ROASTED_BEAN_PREFIX_PATTERN.search(item["title"])
        weight_key = int(weight_m.group(1)) if weight_m else float("inf")
        existing = by_base_name.get(base_name)
        existing_weight_m = ROASTED_BEAN_PREFIX_PATTERN.search(existing["title"]) if existing else None
        existing_weight = int(existing_weight_m.group(1)) if existing_weight_m else float("inf")
        if existing is None or weight_key < existing_weight:
            by_base_name[base_name] = item
    return list(by_base_name.values())


def build_record(item: dict) -> dict | None:
    title = item["title"]
    # 「〈焙煎豆100g〉」部分を取り除いた銘柄名で産地等を解析する
    bean_name = WEIGHT_TOKEN_PATTERN.sub("", title).strip()
    parsed = parse_product(bean_name)

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
    weight_m = ROASTED_BEAN_PREFIX_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None

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
        "grade": desc_fields.get("grade") or parsed["grade"],
        "roast_level": parsed["roast_level"],
        "post_processing_tags": parsed["post_processing_tags"],
        "region_detail": desc_fields.get("region_detail"),
        "variety_note": desc_fields.get("variety_note"),
        "blend_components": [],
        "flavor_notes": flavor_notes,
        "price": item["price"],
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_product_urls()

    all_items = []
    for product_url in product_urls:
        try:
            fields = extract_fields(fetch_page(product_url))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if not fields:
            continue
        if not ROASTED_BEAN_PREFIX_PATTERN.search(fields["title"]):
            continue
        if any(kw in fields["title"] for kw in NON_BEAN_KEYWORDS):
            continue
        all_items.append({"title": fields["title"], "price": fields["price"], "url": product_url})

    canonical_items = pick_canonical_items(all_items)
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for item in canonical_items:
        prev = previous.get(item["url"])
        if is_unchanged(prev, raw_name=item["title"], price=item.get("price")):
            records.append(prev)
            continue

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
    with open("data_saihoku.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_saihoku.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
