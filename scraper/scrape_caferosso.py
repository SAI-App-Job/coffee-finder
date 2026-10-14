# -*- coding: utf-8 -*-
"""
scrape_caferosso.py

CAFE ROSSO Beans Store(https://caferosso.ocnk.net/、島根県安来市門生町4-3)の商品情報を取得する。
おちゃのこネット(Ocnk)クリーンURLテーマ。公式サイトは https://caferosso.net/ 。

【店舗発見の経緯】
全国再調査(島根県)の新規発掘で発見。住所はOcnkの特定商取引法表示ページ(/info)の
「カフェロッソ 門脇 洋之 / 島根県安来市門生町4-3」で番地まで確認済み。

【robots.txt】
確認済み(2026-10-15時点): GPTBot/Bytespider/TikTokSpider/meta-externalagentのみ個別にDisallow: /、
それ以外は制限なし。識別可能な独自User-Agentで1秒間隔でアクセスする。

【対象商品について】
実データ確認済み(2026-10-15時点): sitemap.xmlの/product/N形式87件のうち、コーヒー豆(200g/500gの2規格が
別商品として登録)は19銘柄(ブレンド13・シングルオリジン6)。最小重量の200gを代表として採用する。
除外: ドリップバッグ(各種・セット)、ギフト各種(エスプレッソ/ビーンズ/ドリップバッグ/ミックス/カジュアル/秋のブレンド/
カフェラテベース)、カフェラテベース、飲み比べセット、器具(ミルクピッチャー・ミル・フィルター・ジャグ)、
グッズ(マグ・カップ・シロップ)、500gの大容量側。
各商品ページの商品説明末尾に「原産国」「ロースト(例: シティロースト（中煎り）)」が明記されているため、
焙煎度は括弧内の中煎り/中深煎り/浅煎り/深煎りを採用する。
「ブラジル・モンテアレグレ for ICE / for ESPRESSO」は原産国が「ブラジル ほか」(for ESPRESSOは上質なロブスタを
少量加えると明記)のためブレンドとして扱う。
価格(OGPのproduct:price:amount、税込)・商品説明は商品ページから取得する。在庫切れ表示(SOLD OUT・品切れ・
在庫切れ・入荷待ち)があれば完売とする(2026-10-15時点で対象19件に該当なし)。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "CAFE ROSSO Beans Store",
    "url": "https://caferosso.ocnk.net/",
    "platform": "おちゃのこネット(Ocnk)",
    "address": "島根県安来市門生町4-3",
    "prefecture": "島根県",
    "robots_txt_status": "実質許可(2026-10-15確認。GPTBot等AI系ボットのみ個別にDisallow: /、それ以外は制限なし)",
}

BASE_URL = "https://caferosso.ocnk.net"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 1

# (商品ID, 商品名(重量表記を除く), 重量(g), ブレンドか, 焙煎度)
ITEMS = [
    ("8", "ロッソブレンド -ベーシック-", 200, True, "中煎り"),
    ("109", "ロッソブレンド -ライト-", 200, True, "浅煎り"),
    ("161", "ロッソブレンド -リッチ＆スイート-", 200, True, "中深煎り"),
    ("194", "ロッソブレンド -for ICE-", 200, True, "深煎り"),
    ("10", "エスプレッソブレンド -ベーシック-", 200, True, "中深煎り"),
    ("45", "エスプレッソブレンド -メリディオーネ-", 200, True, "中深煎り"),
    ("121", "エスプレッソブレンド -ラテアート-", 200, True, "中深煎り"),
    ("115", "ドルチェブレンド", 200, True, "深煎り"),
    ("354", "秋のブレンド", 200, True, "中煎り"),
    ("451", "コロンビアとボリビアのブレンド", 200, True, "中煎り"),
    ("487", "ケニアとグァテマラのブレンド", 200, True, "中煎り"),
    ("496", "ブラジル・モンテアレグレ for ICE", 200, True, "深煎り"),
    ("498", "ブラジル・モンテアレグレ for ESPRESSO", 200, True, "中深煎り"),
    ("116", "マンデリン", 200, False, "深煎り"),
    ("156", "エチオピア イルガチェフ ウオッシュド", 200, False, "浅煎り"),
    ("457", "エチオピア イルガチェフ ゲデブ ゴチチ ナチュラル", 200, False, "中煎り"),
    ("182", "ブラジル", 200, False, "中煎り"),
    ("508", "ルワンダ アナエロビック ナチュラル", 200, False, "中煎り"),
    ("514", "ボリビア バレンティン チョケウアンカ", 200, False, "中煎り"),
]

DETAIL_PATTERN = re.compile(r"返品特約に関する重要事項 お問い合わせ(.*?)(?:※ギフト包装はできません。|流行を追うのではなく)")
SOLD_OUT_PATTERN = re.compile(r"SOLD ?OUT|品切れ|在庫切れ|入荷待ち|売り切れ")


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
    sold_out = bool(SOLD_OUT_PATTERN.search(text))
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
    with open("data_caferosso.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_caferosso.json に出力しました")


if __name__ == "__main__":
    main()
