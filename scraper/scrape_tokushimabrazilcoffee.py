# -*- coding: utf-8 -*-
"""
scrape_tokushimabrazilcoffee.py

徳島ブラジルコーヒ(有限会社徳島ブラジルコーヒ店、brazil-coffee.jp、公式サイト brazil-coffee.co.jp、
徳島県徳島市東沖洲2-26-12)の商品情報を取得する。ShopServe(店舗単独のShopServeサイト)。

【店舗の特殊性について】
実データ確認済み(2026-10-15): 店舗サイト下部の「ご連絡先」に「ショップ名:徳島ブラジルコーヒ店 / 所在地
〒770-0873 徳島県徳島市東沖洲2-26-12」とある。登録済みのNOVOLD COFFEE ROASTERSと同一事業者・同一
住所だが、別サイト・別商品構成のため別店舗として扱う。

【対象商品について】
実データ確認済み(2026-10-15): カテゴリ「コーヒー豆」(/SHOP/60561/list.html、全30件、3ページ)は
同一銘柄が200g/500gで別商品として並ぶ(200gのみの銘柄: サントス・デカフェ)。最小重量の200gを
代表とする16商品(ストレート8・ブレンド7・デカフェ1)。500g、アイスコーヒー(液体1L)、ギフト、ドリップバッグ、
コーヒー関連商品は対象外。「挽き方」の選択肢は同一商品。価格は税込。
商品名はh2の表記(キャッチコピー・重量・【】を除く)を明示している。焙煎度は商品情報欄の「焙煎度(合い)」
表記を読む(サントスのみ記載が無くnull)。

【robots.txtについて】
実データ確認済み(2026-10-15): robots.txt は404(制限の記載なし)。商品ページ・カテゴリページのみ使用。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import (parse_product, apply_category_hint_fallback, detect_country_name,
                           normalize_processing_method)

SHOP_INFO = {
    "name": "徳島ブラジルコーヒ",
    "url": "https://www.brazil-coffee.jp/",
    "platform": "ShopServe",
    "address": "徳島県徳島市東沖洲2-26-12",
    "prefecture": "徳島県",
    "robots_txt_status": "制限なし(2026-10-15確認。robots.txtは404)",
}

BASE_URL = "https://www.brazil-coffee.jp/SHOP"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 1

# (ページコード, 商品名, 分類の上書き(Noneなら自動判定), 産地(国名。Noneなら商品名から判定), 焙煎度の補完(欄が無い場合))
ITEMS = [
    ("Guatemala_SHB", "グアテマラ エルインヘルト農園", None, "グアテマラ", None),
    ("Cafe_Queen", "カフェクィーン", "ブレンド", None, None),
    ("Royal_Blend", "ロイヤルブレンド", "ブレンド", None, None),
    ("Special_Blend", "スペシャルブレンド", "ブレンド", None, None),
    ("Brazil_Santos", "サントス ナチュラル", None, "ブラジル", None),
    ("Colombia_Supremo", "コロンビア エスペシャル", None, "コロンビア", None),
    ("European_Blend", "ヨーロピアンブレンド", "ブレンド", None, None),
    ("Italian_Blend", "イタリアンブレンド", "ブレンド", None, None),
    ("American_Blend", "アメリカンブレンド", "ブレンド", None, None),
    ("Indonesia_Mandheling", "マンデリン リントンスペシャル", None, "インドネシア", None),
    ("Tanzania_Mondul_AA", "キリマンジャロ モンデュール農園", None, "タンザニア", None),
    ("Iced_Coffee", "アイスコーヒー", "ブレンド", None, None),
    ("Jamaica_Blue_Mountain", "ブルーマウンテンNO.1", None, "ジャマイカ", None),
    ("Blue_Mountain_Blend", "ブルーマウンテンブレンド", "ブレンド", None, None),
    ("De_Cafe", "カフェインレスコーヒー(デカフェ)", "デカフェ", None, None),
    ("Nagomi", "和み", "ブレンド", None, None),
]

PRICE_PATTERN = re.compile(r'class="price no2"[^>]*>\s*([\d,]+)円')
STOCK_PATTERN = re.compile(r"var stockInfo = '([^']*)'")
ROAST_PATTERN = re.compile(r"焙煎度(?:合い)?\s*[:：]?\s*[\[【]([^\]】/\s]+)")
PROCESS_PATTERN = re.compile(r"精製方法\s*[:：]\s*[\[【]([^\]】]+)[\]】]")
ROAST_NORMALIZE = {"極深煎り": "深煎り"}


def fetch_page(code: str) -> str:
    resp = requests.get(f"{BASE_URL}/{code}_200g.html", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.content.decode("utf-8")


def extract_description(soup: BeautifulSoup) -> str | None:
    """商品説明の冒頭(見出しの重複行を除いた最初の数段落)を返す。"""
    main = soup.select_one("div.mainCont")
    if not main:
        return None
    lines = []
    for line in main.get_text("\n", strip=True).split("\n"):
        if line in lines:
            continue
        if line.startswith(("商品情報", "商品名:", "関連キーワード", "拡大表示")):
            break
        lines.append(line)
    text = re.sub(r"\s+", " ", " ".join(lines)).strip()
    return text[:400] or None


def build_record(code, name, category_override, origin, roast_fallback) -> dict | None:
    text = fetch_page(code)
    soup = BeautifulSoup(text, "html.parser")
    price_m = PRICE_PATTERN.search(text)
    stock_m = STOCK_PATTERN.search(text)
    in_stock = bool(stock_m) and stock_m.group(1) == "在庫あり"

    plain = soup.get_text("\n", strip=True)
    roast_m = ROAST_PATTERN.search(plain)
    roast = roast_m.group(1) if roast_m else roast_fallback
    roast = ROAST_NORMALIZE.get(roast, roast)
    process_m = PROCESS_PATTERN.search(plain)

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if category_override:
        parsed["category"] = category_override
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = origin or detect_country_name(name)
        if detected:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
    processing = parsed["processing_method"]
    if process_m:
        processing = normalize_processing_method(process_m.group(1).replace("式", "")) or processing

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": roast or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": extract_description(soup),
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price_m.group(1).replace(",", "")) if price_m else None,
        "weight_g": 200,
        "stock_status": "販売中" if in_stock else "完売",
        "out_of_stock": not in_stock,
        "product_url": f"{BASE_URL}/{code}_200g.html",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for code, name, category_override, origin, roast_fallback in ITEMS:
        try:
            record = build_record(code, name, category_override, origin, roast_fallback)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {code} ({e})")
            continue
        if record is not None:
            records.append(record)
        time.sleep(CRAWL_DELAY_SECONDS)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_tokushimabrazilcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_tokushimabrazilcoffee.json に出力しました")


if __name__ == "__main__":
    main()
