# -*- coding: utf-8 -*-
"""
scrape_thecoffeeshop.py

THE COFFEESHOP(os.thecoffeeshop.jp、東京都渋谷区猿楽町2-3、自家焙煎豆の
オンライン販売)の商品情報を取得する。フューチャーショップ
(class名の"fs-c-"プレフィックスから実データ確認)。

【店舗発見の経緯】
高田馬場エリアの調査を機に開始した全国の未調査エリア洗い出しの一環で、渋谷
エリアを調査した際にtailoredcafe.jp/coffee-labo.co.jpの紹介記事経由で発見。

【対象カテゴリについて】
実データ確認済み(2026-09時点): 「SINGLE ORIGIN」(/c/beans/singleorigin、
12件)と「ORIGINAL MIX」(/c/beans/originalmix、8件)を対象とする。両カテゴリ
とも複数銘柄セット・大容量バリューパック・水出しコーヒーバッグ・ドリップ
セットが混在しているためNON_BEAN_KEYWORDSで除外する(バリューパックは
既存の100g商品と重複するため)。

【商品説明の取得方法について】
実データ確認済み: 商品詳細ページのJSON-LD(@type: Product)のdescriptionに、
HTMLエンティティで二重エスケープされた構造化HTML(dl.commentarea内の
ROASTER COMMENT、dl.flavorarea内のFLAVOR、末尾のSTORY見出し以降の農園
説明文)が埋め込まれている。html.unescape()でデコードしBeautifulSoupで
再パースする。ROASTER COMMENT(dd)・FLAVORのdd内テキスト(画像alt以外)・
STORYセクションの最初の段落(h3見出し+直後のp)をflavor_notesとして採用し、
ROAST/ACIDITY/おすすめ抽出スタイルの各セクション(焙煎度・酸味の星評価・
抽出器具紹介)は対象外とする(産地情報や器具紹介であり具体的な風味描写では
ないため)。

【重量について】
実データ確認済み: 商品詳細ページのspan.fs-c-productPrice__main__labelに
「100g」のように商品の基準重量が入っている(バリアント選択による重量変更は
無く、挽き方[豆のまま/粗/中粗/中/細]の選択のみ)。

【レート制限について】
実データ確認済み: 詳細ページの連続取得で断続的に429(Too Many Requests)が
発生する(2026-09確認)。1リクエストごとに1秒のスリープを挟むことで軽減する。
"""

import html
import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    detect_stock_status,
    detect_country_name,
)

SHOP_INFO = {
    "name": "THE COFFEESHOP",
    "url": "https://www.thecoffeeshop.jp/",
    "platform": "フューチャーショップ",
    "address": "東京都渋谷区猿楽町2-3",
    "prefecture": "東京都",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://os.thecoffeeshop.jp"
CATEGORY_URLS = [f"{BASE_URL}/c/beans/singleorigin", f"{BASE_URL}/c/beans/originalmix"]
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["Value Pack", "SPECIAL SET", "Drip Set", "COLD BREW COFFEE", "COFFEEBASE"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch(url: str) -> tuple[BeautifulSoup, str]:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser"), resp.text


def fetch_product_urls() -> dict[str, bool]:
    """URL -> is_blend(ORIGINAL MIXカテゴリ由来か)の辞書を返す。
    「September Mix 2026」のように商品名が英語の"Mix"表記のみで、
    coffee_parser.pyのBLEND_KEYWORDS(「ブレンド」「blend」「ミックス」)の
    いずれにも一致しないブレンド商品が実データで見つかったため、商品名だけに
    頼らずカテゴリ由来(ORIGINAL MIX配下=ブレンド確定)でcategoryを上書きする。"""
    urls: dict[str, bool] = {}
    for cat_url in CATEGORY_URLS:
        is_blend_category = "originalmix" in cat_url
        soup, _ = fetch(cat_url)
        for a in soup.select('a[href*="/c/beans/"]'):
            href = a.get("href", "")
            # 実データ確認済み: 商品スラッグは数字のみ(例: singleorigin/00594)と
            # 英数字(例: originalmix/septembermix)の両方がある。並び替え
            # クエリ(?sort=...)のみ除外する。
            m = re.search(r"/c/beans/[a-z]+/[a-z0-9]+", href)
            if not m:
                continue
            url = BASE_URL + m.group(0)
            urls.setdefault(url, is_blend_category)
    return urls


def extract_jsonld_product(raw_html: str) -> dict | None:
    for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', raw_html, re.DOTALL):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if data.get("@type") == "Product":
            return data
    return None


def parse_flavor_notes(description_html_escaped: str) -> str | None:
    unescaped = html.unescape(description_html_escaped or "")
    soup = BeautifulSoup(unescaped, "html.parser")

    parts = []

    comment_dd = soup.select_one("dl.commentarea dd")
    if comment_dd:
        text = comment_dd.get_text(strip=True)
        if text:
            parts.append(text)

    flavor_dd = soup.select_one("dl.flavorarea dd")
    if flavor_dd:
        # 画像(alt="フレーバーチャート画像")・btxt(英語見出し)は除き、
        # 残りのテキストノード(日本語風味描写)のみを採用する
        for img in flavor_dd.select("img"):
            img.decompose()
        text = flavor_dd.get_text("\n", strip=True)
        if text:
            parts.append(text)

    # STORY見出し(h4)の直後にあるh3(サブ見出し)とp(最初の段落)を採用する
    story_heading = None
    for h4 in soup.select("h4"):
        if h4.get_text(strip=True) == "STORY":
            story_heading = h4
            break
    if story_heading:
        h3 = story_heading.find_next("h3")
        if h3:
            text = h3.get_text(strip=True)
            if text:
                parts.append(text)
        p = story_heading.find_next("p")
        if p:
            text = p.get_text(strip=True)
            if text:
                parts.append(text)

    return "\n".join(parts) if parts else None


def build_record(product_url: str, is_blend_category: bool = False) -> dict | None:
    soup, raw_html = fetch(product_url)
    data = extract_jsonld_product(raw_html)
    if not data:
        return None

    title = (data.get("name") or "").strip()
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)
    if is_blend_category:
        parsed["category"] = "ブレンド"
    offers = data.get("offers") or {}
    price = offers.get("price")
    if isinstance(price, str):
        price = int(re.sub(r"[^\d]", "", price)) if re.search(r"\d", price) else None
    elif isinstance(price, float):
        price = int(price)

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

    flavor_notes = parse_flavor_notes(data.get("description") or "")

    origin_hint = detect_country_name(title)
    if origin_hint:
        parsed["origin_country"] = origin_hint
        parsed["origin_source"] = "raw_name"
    parsed = apply_category_hint_fallback(parsed, title)

    weight_label = soup.select_one("span.fs-c-productPrice__main__label")
    weight_m = WEIGHT_PATTERN.search(weight_label.get_text()) if weight_label else None
    weight_g = int(weight_m.group(1)) if weight_m else None

    availability = (offers.get("availability") or "").rstrip("/").split("/")[-1]
    structural_out_of_stock = availability not in ("InStock", "")
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
        "flavor_notes": flavor_notes,
        "post_processing_tags": parsed["post_processing_tags"],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_product_urls()

    records = []
    flavored_records = []
    for product_url, is_blend_category in product_urls.items():
        time.sleep(1.0)
        try:
            detail = build_record(product_url, is_blend_category)
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


def main():
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_thecoffeeshop.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_thecoffeeshop.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
