# -*- coding: utf-8 -*-
"""
scrape_tirol.py

珈琲亭ちろる(cafe-tirol.shop-pro.jp、〒070-0033 北海道旭川市3条通8丁目
左7、自家焙煎豆のオンライン販売)の商品情報を取得する。カラーミーショップ
(shop-pro.jp)。

住所・電話番号(0166-26-7788)はサイトフッターにて実データ確認済み
(候補リストの住所と一致)。

robots.txt確認済み(2026-09時点): User-agent: *は/secure/と/cart/のみ
制限。AhrefsBot等SEO系ボットのみ個別にDisallow: /(はぜや珈琲と同一の
記述)。

【文字コード】EUC-JP(実データ確認済み)。

【httpとhttpsについて】
実データ確認済み: https://cafe-tirol.shop-pro.jp/へのアクセスはhttpへ
301リダイレクトされる(常時SSL非対応)。本スクレイパーは最初からhttpの
URLを使用する。

【商品一覧の取得方法について】
実データ確認済み(2026-09時点、全18件、1ページ12件×2ページ):
一覧ページ(?mode=srh&cid=&keyword=&sort=n&page=N)のp.item_name/
p.item_priceから商品名・価格を取得する。

【対象商品の絞り込みについて】
実データ確認済み: 全18件中、「密封ビン ボトルケース付」(空きビン単体の
グッズ)の1件のみが非対象。NON_BEAN_KEYWORDSで除外する。ICEブレンドは
アイスコーヒー用に焙煎した豆そのものであるため対象に含める。

【焙煎度について】
実データ確認済み: 商品名末尾に【浅煎】【中煎】【深煎】【極深】のいずれか
が付く(coffee_parserのROAST_KEYWORDSのカタカナ表記とは粒度が異なる)ため
roast_levelには入れずroast_hintとして保持し、roast_selectable=Falseと
する(405coffee.py・はぜや珈琲と同じ考え方)。

【重量・挽き方バリアントについて】
実データ確認済み: 詳細ページのvar Colorme JSONに、100g/200g/300g等の
重量と「そのまま/中挽き/細挽き/粗挽き」等の挽き方を組み合わせた
バリアントがあり、価格は重量に比例する。豆のまま(「そのまま」を含む
option2_value)×最小重量を代表バリアントとして採用する(405coffee.pyと
同じ考え方)。一覧ページの価格は最小重量バリアントの価格と一致することを
実データ確認済み。
"""

import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "珈琲亭ちろる",
    "url": "http://cafe-tirol.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "北海道旭川市3条通8丁目左7",
    "prefecture": "北海道",
    "robots_txt_status": "許可(2026-09確認。User-agent: *は/secure/と/cart/のみ制限。"
                          "AhrefsBot等SEO系ボットのみ個別にDisallow: /)",
}

BASE_URL = "http://cafe-tirol.shop-pro.jp/"
LIST_URL = "http://cafe-tirol.shop-pro.jp/?mode=srh&cid=&keyword=&sort=n"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["密封ビン"]
ROAST_HINT_KEYWORDS = ["極深煎", "極深", "浅煎", "中煎", "深煎"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*\});", re.DOTALL)


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-jp"  # 実データ確認済み(Content-Type: text/html; charset=EUC-JP)
    return BeautifulSoup(resp.text, "html.parser")


def fetch_list_items() -> list[dict]:
    items = []
    page = 1
    while True:
        url = LIST_URL if page == 1 else f"{LIST_URL}&page={page}"
        soup = fetch_page(url)
        lis = soup.select("div.item-list li")
        if not lis:
            break
        for li in lis:
            name_el = li.select_one("p.item_name a")
            if not name_el:
                continue
            href = name_el.get("href", "")
            m = re.search(r"pid=(\d+)", href)
            if not m:
                continue
            raw_title = name_el.get_text(strip=True)
            title = unicodedata.normalize("NFKC", raw_title)
            if any(kw in title for kw in NON_BEAN_KEYWORDS):
                continue
            items.append({"pid": m.group(1), "title": title, "url": f"{BASE_URL}?pid={m.group(1)}"})
        page += 1
    return items


def extract_colorme_product(soup: BeautifulSoup) -> dict | None:
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        m = COLORME_JSON_PATTERN.search(text)
        if not m:
            continue
        try:
            import json
            data = json.loads(m.group(1))
        except Exception:
            return None
        return data.get("product")
    return None


def weight_from_variant(variant: dict | None, fallback_text: str = "") -> int | None:
    if variant:
        m = WEIGHT_PATTERN.search(variant.get("option1_value") or "")
        if m:
            return int(m.group(1))
    m = WEIGHT_PATTERN.search(fallback_text or "")
    return int(m.group(1)) if m else None


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    """挽き方×重量のバリアントから代表の1件を選ぶ。豆のまま(「そのまま」)を
    優先し、その中で最小重量のものを採用する(405coffee.pyと同じ考え方)。"""
    if not variants:
        return None

    def weight_key(v):
        w = weight_from_variant(v)
        return w if w is not None else float("inf")

    whole_bean = [v for v in variants if "そのまま" in (v.get("option2_value") or "")]
    pool = whole_bean or variants
    return min(pool, key=weight_key)


def detect_roast_hint(text: str) -> str | None:
    for kw in ROAST_HINT_KEYWORDS:
        if kw in text:
            return kw
    return None


def build_record(item: dict, colorme_product: dict) -> dict:
    title = item["title"]
    parsed = parse_product(title)

    variant = pick_canonical_variant(colorme_product.get("variants", []))

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": variant.get("option_price_including_tax") if variant else colorme_product.get("sales_price_including_tax"),
            "product_url": item["url"],
        }

    stock_num = colorme_product.get("stock_num")
    structural_out_of_stock = isinstance(stock_num, int) and stock_num <= 0
    stock_status = detect_stock_status(title, structural_out_of_stock)

    price = variant.get("option_price_including_tax") if variant else colorme_product.get("sales_price_including_tax")
    weight_g = weight_from_variant(variant, title)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": None,
        "roast_hint": detect_roast_hint(title),
        "roast_selectable": False,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    list_items = fetch_list_items()

    records = []
    flavored_records = []
    for item in list_items:
        try:
            soup = fetch_page(item["url"])
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['url']} ({e})")
            continue
        colorme_product = extract_colorme_product(soup)
        if not colorme_product:
            continue
        detail = build_record(item, colorme_product)
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
    with open("data_tirol.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_tirol.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
