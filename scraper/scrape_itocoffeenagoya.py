# -*- coding: utf-8 -*-
"""
scrape_itocoffeenagoya.py

イトウコーヒー(株式会社イトウ珈琲商会 / イトウコーヒー本店、https://shop-ito-coffee.com/、
愛知県名古屋市東区泉1-7-25)の商品情報を取得する。カラーミーショップ(EUC-JP)。
(scrape_itoucoffee.py は大口町の別店「伊藤珈琲豆販売所」のため、slugを分けた。)

【店舗発見の経緯】
愛知県の未登録店発掘(disc3)で発見。公式 https://ito-coffee.com/ に「約70年もの間、名古屋でロースターとして
活動」、直営ショップ案内(https://ito-coffee.com/05_shopinfo.html)に「イトウコーヒー本店 直営ショップ」。

【対象商品について】
実データ確認済み(2026-10時点): 「コーヒーを探す」カテゴリ(cbid=1840805)71商品のうち、コーヒー豆の
200g商品29点(ストレート・ブレンド・デカフェ)を対象とする。同一銘柄に500g商品があるものは小さい200gを代表とする。
除外: ドリップバッグ(単品・100個入り)、アイス珈琲ボトル、インスタント、パウダーコーヒー、エマージェンシーコーヒー、
カフェオレベース、水出しアイス珈琲(バッグ)、おつまみ、500g商品。「夏季限定/キリマンブレンドアイス珈琲」と
「<期間限定>インドネシア マンデリン ミトラ」は豆の商品のため含める。
選択肢は「豆/粉」で、豆の価格を採用する。商品名・分類は商品ページのパンくず(ストレート/ブレンドコーヒー)を元に
ITEMSに明示している。焙煎度は商品名が焙煎度のもの(シティ〜イタリアン)のみ設定する。

【在庫について】
var Colorme のstock_numが0以下、または「カートに入れる」ボタンが無く「売り切れ」表示の商品を品切れとする。

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
    "name": "イトウコーヒー",
    "url": "https://shop-ito-coffee.com/",
    "platform": "カラーミーショップ",
    "address": "愛知県名古屋市東区泉1-7-25",
    "prefecture": "愛知県",
    "robots_txt_status": "許可(2026-10確認。/secure/と/cart/以外は制限なし)",
    "source_note": "カラーミー「コーヒーを探す」カテゴリ(https://shop-ito-coffee.com/?mode=cate&cbid=1840805&csid=0)と各商品ページを2026-10-21に確認。住所は特商法表示(?mode=sk)と直営ショップ案内(https://ito-coffee.com/05_shopinfo.html)、自家焙煎は公式 https://ito-coffee.com/(「約70年もの間、名古屋でロースターとして活動」)。業務用卸が主体の会社",
    "last_verified_at": "2026-10-21",
}

BASE_URL = "https://shop-ito-coffee.com/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
CRAWL_DELAY_SECONDS = 2
WEIGHT_G = 200

# (商品ID, 表示名, 分類(ストレート/ブレンド), 焙煎度(Noneなら商品名から判定せずNone))
ITEMS = [
    ("87308436", "モカ", "ストレート", None),
    ("87307548", "コロンビア", "ストレート", None),
    ("87313292", "ブラジルサントス", "ストレート", None),
    ("87308132", "グァテマラ", "ストレート", None),
    ("87308925", "キリマンジャロ", "ストレート", None),
    ("87308237", "マンデリン", "ストレート", None),
    ("154365248", "カラコール炭焼珈琲", "ストレート", None),
    ("154365049", "カラコール ストレート", "ストレート", None),
    ("82215378", "エチオピア イルガチェフェ G2 ウォッシュド", "ストレート", None),
    ("191854877", "ブラジル ショコラ ナチュラル", "ストレート", None),
    ("191856561", "グァテマラ ステイゴールド", "ストレート", None),
    ("137440629", "タンザニア AA リマ KIBO", "ストレート", None),
    ("191883224", "ケニア マサイ AA", "ストレート", None),
    ("193602993", "<期間限定> インドネシア マンデリン ミトラ", "ストレート", None),
    ("137440577", "インドネシア マンデリン ウルトラ", "ストレート", None),
    ("137440606", "デカフェ コロンビア", "ストレート", None),
    ("87312118", "アメリカン", "ブレンド", None),
    ("87305648", "シティ", "ブレンド", "シティロースト"),
    ("87305522", "ハイシティ", "ブレンド", "ハイシティロースト"),
    ("87305802", "フルシティ", "ブレンド", "フルシティロースト"),
    ("87305707", "フレンチ", "ブレンド", "フレンチロースト"),
    ("87305919", "イタリアン", "ブレンド", "イタリアンロースト"),
    ("148949300", "いずみブレンド", "ブレンド", None),
    ("111582969", "ブルーマウンテンブレンド", "ブレンド", None),
    ("87307106", "モカブレンド", "ブレンド", None),
    ("154364483", "カラコールブレンド", "ブレンド", None),
    ("87355697", "なごやブレンド", "ブレンド", None),
    ("87356456", "白壁ブレンド", "ブレンド", None),
    ("117985386", "夏季限定/キリマンブレンドアイス珈琲", "ブレンド", None),
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
        if (v.get("option1_value") or "").strip() == "豆":
            return v.get("option_price_including_tax")
    return product.get("sales_price_including_tax")


def extract_tagline(soup: BeautifulSoup, name: str) -> str | None:
    """商品名・重量の直後から価格表記の手前までのキャッチコピーを返す(無ければNone)。"""
    text = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", soup.get_text(" ", strip=True)))
    m = re.search(r"ショッピングを続ける ショッピングを続ける (.*?) [\d,]+円\(内税\)", text)
    if not m:
        return None
    seg = m.group(1)
    norm = unicodedata.normalize("NFKC", name)
    seg = re.sub(r"^.*?200\s*g\s*", "", seg).strip() if "200" in seg else seg
    return seg[:300] or None


def build_record(item) -> dict | None:
    pid, name, category, roast = item
    soup, product = fetch_page(pid)
    text = soup.get_text(" ", strip=True)
    stock = product.get("stock_num")
    sold_out = (isinstance(stock, int) and stock <= 0) or "カートに入れる" not in text

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    parsed["category"] = category
    if category == "ブレンド":
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
        "flavor_notes": extract_tagline(soup, name),
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
    with open("data_itocoffeenagoya.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_itocoffeenagoya.json に出力しました")


if __name__ == "__main__":
    main()
