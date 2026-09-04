# -*- coding: utf-8 -*-
"""
scrape_cotoricoffee.py

自家焙煎珈琲コトリ(shop.cotoricoffee.jp、栃木県那須塩原市井口1181-3、
自家焙煎豆のオンライン販売)の商品情報を取得する。カラーミーショップ。

robots.txt確認済み(2026-09時点): 他のカラーミー店舗と同一の記述。
User-agent: *に対し/secure/・/cart/のみDisallow。AhrefsBot等一部
ボットを個別にDisallow: /、それ以外は制限なし。

【商品名の構造について】
実データ確認済み: 商品名(product.name)が"産地/ブレンド名</br>説明文
</br>焙煎度"の3セグメントを"</br>"で連結した1つの文字列になっている
(例: "インドネシア</br>マンデリン　トバコ</br>深煎り")。焙煎度が
商品名本体に含まれないためcoffee_parser側で焙煎度を検出できるよう、
3セグメントを半角スペースで連結してraw_nameとする。

【非コーヒー豆商品の除外について】
実データ確認済み: 全33件のうち「マイニチアイス」(麦茶式水出しパック、
液体抽出用の個包装)・「コトリさん」(テトラバッグ入りの個包装)・
「マイニチタンブラー」(タンブラーとのセット商品)・ドリップバッグ・
HARIO用ペーパーフィルター・コーヒーゼリー・八菓市庭縁いせとうさんの
クッキーがコーヒー豆単品ではないためNON_BEAN_KEYWORDSで除外する。
商品名が空の削除済みプレースホルダーレコードも除外する。

【</br>(閉じタグ形式の誤ったbrタグ)について】
実データ確認済み(初回実行で発覚): この店のColorme JSONに埋め込まれた
product.nameは、他店で一般的な"<br>"/"<br/>"/"<br />"ではなく、HTML的には
誤りである閉じタグ形式"</br>"でセグメントを区切っている。当初
`<br\s*/?>`という開きタグのみにマッチする正規表現でsplitしていたため
1件も分割されず、"インドネシア</br>マンデリン　トバコ</br>深煎り"のように
"</br>"がそのままraw_nameに残ってしまっていた(NON_BEAN_KEYWORDSに
よる除外判定はキーワードが単純な部分文字列一致のため実害は無かった)。
`</?br\s*/?>`に変更し、開き・閉じ両方の表記に対応した。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "自家焙煎珈琲コトリ",
    "url": "https://shop.cotoricoffee.jp/",
    "platform": "カラーミーショップ",
    "address": "栃木県那須塩原市井口1181-3",
    "prefecture": "栃木県",
    "robots_txt_status": "実質許可(2026-09確認。他のカラーミー店舗と同一の記述。"
                          "/secure/・/cart/のみDisallow。AhrefsBot等一部ボットを"
                          "個別にDisallow: /、それ以外は制限なし)",
}

BASE_URL = "https://shop.cotoricoffee.jp"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "マイニチアイス", "コトリさん", "マイニチタンブラー", "ドリップバッグ",
    "ペーパーフィルター", "コーヒーゼリー", "クッキー",
]
COLORME_PATTERN = re.compile(r"var Colorme\s*=\s*(\{.*?\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_pid_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "pid=" in loc.get_text()]


def build_record(soup: BeautifulSoup, product_url: str) -> dict | None:
    script_text = ""
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        if "var Colorme" in text:
            script_text = text
            break

    m = COLORME_PATTERN.search(script_text)
    if not m:
        return None
    data = json.loads(m.group(1))
    product = data.get("product") or {}
    raw = product.get("name") or ""
    segments = [s.strip() for s in re.split(r"</?br\s*/?>", raw) if s.strip()]
    title = " ".join(segments)
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)
    price = product.get("sales_price_including_tax") or product.get("sales_price")

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": int(price) if price is not None else None,
            "product_url": product_url,
        }

    structural_out_of_stock = product.get("stock_num") == 0
    stock_status = detect_stock_status(title, structural_out_of_stock)
    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None

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
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price) if price is not None else None,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_pid_urls()

    records = []
    flavored_records = []
    for product_url in product_urls:
        try:
            detail = build_record(fetch_page(product_url), product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


if __name__ == "__main__":
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_cotoricoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_cotoricoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
