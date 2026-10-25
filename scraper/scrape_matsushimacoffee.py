# -*- coding: utf-8 -*-
"""
scrape_matsushimacoffee.py

松島珈琲(https://matsushimacoffe.shop-pro.jp/、愛知県名古屋市千種区高見2-11-2 シンワビル1階)の
商品情報を取得する。カラーミーショップ(EUC-JP)。公式サイトは http://matucafe.com/。

【店舗発見の経緯】
愛知県の未登録店発掘(disc3)で発見。公式トップに「自家焙煎 コーヒー豆 の販売及び喫茶のコーヒー専門店です」
「直火式焙煎機を使用し」の記載、食べログ(池下駅)にも掲載。

【対象商品について】
実データ確認済み(2026-10時点): カテゴリ「アフリカ」(4)・「アジア」(1)・「中南米」(3)・
「ブレンドコーヒー」(5)の計13商品(単品種8・ブレンド5。カフェインレス メキシコ1を含む)すべて200g。
商品名・分類・焙煎度は商品ページのパンくず(例「深煎り フレンチロースト」)を元に下のITEMSに明示している。
価格は税込、在庫は「カートに入れる」ボタンの有無で判定する。

【robots.txtについて】
User-agent: * は /secure/ と /cart/ のみ制限(2026-10確認)。識別可能な独自User-Agentを使用する。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "松島珈琲",
    "url": "https://matsushimacoffe.shop-pro.jp/",
    "platform": "カラーミーショップ",
    "address": "愛知県名古屋市千種区高見2-11-2 シンワビル1階",
    "prefecture": "愛知県",
    "robots_txt_status": "許可(2026-10確認。/secure/と/cart/以外は制限なし)",
    "source_note": "カラーミー各カテゴリ(アフリカ・アジア・中南米・ブレンドコーヒー)と商品ページを2026-10-21に確認。住所は特商法表示(?mode=sk)と公式 http://matucafe.com/ で一致、自家焙煎は公式トップ(「自家焙煎 コーヒー豆の販売及び喫茶」「直火式焙煎機」)。公式トップに2026-10-13の臨時休業告知",
    "last_verified_at": "2026-10-21",
}

BASE_URL = "https://matsushimacoffe.shop-pro.jp/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 2
WEIGHT_G = 200

# (商品ID, 表示名, 分類の上書き(Noneなら自動判定), 焙煎度)
ITEMS = [
    ("190768443", "エチオピアナチュラル イルガチェフェ・ウォテ 深煎り", None, "深煎り(フレンチロースト)"),
    ("190768915", "エチオピアナチュラル イルガチェフェ・ウォテ やや浅煎り", None, "やや浅煎り(ハイロースト)"),
    ("190768932", "エチオピアウオッシュト ウオテ 中煎り", None, "中煎り(シティロースト)"),
    ("192219538", "ケニア ギチャサイニファクトリー 中深煎り", None, "中深煎り(フルシティロースト)"),
    ("190768381", "インドネシアマンデリン オナンガンジャン 中深煎り", None, "中深煎り(フルシティロースト)"),
    ("190768308", "グアテマラ エチェベリア家 深深煎り", None, "深深煎り(イタリアンロースト)"),
    ("190768334", "カフェインレス メキシコ サン・フェルナンド 中煎り", None, "中煎り(シティロースト)"),
    ("191337903", "コスタリカ モンテス・デ・オロ 中煎り", None, "中煎り(シティロースト)"),
    ("190767945", "赤ブレンド", "ブレンド", None),
    ("190768029", "松島ブレンド", "ブレンド", None),
    ("190768041", "プレミアムブレンド", "ブレンド", None),
    ("190768051", "青ブレンド", "ブレンド", None),
    ("190768055", "黄ブレンド", "ブレンド", None),
]

COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.DOTALL)


def fetch_page(pid: str):
    resp = requests.get(f"{BASE_URL}?pid={pid}", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    text = resp.content.decode("euc-jp", errors="replace")
    soup = BeautifulSoup(text, "html.parser")
    m = COLORME_JSON_PATTERN.search(text)
    product = json.loads(m.group(1)).get("product", {}) if m else {}
    return soup, product


def extract_desc(soup: BeautifulSoup) -> str | None:
    text = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", soup.get_text(" ", strip=True)))
    m = re.search(r"DETAIL\s*(.*?)\s*※粉をご希望", text)
    if not m:
        return None
    desc = re.sub(r"#+|\\+|//", "", m.group(1))
    desc = re.sub(r"\s+", " ", desc).strip()
    return desc[:400] or None


def build_record(item) -> dict | None:
    pid, name, category_override, roast = item
    soup, product = fetch_page(pid)
    desc = extract_desc(soup)
    sold_out = "カートに入れる" not in soup.get_text(" ", strip=True)

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if category_override:
        parsed["category"] = category_override
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
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
        "roast_level": roast,
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": product.get("sales_price_including_tax"),
        "weight_g": WEIGHT_G,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}?pid={pid}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in ITEMS:
        try:
            record = build_record(item)
        except (requests.RequestException, ValueError) as e:
            print(f"[warn] 詳細ページ取得失敗: pid={item[0]} ({e})")
            continue
        if record is not None:
            records.append(record)
        time.sleep(CRAWL_DELAY_SECONDS)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_matsushimacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_matsushimacoffee.json に出力しました")


if __name__ == "__main__":
    main()
