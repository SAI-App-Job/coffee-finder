# -*- coding: utf-8 -*-
"""
scrape_minatocoffee.py

みなと珈琲店(www.minato-coffee.com、〒737-0046 広島県呉市中通3-1-30、
60年以上の歴史を持つ呉市の自家焙煎珈琲豆専門店)の商品情報を取得する。
プラットフォーム: 独自ECシステム(レガシーなCGIベースのショッピングカート、
Shift_JISエンコード。BASE/Shopify/カラーミー/Ocnk/theShop/EC Force等の
いずれにも該当しない)。

【HTTPSではなくHTTPを使用する理由について】
実データ確認済み(2026-09時点): https://www.minato-coffee.comはTLS証明書の
ホスト名不一致エラー(証明書がxrea.com共用サーバーの汎用証明書になっており
www.minato-coffee.comを含んでいない)が発生し接続できない。一方、
http://www.minato-coffee.com(平文HTTP)は同一サーバー・同一コンテンツに
問題なく接続でき、証明書検証を無効化する必要は無い(検証を無効化して
不正な証明書を迂回するのではなく、サーバーが実際に提供している非TLS
エンドポイントをそのまま利用するだけ)。本スクレイパーは全リクエストを
http://で送信する。

【住所について】
候補リストでは呉市在の老舗として住所未確定だったが、公式サイトの
会社案内ページ(http://www.minato-coffee.com/03annai/index.html)で実データ
確認したところ「住所：７３７−００４６　呉市中通３−１−３０」であることを
確認した(2026-09時点、会社名「(有)みなと珈琲店」)。

robots.txt確認済み(2026-09時点): http://www.minato-coffee.com/robots.txtは
404(存在しない)。クロール制限の記述が無いため実質無制限と判断した。

【商品一覧の取得方法について】
実データ確認済み: 商品一覧ページ(/shop/shop.cgi?class=all&FF=<0,10,20,...>)
に10件ずつページングされた商品カード(div.goods_customize)が並び、各カードの
h2タグに「商品名　重量パック [商品コード]」の形式で商品名と重量、価格
(税込)がli要素に直接出力されている静的HTMLで取得できる(JS不要)。全71件。

【非コーヒー商品の除外について】
実データ確認済み: 商品コードが"c"で始まる商品(セイロン・ダージリン・
アッサム・リプトンレストランブレンド・アールグレイ)は紅茶であり非対象。
「海軍伝統の紅茶」はc0007として登録されている一方、同一商品がos0010という
"c"以外のコードでも重複登録されているため、商品名に「紅茶」を含む商品も
併せて除外する。商品コードが空([])の1件(「港町"呉"にかおる珈琲港町
250gパック」)は、同一銘柄の別コード版(os0011「港町"呉"にかおる珈琲」)と
併存する編集ミスと思われる非正規のカタログ行のため除外する(有効な商品
コードを持たない行は正規のSKUではないと判断)。

【全角/半角表記の揺れについて】
実データ確認済み: 「メキシコ　ＪＡＳオーガニック500ｇ」(全角JAS)と
「メキシコ JASオーガニック250ｇ」(半角JAS)のように、同一銘柄でも全角/
半角表記が商品間で揺れている箇所がある。これをunicodedata.normalize
("NFKC", ...)で正規化してから基準名グルーピングを行うことで、表記揺れに
よる重複(別商品として認識されてしまう問題)を防ぐ。

【重量違いの重複について】
実データ確認済み: コーヒー豆商品はいずれも500g/250gの2種類の重量で別々の
カタログ行として登録されている(バリアントではない)。さらに、初期の
ブレンド8銘柄(マイルド・ブルマン・ヨーロピアン・ストロング)は"os"接頭の
コードと"b"接頭のコードで同一商品・同一価格の行が重複登録されている
(実データ確認済み、名称・価格ともに完全一致)。また「マウンテン」系4銘柄
(ブルーマウンテンNo1・ハイマウンテン)は"st"接頭と"m"接頭で同様に重複
登録されている。商品名末尾の重量・パック表記を除いた基準名でグルーピング
し、最小重量(250g、一部200g)を代表として採用することで、これらの重複を
自然に解消する。
"""

import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "みなと珈琲店",
    "url": "http://www.minato-coffee.com/",
    "platform": "独自ECシステム(レガシーCGIカート)",
    "address": "広島県呉市中通3-1-30",
    "prefecture": "広島県",
    "robots_txt_status": "実質許可(2026-09確認。http://www.minato-coffee.com/robots.txtが"
                          "404で存在せず、クロール制限の記述なし)",
}

BASE_URL = "http://www.minato-coffee.com"
LIST_URL = f"{BASE_URL}/shop/shop.cgi"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

CODE_PATTERN = re.compile(r"\s*\[([^\]]*)\]\s*$")
PRICE_PATTERN = re.compile(r"([\d,]+)")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
TRAILING_WEIGHT_PATTERN = re.compile(r"[\s　]*\d+\s*[gｇ]\s*(?:ﾊﾟｯｸ|パック)?\s*$")


def fetch_page(ff: int) -> BeautifulSoup:
    params = {"class": "all", "keyword": "", "superkey": "1", "FF": str(ff), "order": "", "pic_only": ""}
    resp = requests.get(LIST_URL, params=params, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    resp.encoding = "shift_jis"
    return BeautifulSoup(resp.text, "html.parser")


def parse_name_and_code(h2_text: str) -> tuple[str, str]:
    # 全角英数字(JAS表記の全角/半角混在等)を半角に正規化してから処理する
    h2_text = unicodedata.normalize("NFKC", h2_text)
    m = CODE_PATTERN.search(h2_text)
    code = m.group(1) if m else ""
    name = CODE_PATTERN.sub("", h2_text).strip()
    name = name.lstrip("■").strip()
    return name, code


def fetch_items() -> list[dict]:
    items = []
    ff = 0
    while True:
        soup = fetch_page(ff)
        blocks = soup.select("div.goods_customize")
        if not blocks:
            break
        for block in blocks:
            h2 = block.select_one("h2")
            if not h2:
                continue
            name, code = parse_name_and_code(h2.get_text())
            if not code or code.startswith("c") or "紅茶" in name:
                continue  # 理由はモジュールdocstring参照(紅茶・非正規重複行を除外)

            price = None
            for li in block.find_all("li"):
                text = li.get_text()
                if "価格" in text:
                    m = PRICE_PATTERN.search(text.split("]", 1)[-1])
                    if m:
                        price = int(m.group(1).replace(",", ""))
                    break

            items.append({"title": name, "code": code, "price": price,
                          "url": f"{BASE_URL}/shop/shop.cgi?mode=p_wide&class=all&id={code}"})
        if len(blocks) < 10:
            break
        ff += 10
    return items


def base_name_and_weight(title: str) -> tuple[str, int | None]:
    m = WEIGHT_PATTERN.search(title)
    weight_g = int(m.group(1)) if m else None
    base = TRAILING_WEIGHT_PATTERN.sub("", title).strip()
    return base, weight_g


def pick_canonical_items(items: list[dict]) -> list[dict]:
    by_base_name: dict[str, dict] = {}
    for item in items:
        base, weight_g = base_name_and_weight(item["title"])
        item = {**item, "base_name": base, "weight_g": weight_g}
        weight_key = weight_g if weight_g is not None else float("inf")
        existing = by_base_name.get(base)
        if existing is None:
            by_base_name[base] = item
            continue
        existing_weight = existing["weight_g"] if existing["weight_g"] is not None else float("inf")
        if weight_key < existing_weight:
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
    items = fetch_items()
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
    with open("data_minatocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_minatocoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
