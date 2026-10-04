# -*- coding: utf-8 -*-
"""
scrape_kissatrunk.py

喫茶トランク(https://oldcafetrunk.wixsite.com/-site、大阪府貝塚市西町10-10、
明治時代の古民家を改装した喫茶店の自家焙煎珈琲豆)の商品情報を取得する。Wix。

【店舗発見の経緯】
全国再調査(大阪府)の新規発掘で発見。

【取得方法について】
実データ確認済み(2026-10時点): Wixストアの商品一覧ページ(/-site/category-page)に
5商品が表示される(ガトーショコラ・抹茶のガトーショコラ・自家焙煎珈琲豆(100g)・
ドリップバッグ・メッセージドリップバッグ)。商品詳細ページ・サイトマップの商品一覧は
公開されていない(一覧の商品リンクが壊れている)ため、一覧ページのHTML(SSR済み)から
「商品名 / 価格 / ￥金額」の並びを読み取る。豆は「自家焙煎珈琲豆(100g)」1商品のみで、
他はスイーツ・ドリップバッグのため除外。

【価格について】
商品一覧(ストア)の価格は￥700。トップページの紹介文には「自家焙煎珈琲豆100g800円」と
あり食い違うため、実際に購入時に使われるストア側の価格(700円)を採用した。

【焙煎度・産地について】
トップページに「マスターが直火焙煎している深煎り珈琲」とあるため焙煎度は深煎り。
「その時々でマスターが厳選した珈琲豆を焙煎」とあり銘柄・産地は固定されていないため、
産地・精選方法は null、種別は商品名から自動判定(ブレンド表記なしのためストレート扱い)。

【在庫状況について】
在庫切れの表示はないため販売中として扱う。

【robots.txtについて】
確認済み(2026-10時点): User-agent: * は Allow: /(lightbox用クエリのみDisallow)。
本スクレイパーは識別可能な独自User-Agentを使用する。

【product_urlについて】
商品詳細ページが取得できないため、一覧ページURLに商品名のフラグメント(#商品名)を
付けて一意にしている。
"""

import json
import re
import unicodedata
import urllib.parse

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product

SHOP_INFO = {
    "name": "喫茶トランク",
    "url": "https://oldcafetrunk.wixsite.com/-site",
    "platform": "Wix",
    "address": "大阪府貝塚市西町10-10",
    "prefecture": "大阪府",
    "robots_txt_status": "許可(2026-10確認。User-agent: * は Allow: /。識別可能なUser-Agentを使用)",
}

LIST_PAGE_URL = "https://oldcafetrunk.wixsite.com/-site/category-page"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# 一覧中の対象商品(焙煎豆)。商品名に「珈琲豆」を含み、ドリップバッグ・ギフト・ゼリー等は含まないもの
BEAN_NAME_PATTERN = re.compile(r"珈琲豆|コーヒー豆")
EXCLUDE_PATTERN = re.compile(r"ドリップバッグ|セット|ギフト|ゼリー|ケーキ|ショコラ")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")
PRICE_PATTERN = re.compile(r"[￥¥]\s*([\d,]+)")


def fetch_lines() -> list[str]:
    resp = requests.get(LIST_PAGE_URL, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return [l.strip() for l in soup.get_text("\n").split("\n") if l.strip()]


def parse_items(lines: list[str]) -> list[dict]:
    """「商品名 / 価格 / ￥金額」の並びから商品を取り出す。"""
    items = []
    for i, line in enumerate(lines):
        if line == "価格" and i >= 1 and i + 1 < len(lines):
            pm = PRICE_PATTERN.match(lines[i + 1])
            if pm:
                items.append({"name": unicodedata.normalize("NFKC", lines[i - 1]),
                              "price": int(pm.group(1).replace(",", ""))})
    return items


def build_record(item: dict) -> dict | None:
    name = item["name"]
    if not BEAN_NAME_PATTERN.search(name) or EXCLUDE_PATTERN.search(name):
        return None
    parsed = parse_product(name)
    wm = WEIGHT_PATTERN.search(name)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": None,
        "origin_source": None,
        "designated_brand": None,
        "processing_method": None,
        "grade": None,
        "roast_level": "深煎り",
        "roast_hint": None,
        "flavor_notes": None,
        "farm_note": None,
        "post_processing_tags": [],
        "blend_components": [],
        "price": item["price"],
        "weight_g": int(wm.group(1)) if wm else None,
        "stock_status": "販売中",
        "out_of_stock": False,
        "product_url": f"{LIST_PAGE_URL}#{urllib.parse.quote(name)}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in parse_items(fetch_lines()):
        record = build_record(item)
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_kissatrunk.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kissatrunk.json に出力しました")


if __name__ == "__main__":
    main()
