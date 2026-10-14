# -*- coding: utf-8 -*-
"""
scrape_kurikuricoffee.py

栗栗珈琲(https://www.kurikuricoffee.jp/、島根県益田市あけぼの西町8-6)の商品情報を取得する。
おちゃのこネット(Ocnk)クリーンURLテーマ。

【店舗発見の経緯】
全国再調査(島根県)の新規発掘で発見。住所は特定商取引法表示(/info)で確認。

【robots.txt】
確認済み(2026-10-15時点): GPTBot/Bytespider/TikTokSpider/meta-externalagentのみ個別にDisallow: /、
それ以外は制限なし。識別可能な独自User-Agentで1秒間隔でアクセスする。

【対象商品について】
実データ確認済み(2026-10-15時点): sitemap.xmlの/product/N形式35件と各カテゴリページの商品を突き合わせ、
コーヒー豆は11銘柄(ブレンド4・シングルオリジン7)。同一銘柄が250g/500g(ピンクブルボンのみ100g/200g)で
別商品として登録されているため、最小重量(250g、ピンクブルボンは100g)を代表として採用する。
除外: ドリップバッグ(バラ売り各種・7個セット・詰め合わせ)、WEB限定の飲み比べセット(NOMIKURABE)、500g/200gの大容量側。
商品名の重量表記を除いた名前・重量・焙煎度は下のITEMSに明示する(焙煎度は店舗の「焙煎度合いから選ぶ」
カテゴリ(浅煎り=product-group/14、中煎り=15、深煎り=16)と商品説明の表記による。
グアテマラ ラ グロリアのみ商品説明に「中深煎り」と明記されているため中深煎りとした)。
価格(OGPのproduct:price:amount、税込)・在庫表示(在庫あり/在庫なし)・商品説明は商品ページから取得する。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "栗栗珈琲",
    "url": "https://www.kurikuricoffee.jp/",
    "platform": "おちゃのこネット(Ocnk)",
    "address": "島根県益田市あけぼの西町8-6",
    "prefecture": "島根県",
    "robots_txt_status": "実質許可(2026-10-15確認。GPTBot等AI系ボットのみ個別にDisallow: /、それ以外は制限なし)",
}

BASE_URL = "https://www.kurikuricoffee.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 1

# (商品ID, 商品名(重量表記を除く), 重量(g), ブレンドか, 焙煎度)
ITEMS = [
    ("2", "栗栗ブレンド（クリクリブレンド）", 250, True, "中煎り"),
    ("6", "コニーズブレンド", 250, True, "浅煎り"),
    ("26", "ボスコブレンド", 250, True, "深煎り"),
    ("202", "ダークローストブレンド", 250, True, "深煎り"),
    ("142", "コロンビア カルロス・ヘルナン ピンクブルボン ナチュラル", 100, False, "浅煎り"),
    ("169", "エチオピア イルガチェフ イディド トゥルセ ウォッシュト", 250, False, "浅煎り"),
    ("311", "甘味のモカ!! エチオピア イルガチェフ ゲデブ ゴチチ ナチュラル", 250, False, "浅煎り"),
    ("208", "ブラジル シティオダトーレ", 250, False, "中煎り"),
    ("273", "グアテマラ ラ グロリア", 250, False, "中深煎り"),
    ("331", "コロンビア ウィラ ティマコAA", 250, False, "中煎り"),
    ("271", "ケニア キアンブ タトゥAA ダークロースト", 250, False, "深煎り"),
]

DETAIL_PATTERN = re.compile(r"商品詳細(.*?)(?:他の写真|関連商品|ログイン 新規登録)")


def fetch_soup(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def build_record(item_id: str, name: str, weight_g: int, is_blend: bool, roast_level: str | None) -> dict | None:
    url = f"{BASE_URL}/product/{item_id}"
    soup = fetch_soup(url)
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))

    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None
    stock_el = soup.select_one(".detail_block_stock")
    stock_text = stock_el.get_text(" ", strip=True) if stock_el else ""
    sold_out = ("在庫なし" in stock_text) or ("カートに入れる" not in text)
    m = DETAIL_PATTERN.search(text)
    desc = m.group(1).strip()[:400] if m else None

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["processing_method"] = None
        parsed["grade"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item_id, name, weight_g, is_blend, roast_level in ITEMS:
        time.sleep(CRAWL_DELAY_SECONDS)
        try:
            record = build_record(item_id, name, weight_g, is_blend, roast_level)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: product/{item_id} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_kurikuricoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kurikuricoffee.json に出力しました")


if __name__ == "__main__":
    main()
