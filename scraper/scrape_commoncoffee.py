# -*- coding: utf-8 -*-
"""
scrape_commoncoffee.py

珈琲豆ストア コモン(https://common.shop-pro.jp/、愛知県名古屋市名東区富が丘69)の商品情報を取得する。
カラーミーショップ(EUC-JP)。公式サイトは https://www.common-coffee.com/。

【店舗発見の経緯】
愛知県の未登録店発掘(disc3)で発見。公式 about.html に「名古屋 藤ヶ丘にあるコーヒーロースターです」、
beans.html に「30年来の相棒であるFUJI ROYALをつかって」、店舗情報(map.html)あり。

【対象商品について】
実データ確認済み(2026-10時点): 珈琲豆カテゴリ(cbid=2576203)の17商品のうち、
「【冬季限定】バターフレイバー」(香料付きフレーバーコーヒー)を除く16商品(ブレンド6・デカフェ2・
シングルオリジン8)を対象とする。オンラインストアは「コーヒー豆1袋200gごと」の注文で、
全商品200g。挽き目は「豆のまま」の価格(挽き目で価格差なし)。価格は税込。
商品名・分類・産地は下のITEMSに明示している。焙煎度は商品ページに記載がないためNone。
産地・精製は商品ページの「原産国」「生産処理」から取得する。

【在庫について】
var Colorme のstock_numが0以下、または「add to cart」ボタンが無い商品を品切れとする。

【robots.txtについて】
User-agent: * は /secure/ と /cart/ のみ制限(2026-10確認)。識別可能な独自User-Agentを使用する。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method

SHOP_INFO = {
    "name": "珈琲豆ストア コモン",
    "url": "https://common.shop-pro.jp/",
    "platform": "カラーミーショップ",
    "address": "愛知県名古屋市名東区富が丘69",
    "prefecture": "愛知県",
    "robots_txt_status": "許可(2026-10確認。/secure/と/cart/以外は制限なし)",
    "source_note": "珈琲豆カテゴリ(https://common.shop-pro.jp/?mode=cate&cbid=2576203&csid=0)と各商品ページを2026-10-21に確認。住所は特商法表示(?mode=sk)と店舗情報(https://www.common-coffee.com/map.html)、自家焙煎は https://www.common-coffee.com/about.html(「名古屋 藤ヶ丘にあるコーヒーロースター」)。ブログに2026-08-07の夏季休業告知",
    "last_verified_at": "2026-10-21",
}

BASE_URL = "https://common.shop-pro.jp/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
CRAWL_DELAY_SECONDS = 2
WEIGHT_G = 200

# (商品ID, 表示名, 分類の上書き(Noneなら自動判定))
ITEMS = [
    ("146781485", "コモンブレンド", "ブレンド"),
    ("173388308", "香流川ブレンド", "ブレンド"),
    ("148313069", "アイスブレンド", "ブレンド"),
    ("148276916", "藤が丘ブレンド", "ブレンド"),
    ("148276986", "フレンチブレンド", "ブレンド"),
    ("148277063", "木曜日ブレンド", "ブレンド"),
    ("169855778", "デカフェ メキシコ チアバス", None),
    ("187467224", "デカフェ エチオピア シダモ", None),
    ("148277117", "ブラジル完熟", None),
    ("187467437", "コロンビア クラシック ウィラ", None),
    ("148277469", "インドネシア マンデリン トバコ", None),
    ("148277537", "イェメン モカマタリ #9", None),
    ("182514925", "タンザニア スノートップ", None),
    ("189367437", "エルサルバドル マラカラ ブルボン", None),
    ("188990257", "エチオピア G-1 シャンタワネ", None),
    ("189868023", "ニカラグア ロス・アルチプラーノス農園 パライネマ ナチュラル", None),
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


def pick_price(product: dict) -> int | None:
    for v in product.get("variants", []):
        if (v.get("option1_value") or "").startswith("豆のまま"):
            return v.get("option_price_including_tax")
    return product.get("sales_price_including_tax")


def extract_sections(soup: BeautifulSoup) -> dict:
    text = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", soup.get_text(" ", strip=True)))
    def section(label):
        m = re.search(rf"■\s*{label}[^■]*?[|｜]?\s*(?:Profile|Country of origin|Country oforigin|Process|Taste)?\s*(.*?)(?=■|内容量、サービス)", text)
        return m.group(1).strip() if m else None
    profile = re.search(r"■\s*商品説明\s*[|｜]?\s*Profile\s*(.*?)\s*■\s*テイスト", text)
    origin = re.search(r"■\s*原産国\s*[|｜]?\s*Country\s*of\s*origin\s*(.*?)\s*(?=■|内容量)", text)
    process = re.search(r"■\s*生産処理\s*[|｜]?\s*Process\s*(.*?)\s*(?=■|内容量)", text)
    return {
        "desc": profile.group(1).strip()[:400] if profile else None,
        "origin_text": origin.group(1).strip() if origin else None,
        "process_text": process.group(1).strip() if process else None,
        "in_cart": "add to cart" in text.lower(),
    }


def build_record(item) -> dict | None:
    pid, name, category_override = item
    soup, product = fetch_page(pid)
    sec = extract_sections(soup)
    stock = product.get("stock_num")
    sold_out = (isinstance(stock, int) and stock <= 0) or not sec["in_cart"]

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
        if not parsed["origin_country"] and sec["origin_text"]:
            c = detect_country_name(sec["origin_text"])
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "description"
    process = parsed["processing_method"]
    if not process and sec["process_text"]:
        process = detect_processing_method(sec["process_text"])

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": process,
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": sec["desc"],
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": pick_price(product),
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
    with open("data_commoncoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_commoncoffee.json に出力しました")


if __name__ == "__main__":
    main()
