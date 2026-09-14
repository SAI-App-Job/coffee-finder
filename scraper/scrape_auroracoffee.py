# -*- coding: utf-8 -*-
"""
scrape_auroracoffee.py

オーロラコーヒー(auroracoffee.shop-pro.jp、〒990-2435 山形県山形市青田4丁目9-31 1F、
自家焙煎豆のオンライン販売)の商品情報を取得する。カラーミーショップ(shop-pro.jp)。

【2段構成のサイトについて】
実データ確認済み(2026-09時点): auroracoffee.shop-pro.jp(カート機能を提供する
Colorme本体)のトップページはmeta refreshで独自ドメインのhttps://www.auroracoffee.jp/shop/
(商品一覧のデザインページ)に即座に転送される。この独自ページには各商品ごとに
`<script src="https://auroracoffee.shop-pro.jp/?mode=cartjs&pid=XXXXXX...">`という
埋め込みウィジェット(JSレンダリングのため静的HTMLには価格が出てこない)がある。
そのためこのスクレイパーは、(1) www.auroracoffee.jp/shop/をパースしてセクション見出し
(STRAIGHT/BLEND/DECAF等)ごとの商品名・pidを収集、(2) 各pidをauroracoffee.shop-pro.jp
側の商品詳細ページ(var Colorme JSON、405coffee.py等と同じ抽出方法)から実際の価格・
重量バリアントを取得、という2段階で行う。

【住所について】
auroracoffee.shop-pro.jp側の特定商取引法ページで実データ確認(2026-09時点):
〒990-2435 山形県山形市青田4丁目9-31 1F。

robots.txt確認済み(2026-09時点): auroracoffee.shop-pro.jpはPHILOCOFFEA等と同一の
記述(/secure/と/cart/のみ制限)。独自ドメインwww.auroracoffee.jp側はrobots.txt自体が
存在しない(404、ロリポップ標準の404ページが返る)ため実質無制限と判断した。

【対象セクションについて】
実データ確認済み: www.auroracoffee.jp/shop/にはLIMITED(5件)・STRAIGHT(9件)・
BLEND(6件、うち1件は「ORIGINAL_BLEND」という総量2kg以上のオーダーメイド案内で
pidが無いため自動的に除外される)・DECAF(3件)・EASY_COFFEE_BAG(4件、ティーバッグ
形式のドリップ用でpid付きだが焙煎豆単品ではない)・GOODS/GIFT(器具・ギフト)の
6セクションがある。EASY_COFFEE_BAG/GOODS/GIFTは対象外とし、LIMITED/STRAIGHT/
BLEND/DECAFのみを対象とする。

【既知の残存重複について】
実データ確認済み(2026-09時点): 「コロンビア／ラセレーザ」がLIMITEDセクションと
STRAIGHTセクションの両方に別のpid(192090525/184032016)で掲載されており、
価格・重量とも同一(840円/100g)。店側が同じ銘柄を2箇所に重複掲載している
実際のサイト構成のため、pidが異なる限りこのスクレイパー側では統合しない
(1518coffee.py等と同じ「軽微な既知の残存重複」として許容する)。

【重量・挽き方バリアントについて】
実データ確認済み: 各商品のvariantsはoption1_value(「中煎り／100g」のように
焙煎度+重量の組み合わせ)×option2_value(挽き方)の掛け合わせ。挽き方は価格に
影響しないため、最小重量(100g)×「豆のまま」を代表バリアントとして採用する
(405coffee.py等のpick_canonical_variant()と同じ考え方)。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "オーロラコーヒー",
    "url": "https://auroracoffee.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "山形県山形市青田4丁目9-31 1F",
    "prefecture": "山形県",
    "robots_txt_status": "許可(2026-09確認。shop-pro.jp側はPHILOCOFFEA等と同一の記述で"
                          "/secure/と/cart/以外は制限なし。独自ドメイン側はrobots.txt自体が"
                          "存在せず実質無制限)",
}

CART_BASE_URL = "https://auroracoffee.shop-pro.jp"
SHOP_PAGE_URL = "https://www.auroracoffee.jp/shop/"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 理由はモジュールdocstring参照(焙煎豆単品を扱うセクションのみ対象)
TARGET_SECTIONS = ["LIMITED.", "STRAIGHT.", "BLEND.", "DECAF."]

PID_PATTERN = re.compile(r"[?&]pid=(\d+)")
COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str, encoding: str | None = None) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    if encoding:
        resp.encoding = encoding
    return BeautifulSoup(resp.text, "html.parser")


def scrape_shop_page_items() -> list[dict]:
    """独自ドメイン側の商品一覧デザインページから、対象セクションの商品名・pidを集める。"""
    # 実データ確認済み(2026-09時点): レスポンスヘッダにcharset指定が無く(Content-Type:
    # text/htmlのみ)、HTML側は<meta charset="UTF-8">のため明示的にUTF-8を指定する
    soup = fetch_page(SHOP_PAGE_URL, encoding="utf-8")
    items = []
    seen_pids = set()

    for h2 in soup.find_all("h2"):
        section_name = h2.get_text(strip=True)
        if section_name not in TARGET_SECTIONS:
            continue
        ul = h2.find_next_sibling("ul")
        if not ul:
            continue
        for li in ul.select("li.beans"):
            script_el = li.select_one('p.cart script, p.price script')
            if not script_el or not script_el.get("src"):
                continue
            pid_m = PID_PATTERN.search(script_el["src"])
            if not pid_m:
                continue
            pid = pid_m.group(1)
            if pid in seen_pids:
                continue
            name_el = li.select_one("p.name")
            if not name_el:
                continue
            seen_pids.add(pid)
            items.append({
                "pid": pid,
                "raw_name": name_el.get_text(strip=True),
            })
    return items


def extract_colorme_product(soup: BeautifulSoup) -> dict | None:
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        m = COLORME_JSON_PATTERN.search(text)
        if not m:
            continue
        import json as _json
        try:
            data = _json.loads(m.group(1))
        except _json.JSONDecodeError:
            return None
        return data.get("product")
    return None


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    """挽き方×重量(+焙煎度)の組み合わせバリアントから、豆のまま×最小重量を代表として選ぶ。
    理由はモジュールdocstring参照。"""
    if not variants:
        return None

    def weight_key(v):
        m = WEIGHT_PATTERN.search(v.get("option1_value") or "")
        return int(m.group(1)) if m else float("inf")

    whole_bean = [v for v in variants if "豆のまま" in (v.get("option2_value") or "")]
    pool = whole_bean or variants
    return min(pool, key=weight_key)


def build_record(item: dict) -> dict | None:
    raw_name = item["raw_name"]
    parsed = parse_product(raw_name)

    detail_url = f"{CART_BASE_URL}/?pid={item['pid']}"
    soup = fetch_page(detail_url, encoding="euc-jp")
    product = extract_colorme_product(soup)
    if not product:
        return None

    variant = pick_canonical_variant(product.get("variants", []))
    price = variant.get("option_price_including_tax") if variant else product.get("sales_price_including_tax")
    weight_m = WEIGHT_PATTERN.search(variant.get("option1_value") or "") if variant else None
    weight_g = int(weight_m.group(1)) if weight_m else None

    stock_num = product.get("stock_num")
    structural_out_of_stock = isinstance(stock_num, int) and stock_num <= 0
    stock_status = detect_stock_status(raw_name, structural_out_of_stock)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": raw_name,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": detail_url,
        }

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": raw_name,
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
        "product_url": detail_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    items = scrape_shop_page_items()
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for item in items:
        product_url = f"{CART_BASE_URL}/?pid={item['pid']}"
        prev = previous.get(product_url)
        if is_unchanged(prev, raw_name=item["raw_name"]):
            records.append(prev)
            continue

        try:
            detail = build_record(item)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={item['pid']} ({e})")
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
    with open("data_auroracoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_auroracoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
