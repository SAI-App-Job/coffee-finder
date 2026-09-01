# -*- coding: utf-8 -*-
"""
scrape_kagisippo.py

かぎしっぽ(r.goope.jp/kagisippo-coffee、神奈川県川崎市幸区)の商品情報を取得する。
「Goope」(株式会社サブスクライブ提供のホームページ作成サービス)を使う初めての
店舗。ECカート機能を持たず、/menu配下の「メニュー表」ページに商品名・価格・
説明文をテキストで掲載する形式(BASE/Shopify/カラーミーショップのような
var Colorme・products.json・JSON-LD等の構造化データは一切無い)。

robots.txt確認済み(2026-08時点): https://r.goope.jp/robots.txt はHTTP 302で
goope.jp(サービス自体のマーケティングサイト)へリダイレクトされ、実体としての
robots.txtファイルが存在しない。404を「制限なしとみなす」既存の方針
(scrape_cafecafa.py等)と同じ扱いとし、Disallow指定が無いため全面許可とみなす。

【対象カテゴリについて】
店舗の/menuページには「当店の焙煎豆について」「自家製焙煎豆(※表示価格は
全て税込みです)」「店舗カフェメニュー」という3つのメニューカテゴリがあり、
このうち「自家製焙煎豆」(cid=c1121724)が豆売り商品を掲載するカテゴリ。

【カフェ限定商品の除外について】
ユーザー指示により、「グァテマラ ゲイシャ(カフェのみの販売です)」のように
豆売りではなくカフェでの提供のみの商品は除外する。実データ確認時点(2026-08)
ではこのカテゴリに該当する商品は無かった(全3件とも通常の豆売り商品)ため、
このパターン自体は実データで検証できていないが、将来的にこうした商品が
掲載された場合に備えてタイトル・説明文に「カフェのみ」「カフェ限定」等の
語を含む商品を除外するキーワードチェックを持たせている(CAFE_ONLY_KEYWORDS)。

【商品名の構造(重量・焙煎度選択肢)】
実データ確認済み(全3件共通): 「コロンビア　ライチ　100ｇ(浅煎り　中煎り)」
のように「[産地/銘柄名]　[重量]ｇ([焙煎度の選択肢を全角スペース区切りで
列挙])」という形式。焙煎度は「浅煎り/中煎り/中深煎り/深煎り」という4段階の
粗い自己申告表記で、本アプリのroast_levelが要求するプロ向け8段階表記とは
粒度が異なる(scrape_coulane.py等で確立した方針と同じ)ため、roast_levelには
反映せずroast_hintとして選択肢をそのまま保持する。焙煎度が選べる=注文時に
指定する方式のため、roast_selectable=Trueとする。

【商品説明文の構造(段落単位でのラベル抽出)】
実データ確認済み: 商品説明はdiv.textfield内の複数の<p>タグに分かれており、
各段落が「品種：カスティージョ　精製：ダブルアナエロビックファーメンテーション
　標高：1700ｍ　農園：ビジャローシタ農園　」のように1つの段落に複数ラベルが
まとめて入っている場合と、「標高：1500ｍ」のように1段落1ラベルの場合の両方が
ある。段落を跨いでラベル・値を検出しようとすると、末尾にラベルを持たない
段落(次の商品まで続くテイスティングノート等の自由記述)の内容がその直前の
ラベルの値として誤って取り込まれてしまう不具合が実データ調査で判明したため、
段落ごとに独立してラベルを抽出し、ラベルを1つも含まない段落は自由記述
(flavor_notes)として別途保持する(parse_textfield参照)。ラベルの並び順・
有無は商品によって異なる(登記済みラベル: 品種/精製/標高/農園/生産者/生産地/
カッピング)。

【ページネーションについて】
実データ確認時点(2026-08)では「自家製焙煎豆」カテゴリは3件のみで1ページに
収まっている(div.pagerにページ2以降へのリンク無し)。将来的に商品数が増えた
場合に備え、pager内に次ページへのリンクがあれば辿る処理を持たせている。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, normalize_processing_method

SHOP_INFO = {
    "name": "かぎしっぽ",
    "url": "https://r.goope.jp/kagisippo-coffee/",
    "platform": "Goope",
    "address": "神奈川県川崎市幸区古市場1-31-7",
    "prefecture": "神奈川県",
    "robots_txt_status": "許可(2026-08確認。robots.txt自体が存在せず[HTTP 302でgoope.jp"
                          "のマーケティングサイトへリダイレクト]、Disallow指定が無いため全面許可とみなす)",
}

BASE_URL = "https://r.goope.jp/kagisippo-coffee"
BEANS_CATEGORY_ID = "c1121724"  # 自家製焙煎豆(※表示価格は全て税込みです)
CRAWL_DELAY_SECONDS = 2
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 理由はモジュールdocstring参照(実データでは未検証、将来の掲載に備えた防御的な除外)
CAFE_ONLY_KEYWORDS = ["カフェのみ", "カフェ限定", "カフェメニューのみ"]

TITLE_PATTERN = re.compile(r"^(.+?)\s*(\d+)\s*[gｇ]\s*\((.+?)\)\s*$")
LABELS = ["品種", "精製", "標高", "農園", "生産者", "生産地", "カッピング"]
LABEL_PATTERN = re.compile(rf"({'|'.join(LABELS)})[：:]\s*(.+?)(?=(?:{'|'.join(LABELS)})[：:]|$)")
ALTITUDE_RANGE_PATTERN = re.compile(r"([\d,]+)\s*[-〜~]\s*([\d,]+)\s*m")
ALTITUDE_SINGLE_PATTERN = re.compile(r"([\d,]+)\s*m")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def parse_altitude(altitude_text: str | None) -> tuple[int | None, int | None]:
    if not altitude_text:
        return None, None
    text = unicodedata.normalize("NFKC", altitude_text)
    text = re.sub(r"\s", "", text)
    m = ALTITUDE_RANGE_PATTERN.search(text)
    if m:
        return int(m.group(1).replace(",", "")), int(m.group(2).replace(",", ""))
    m = ALTITUDE_SINGLE_PATTERN.search(text)
    if m:
        value = int(m.group(1).replace(",", ""))
        return value, value
    return None, None


def parse_textfield(textfield) -> tuple[dict, str]:
    """理由はモジュールdocstring参照。段落(<p>)ごとに独立してラベルを抽出し、
    ラベルを含まない段落は自由記述として返す。"""
    fields: dict[str, str] = {}
    free_text_parts: list[str] = []
    for p in textfield.find_all("p"):
        text = p.get_text().strip()
        if not text:
            continue
        matches = list(LABEL_PATTERN.finditer(text))
        if matches:
            for m in matches:
                fields[m.group(1)] = m.group(2).strip()
        else:
            free_text_parts.append(text)
    return fields, " ".join(free_text_parts).strip()


def is_cafe_only(title: str, free_text: str) -> bool:
    combined = title + (free_text or "")
    return any(kw in combined for kw in CAFE_ONLY_KEYWORDS)


def build_record(product_url: str, raw_title: str, price: int | None, fields: dict, free_text: str) -> dict:
    m = TITLE_PATTERN.match(raw_title)
    if not m:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": raw_title,
            "non_bean": True,
            "product_url": product_url,
        }
    name_part, weight_text, roast_paren = m.group(1), m.group(2), m.group(3)
    weight_g = int(weight_text)
    roast_options = unicodedata.normalize("NFKC", roast_paren).split()

    parsed = parse_product(name_part)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": raw_title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": product_url,
        }

    is_blend = parsed["category"] == "ブレンド"

    if fields.get("精製"):
        parsed["processing_method"] = normalize_processing_method(fields["精製"])
    parsed = apply_category_hint_fallback(parsed, None)

    altitude_min, altitude_max = (None, None) if is_blend else parse_altitude(fields.get("標高"))
    farm_note_parts = []
    if not is_blend:
        if fields.get("農園"):
            farm_note_parts.append(f"農園: {fields['農園']}")
        if fields.get("生産者"):
            farm_note_parts.append(f"生産者: {fields['生産者']}")
        if fields.get("生産地"):
            farm_note_parts.append(f"生産地: {fields['生産地']}")
    farm_note = "、".join(farm_note_parts) if farm_note_parts else None

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": raw_title,
        "category": parsed["category"],
        "origin_country": None if is_blend else parsed["origin_country"],
        "origin_source": None if is_blend else parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": None if is_blend else parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": None,  # 理由はモジュールdocstring参照(4段階表記のためroast_hintに保持)
        "roast_hint": "/".join(roast_options) if roast_options else None,
        "roast_selectable": True,  # 焙煎度は注文時に選択する方式(実データ確認済み)
        "post_processing_tags": parsed["post_processing_tags"],
        "variety": None if is_blend else fields.get("品種"),
        "farm_note": farm_note,
        "altitude_min_m": altitude_min,
        "altitude_max_m": altitude_max,
        "flavor_notes": fields.get("カッピング") or (free_text or None),
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": "販売中",  # サイト上に在庫状態を示す表示が無いため、掲載=販売中として扱う
        "out_of_stock": False,
        "product_url": product_url,
    }


def find_next_page_url(soup: BeautifulSoup, current_page: int) -> str | None:
    pager = soup.select_one("div.pager")
    if not pager:
        return None
    for a in pager.select("a[href]"):
        if a.get_text(strip=True) == str(current_page + 1):
            href = a.get("href", "")
            return href if href.startswith("http") else f"https://r.goope.jp{href}"
    return None


def scrape_all_products() -> tuple[list[dict], list[dict], list[dict]]:
    records = []
    flavored_records = []
    non_bean_records = []

    url = f"{BASE_URL}/menu/{BEANS_CATEGORY_ID}"
    page = 1
    while url:
        soup = fetch_page(url)

        for h4 in soup.select("div.contents_box_inner h4"):
            link_el = h4.select_one("a")
            if not link_el:
                continue
            raw_title = link_el.get_text(strip=True)
            product_url = link_el.get("href", "")
            if product_url.startswith("/"):
                product_url = f"https://r.goope.jp{product_url}"

            price_el = h4.find_next_sibling("div", class_="price")
            price = None
            if price_el:
                price_match = re.search(r"([\d,]+)", price_el.get_text())
                if price_match:
                    price = int(price_match.group(1).replace(",", ""))

            textfield = h4.find_next_sibling("div", class_="textfield")
            fields, free_text = parse_textfield(textfield) if textfield else ({}, "")

            if is_cafe_only(raw_title, free_text):
                non_bean_records.append({
                    "shop_name": SHOP_INFO["name"],
                    "raw_name": raw_title,
                    "non_bean": True,
                    "product_url": product_url,
                })
                continue

            detail = build_record(product_url, raw_title, price, fields, free_text)
            if detail.get("non_bean"):
                non_bean_records.append(detail)
            elif detail.get("is_flavored"):
                flavored_records.append(detail)
            else:
                records.append(detail)

        next_url = find_next_page_url(soup, page)
        if next_url:
            page += 1
            time.sleep(CRAWL_DELAY_SECONDS)
        url = next_url

    return records, flavored_records, non_bean_records


if __name__ == "__main__":
    records, flavored_records, non_bean_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
        "non_bean_products_excluded": non_bean_records,
    }
    with open("data_kagisippo.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kagisippo.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件、"
          f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
