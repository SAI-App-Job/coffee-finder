# -*- coding: utf-8 -*-
"""
scrape_noahcoffee.py

Noah Coffee(ノアコーヒー、noah-coffee.com、〒899-5116 鹿児島県霧島市隼人町
内1449-1、自家焙煎豆のオンライン販売)の商品情報を取得する。楽々シリーズ
(Raku-Uru)。scrape_sabucoffee.py・scrape_kogetsuan.pyと同一プラットフォーム
だが、独自ドメイン(noah-coffee.com)がRaku-Uruの店舗ページをそのまま配信
している(cart.raku-uru.jpへのリンクはカート・会員機能のみ)。

【住所について】
実データ確認済み(2026-09時点): 公式ストアの特定商取引法ページ
(https://noah-coffee.com/law)で「〒899-5116　鹿児島県霧島市隼人町内
1449-1」との記載を確認(候補リストには具体的な住所が無かったため、本
スクレイパーで新たに一次情報から特定した)。

robots.txt確認済み(2026-09時点): /robots.txtは存在せず、SPAではなく
サーバー側で「ページが見つかりません」という通常ページがフォールバックで
返る(404ハンドラ未設定)。明示的な禁止事項が無いため実質許可として扱う。

【商品ラインナップについて】
実データ確認済み(2026-09時点): この店舗は国内(鹿児島県沖永良部島)産の
希少な国産コーヒーを主力とする。「【Made in Japan Coffee】Lineup」
(categoryId=8857)が対象カテゴリの親カテゴリで、傘下の全16件がここに
集約されている(サブカテゴリの「沖永良部島産」「Blend coffee」等は
重複を含むため、親カテゴリのみを対象とする)。

【対象商品について】
実データ確認済み(全16件): 大半がドリップバッグ・コーヒー果実(カスカラ)
ティー・詰め合わせセット・木樽入りギフト包装(通常の100g商品と同一銘柄の
化粧箱違い)のため対象外。単一銘柄のコーヒー豆として残るのは以下の2件のみ:
・沖永良部島100%「和の極（わのきわみ）」100g(ストレート)
・沖永良部島ブレンド「奏の極（かなでのきわみ）」100g(ブレンド、国産×海外)
NON_BEAN_KEYWORDSで残り14件(ドリップパック/ドリップバッグ/セット/
ティー/果実/木樽入り/三種の極)を除外する。

【産地(国産コーヒー)の扱いについて】
実データ確認済み: 商品詳細ページに「原産地：鹿児島県(沖永良部島)」と
明記されている日本国内産のコーヒー豆だが、coffee_parser.pyの
ORIGIN_COUNTRY_KEYWORDSには「日本」が未登録(「タイ」「中国」と同様、
汎用的すぎる語のマスタ登録は誤爆リスクがあるため見送られていると見られる)。
本スクレイパーでは、商品名に含まれる「沖永良部」(誤爆リスクの低い固有の
地名)をトリガーに、この店舗内でのみローカルにorigin_country="日本"を
補完する(coffee_parser.py共通ロジックの変更は本タスクの範囲外のため、
scrape_cafeclaudia.pyの「雲南」→中国のローカル判定と同じ方針)。

【価格・重量について】
実データ確認済み: 対象2件とも「豆」「粉（中挽き）」の2バリアントを持つが、
価格は挽き方に関わらず同一(商品ページ本体の価格を採用すればよく、
バリアント別の価格取得は不要)。重量はいずれも商品名記載の100gで固定。

【flavor_notes(2026-09-22追記)】
実データ確認済み: div.item-detail-txt1に対象2件全てで見出し「商品詳細」・
紹介文・産地エピソード・賞味期限/原材料/原産地の仕様情報が入っている。
見出し「商品詳細」は除去し、末尾には「抽出方法」以降(湯量・やけど注意等
の一般的な抽出手順、保存方法の重複、店舗リンク)、または区切りのドット
記号列(「・・・・・」)が続く場合があるため、いずれか先に現れた方の直前で
打ち切る。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "Noah Coffee",
    "url": "https://noah-coffee.com/",
    "platform": "楽々シリーズ(Raku-Uru)",
    "address": "鹿児島県霧島市隼人町内1449-1",
    "prefecture": "鹿児島県",
    "robots_txt_status": "実質許可(2026-09確認。robots.txt自体が存在せず"
                          "「ページが見つかりません」という通常ページが"
                          "フォールバックで返る。明示的な禁止事項なし)",
}

BASE_URL = "https://noah-coffee.com"
# 理由はモジュールdocstring参照(【Made in Japan Coffee】Lineupの親カテゴリ。
# サブカテゴリはここに含まれる商品の重複のため使用しない)
BEAN_CATEGORY_ID = "8857"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["ドリップパック", "ドリップバッグ", "セット", "ティー", "果実", "木樽", "三種"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
FLAVOR_LEADING_PATTERN = re.compile(r"^商品詳細\n")
FLAVOR_STOP_PATTERN = re.compile(r"・{5,}|抽出方法")


def extract_flavor_notes(soup: BeautifulSoup) -> str | None:
    el = soup.select_one("div.item-detail-txt1")
    text = el.get_text("\n", strip=True) if el else ""
    text = FLAVOR_LEADING_PATTERN.sub("", text)
    m = FLAVOR_STOP_PATTERN.search(text)
    if m:
        text = text[:m.start()].strip()
    return text or None


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def fetch_item_ids() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/item-list?categoryId={BEAN_CATEGORY_ID}")
    ids = []
    for a in soup.select('a[href^="/item-detail/"]'):
        href = a.get("href", "")
        item_id = href.rsplit("/", 1)[-1]
        if item_id and item_id not in ids:
            ids.append(item_id)
    return ids


def build_record(soup: BeautifulSoup, product_url: str) -> dict | None:
    title_el = soup.select_one("h2.item-detail-name")
    if not title_el:
        return None
    title = title_el.get_text(strip=True)
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    price_el = soup.select_one("span.raku-item-vari-price-num")
    price = None
    if price_el:
        m = re.search(r"([\d,]+)", price_el.get_text())
        if m:
            price = int(m.group(1).replace(",", ""))

    parsed = parse_product(title)

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

    # 理由はモジュールdocstring参照(coffee_parser.pyに未収録の「日本」の
    # ローカル補正。「沖永良部」は誤爆リスクの低い固有地名)
    if not parsed["origin_country"] and "沖永良部" in title:
        parsed["origin_country"] = "日本"
        parsed["origin_source"] = "region_name"

    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None

    has_orderinvalid = soup.select_one("div.item-dtail-orderinvalid") is not None
    has_add_cart = soup.select_one("a.raku-add-cart") is not None
    structural_out_of_stock = has_orderinvalid and not has_add_cart
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
        "roast_level": parsed["roast_level"],
        "flavor_notes": extract_flavor_notes(soup),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    item_ids = fetch_item_ids()

    records = []
    flavored_records = []
    for item_id in item_ids:
        product_url = f"{BASE_URL}/item-detail/{item_id}"
        try:
            detail = build_record(fetch_page(product_url), product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
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
    with open("data_noahcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_noahcoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
