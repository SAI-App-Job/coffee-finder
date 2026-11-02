# -*- coding: utf-8 -*-
"""
scrape_icoffee.py

i珈琲(自家焙煎 ｉ珈琲。https://icoffee.theshop.jp/、愛媛県松山市石風呂町50-7)の商品情報を取得する。
BASE系(theshop.jp)。

【店舗の根拠】
公式サイト(https://sites.google.com/site/ehimeicoffee/home/access)に「スペシャルティコーヒーを自家焙煎 ｉ珈琲」
「所在: 〒791-8084 愛媛県松山市石風呂町50-7」「営業時間 10:00～18:00 定休日 水曜日」。
ネットショップの特商法表記(https://icoffee.theshop.jp/law)の所在地も同住所。

【対象商品について】
実データ確認済み(2026-11-03): サイトマップ・トップページとも商品は12件で、すべて「100gあたりの価格」で
販売されるコーヒー豆(シングルオリジン9、ブレンド3)。数量選択ではなく1商品=100g単位のため weight=100 とする。
「豆のまま/中挽き/細挽き/粗挽きの粉」の選択肢は同額のため豆のままを採用。ドリップバッグ等の扱いは現在なし。
商品名は元の表記から「コーヒー豆：」と「（○○円／100g）」の価格表記を除いてITEMSに明示している。

【在庫について】
item_purchasability と、「豆のまま」バリエーションの在庫表示(在庫あり/在庫なし等)で判定する。

【robots.txtについて】
User-agent: * は /cart/ /web_cart/ /shops/ /api/shops/ 等のみ制限(2026-11-03確認)。python-requests/curl 等は
個別にDisallowのため、識別可能な独自User-Agentを使用し、リクエスト間隔は6秒とする。
"""

import html
import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "i珈琲",
    "url": "https://icoffee.theshop.jp/",
    "platform": "BASE",
    "address": "愛媛県松山市石風呂町50-7",
    "prefecture": "愛媛県",
    "robots_txt_status": "実質許可(2026-11-03確認。/cart/等のみ制限。python-requests/curl名義は禁止のため識別UAを使用)",
    "source_note": "BASE系ネットショップ(https://icoffee.theshop.jp/)の商品ページ12件を2026-11-03に確認。"
                   "公式サイト(Googleサイト)のアクセスページに「スペシャルティコーヒーを自家焙煎」「愛媛県松山市石風呂町50-7」、"
                   "特商法表記も同住所。価格は100gあたりの価格で、全商品とも豆のまま(同額)を採用。取扱銘柄ページ(2026-11-01更新)の"
                   "店頭のみの銘柄はネットショップに無いため含めない。",
    "last_verified_at": "2026-11-03",
}

BASE_URL = "https://icoffee.theshop.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 6

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(商品ページの記載があるものだけ明示), 産地の上書き)
ITEMS = [
    ('12924592', 'コスタリカ セントタラス ガンボア農園 SHB', 100, None, None, 'コスタリカ'),
    ('16192696', 'インドネシア マンデリン ミトラG1', 100, None, None, 'インドネシア'),
    ('18263831', 'アフリカブレンド', 100, 'ブレンド', None, None),
    ('25333292', 'エチオピア グジ ゲイシャジャスミンG1(ナチュラル製法)', 100, None, None, 'エチオピア'),
    ('28912111', 'タンザニア サウステラAA', 100, None, '中煎り', 'タンザニア'),
    ('33008595', 'コロンビア スウィートベリーSUP', 100, None, '中深煎り', 'コロンビア'),
    ('7680839', 'ブラジル サントアントニオ プレミアムショコラ', 100, None, '中深煎り', 'ブラジル'),
    ('7682323', 'ブラジル キャラメラード サンタ・カタリーナ農園(深煎り)', 100, None, '深煎り', 'ブラジル'),
    ('7852493', 'ブラジル キャラメラード サンタ・カタリーナ農園(中煎り)', 100, None, '中煎り', 'ブラジル'),
    ('7684523', 'エチオピア モカ シダモG2', 100, None, None, 'エチオピア'),
    ('7852637', 'アイスコーヒーブレンド', 100, 'ブレンド', None, None),
    ('7852794', 'モカブレンド', 100, 'ブレンド', None, None),
]

PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
SHIPPING_PATTERN = re.compile(r"お手数ですが、カートの中で発送方法を選んでください。.*?送料を比較してみて下さい。")


def build_record(item) -> dict | None:
    item_id, name, weight_g, category_override, roast_level, origin_override = item
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")

    desc_el = soup.select_one("[class*=item-detail_description]")
    desc = re.sub(r"\s+", " ", desc_el.get_text(" ", strip=True)) if desc_el else ""
    desc = SHIPPING_PATTERN.sub("", desc).strip()[:400] or None

    price_m = PRICE_PATTERN.search(resp.text)
    purchasability_m = PURCHASABILITY_PATTERN.search(resp.text)
    sold_out = bool(purchasability_m) and purchasability_m.group(1) == "unpurchasable"
    detail = soup.select_one("[class*=item-detail_container]")
    stock_m = re.search(r"豆のまま\s*(\S+)", detail.get_text(" ", strip=True)) if detail else None
    if stock_m and "在庫なし" in stock_m.group(1):
        sold_out = True

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if category_override:
        parsed["category"] = category_override
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if origin_override and not parsed["origin_country"]:
            parsed["origin_country"] = origin_override
            parsed["origin_source"] = "raw_name"

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level,  # 商品ページに記載がある焙煎度のみ採用
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price_m.group(1)) if price_m else None,
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/items/{item_id}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in ITEMS:
        try:
            record = build_record(item)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item[0]} ({e})")
            continue
        if record is not None:
            records.append(record)
        time.sleep(CRAWL_DELAY_SECONDS)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_icoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_icoffee.json に出力しました")


if __name__ == "__main__":
    main()
