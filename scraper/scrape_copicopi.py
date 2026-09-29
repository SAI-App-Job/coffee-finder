# -*- coding: utf-8 -*-
"""
scrape_copicopi.py

自家焙煎珈琲 copicopi(copicopi.cart.fc2.com、群馬県館林市新宿1丁目
3-7)の商品情報を取得する。FC2ショッピングカート。

【店舗発見の経緯】
全国再調査(群馬県)で2026-09-05の別セッションで技術的理由(レガシーな
FC2ベースのカートで構造が脆弱、安定したスクレイピングが困難)により
見送られていたが、本セッションで梶山珈琲(栃木県)等での実装実績から
個別商品ページを番号ごとにfetchする手法が有効と確認し、実装候補に
復帰させた。

【対象商品について】
実データ確認済み(2026-09時点): 全56商品のうち、「かんたん便利！
ドリップパック」(ca5、4件)・「かんたん時短！水だしコーヒーパック」
(ca10、2件、いずれも挽いた粉の個包装形式)を除いた豆売り商品50件は、
各銘柄ごとに「《豆》通常焙煎」「《粉》通常焙煎」「《豆》深め焙煎」
「《粉》深め焙煎」の4バリアントが個別商品ページとして存在する構造
だったため、豆(粉ではなく)の2焙煎度(通常・深め焙煎、両方とも独立した
商品として販売継続中)のみに絞り、13銘柄・25商品(ブレンド1×2焙煎+
ストレート12銘柄、うち1銘柄は焙煎バリエーションが無く1商品のみ)を
対象とする。

【ページ構造について】
実データ確認済み: 他店で見られるカラーミーショップの`var Colorme = {...}`
JSON形式のデータブロックが存在しない、更に古いテーマを使用している。
価格は`span.importantmessage`要素、商品説明は`div.comment`要素から
それぞれ個別に抽出する(価格ラベル直後にHTMLタグが挟まる構造のため、
単純な正規表現では価格を取得できず、また商品ページ内にはコメント
アウトされた過去の価格表記も残存しているため、専用のCSSセレクタで
確実に対象要素のみを取得する必要がある)。重量は商品名に「200g」と
明記されているためそのまま採用する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, normalize_processing_method

SHOP_INFO = {
    "name": "自家焙煎珈琲 copicopi",
    "url": "http://copicopi.crayonsite.info/",
    "platform": "FC2ショッピングカート(cart.fc2.com)",
    "address": "群馬県館林市新宿1丁目3-7",
    "prefecture": "群馬県",
    "robots_txt_status": "未確認",
}

BASE_URL = "http://copicopi.cart.fc2.com"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}

# (item_id, category_prefix) — ドリップパック(ca5)・水だしコーヒーパック(ca10)、
# および《粉》バリアント(《豆》と重複する銘柄のみ)は除外済み
ITEM_PATHS = [
    ("ca1", "46"), ("ca1", "48"),                      # コピコピブレンド(通常/深め焙煎)
    ("ca3", "54"), ("ca3", "56"),                       # グアテマラ アンティグア サン・セバスチャン農園
    ("ca3", "71"), ("ca3", "59"),                       # ブラジル セラード・ブルボン
    ("ca3", "170"), ("ca3", "172"),                     # インドネシア トラジャ・ラマン
    ("ca6", "76"),                                      # インドネシア ランテカルア・トラジャ(焙煎バリエーション無し)
    ("ca6", "132"), ("ca6", "134"),                     # ミャンマー ジーニアス・シャン
    ("ca6", "140"), ("ca6", "142"),                     # パプアニューギニア クムル・マウンテン
    ("ca6", "166"), ("ca6", "168"),                     # インドネシア リントン・マンデリン
    ("ca8", "80"), ("ca8", "82"),                       # グアテマラ ウエウエテナンゴ
    ("ca7", "84"), ("ca7", "86"),                       # タンザニア スノートップ
    ("ca4", "136"), ("ca4", "138"),                     # エチオピア モカ・コチャレ G1
    ("ca4", "158"), ("ca4", "160"),                     # エチオピア イルガチェフ・WOTE
    ("ca11", "174"), ("ca11", "176"),                   # ブラジル ブルボン・ピーベリー
]

TITLE_PATTERN = re.compile(r"<title>([^<]+?)\s*-\s*自家焙煎珈琲")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def build_record(category: str, item_id: str) -> dict | None:
    url = f"{BASE_URL}/{category}/{item_id}/p-r-s/"
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.encoding = "utf-8"
    html_text = resp.text

    title_m = TITLE_PATTERN.search(html_text)
    if not title_m:
        return None
    title = title_m.group(1).strip()

    soup = BeautifulSoup(html_text, "html.parser")

    comment_div = soup.find("div", class_="comment")
    desc = comment_div.get_text(" ", strip=True)[:500] if comment_div else None

    price_span = soup.find("span", class_="importantmessage")
    price = int(re.sub(r"[^\d]", "", price_span.get_text())) if price_span else None

    weight_m = WEIGHT_PATTERN.search(title) or (WEIGHT_PATTERN.search(desc) if desc else None)
    weight_g = int(weight_m.group(1)) if weight_m else 100

    parsed = parse_product(title)
    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": url,
        }

    if parsed["category"] != "ブレンド":
        detected = detect_country_name(title) or (detect_country_name(desc) if desc else None)
        if detected:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name" if detect_country_name(title) else "product_description"
        parsed = apply_category_hint_fallback(parsed, title)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": "販売中",
        "out_of_stock": False,
        "product_url": url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    records = []
    flavored_records = []
    for category, item_id in ITEM_PATHS:
        try:
            detail = build_record(category, item_id)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {category}/{item_id} ({e})")
            continue
        if detail is None:
            continue
        (flavored_records if detail.get("is_flavored") else records).append(detail)
    return records, flavored_records


def main():
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_copicopi.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_copicopi.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
