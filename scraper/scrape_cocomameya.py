# -*- coding: utf-8 -*-
"""
scrape_cocomameya.py

珈々豆屋(CoCoMAMEYA、有限会社珈々豆屋、北海道旭川市末広東1条4丁目8番30号)の
Yahoo!ショッピング店(store.shopping.yahoo.co.jp/cocomameyashop)の商品情報を取得する。

【販売先について】
公式サイト cocomameya.jp はWordPressの会社紹介サイトでショップ機能が無い。楽天市場への出店は無し。
Yahoo!ショッピング店の「珈琲豆」カテゴリ(e0dde0eac6、23点)が唯一の通販先。

【対象商品について】
カテゴリ23点のうち、同一銘柄を複数パックにした「自家焙煎の豆単品」だけを対象にする(100g単品の設定は無く、
最小重量は100g×3パック=300g。コスタリカ・グアテマラは300g袋)。
 - 採用8件: 大雪山ブレンド/リッチブレンド/ヨーロピアンブレンド/マイルドブレンド(各100g×3pk)、
   ブラジル ファゼンダ ジュリアナ(100g×3pk)、ペルー マチュピチュ天空(100g×3pk)、
   コスタリカ ジャガーハニー(300g)、グアテマラ アンティグア アルコイリス農園(300g)。
 - 同一銘柄の大容量(5パック=500g、500g×4=2kg)は最小重量でないため除外。
 - 除外: ギフト(アロマパック/缶入り)、複数銘柄の詰め合わせ(ブレンド3種セット、セレクト3pk/5pk/4種、
   選べるスペシャルティ3パック)。
商品ごとの `item.stock.isAvailable` で在庫を判定する。
"""

import html
import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "珈々豆屋",
    "url": "https://store.shopping.yahoo.co.jp/cocomameyashop/",
    "platform": "Yahoo!ショッピング",
    "address": "北海道旭川市末広東1条4丁目8番30号",
    "prefecture": "北海道",
    "robots_txt_status": "実質許可とみなす(2026-10確認。store.shopping.yahoo.co.jpのrobots.txtは検索系パラメータ・レビュー等のみ禁止。商品ページと /xxxx.html のカテゴリページのみ使用)",
    "source_note": "Yahoo!ショッピング店(https://store.shopping.yahoo.co.jp/cocomameyashop/)のカテゴリ「珈琲豆」と各商品ページを2026-10-20に確認。"
                   "公式(https://www.cocomameya.jp/)に「自家焙煎珈琲」「少ロットからの対応」、グーペの店舗ページ(https://r.goope.jp/sr-01-0120450010/)に住所・営業時間・「珈琲豆販売コーナー」の記載。"
                   "商品はいずれも100g×3パック以上の複数パック販売(単品100gの設定なし)",
    "last_verified_at": "2026-10-20",
}

BASE = "https://store.shopping.yahoo.co.jp/cocomameyashop/"
HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
INTERVAL = 3
NEXT_DATA = re.compile(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)

# (商品コード, 登録名, 重量g, ブレンドか, 産地, 焙煎度, 焙煎度の原文)
ITEMS = [
    ("taisetsuzanblend300g", "大雪山ブレンド 100g×3パック", 300, True, None, "フルシティロースト", "フルシティ〜フレンチロースト"),
    ("richblend3pack", "リッチブレンド 100g×3パック", 300, True, None, "シティロースト", "シティロースト(ミックス焙煎)"),
    ("europeanblend3pack", "ヨーロピアンブレンド 100g×3パック", 300, True, None, "シティロースト", "シティロースト"),
    ("mildblend3pack", "マイルドブレンド 100g×3パック", 300, True, None, "ミディアムロースト", "ミディアムロースト"),
    ("braziljuliana300g", "ブラジル ファゼンダ ジュリアナ 100g×3パック", 300, False, "ブラジル", "シティロースト", "シティロースト"),
    ("perumachupichu300g", "ペルー マチュピチュ天空 100g×3パック", 300, False, "ペルー", "ハイロースト", "ハイロースト〜シティロースト"),
    ("costarica300g", "コスタリカ ジャガーハニー 300g", 300, False, "コスタリカ", "シティロースト", "シティロースト"),
    ("guatemalaq300", "グアテマラ アンティグア アルコイリス農園 300g", 300, False, "グアテマラ", None, None),
]


def text_of(v) -> str:
    s = html.unescape(str(v or "")).replace("<br>", "\n").replace("<br />", "\n")
    return BeautifulSoup(s, "html.parser").get_text("\n", strip=True)


def fetch_item(code: str) -> dict | None:
    url = f"{BASE}{code}.html"
    resp = None
    for attempt in range(3):
        resp = requests.get(url, headers=HEADERS, timeout=60)
        if resp.status_code not in (429, 500, 502, 503, 504):
            break
        time.sleep(10 * (attempt + 1))
    if resp.status_code != 200:
        print(f"[warn] 取得失敗 {code} HTTP {resp.status_code}")
        return None
    m = NEXT_DATA.search(resp.content.decode("utf-8"))
    if not m:
        print(f"[warn] __NEXT_DATA__ 無し {code}")
        return None
    return json.loads(m.group(1))["props"]["pageProps"].get("item")


def build_record(code, name, weight, blend, origin, roast, roast_hint, item) -> dict:
    parsed = parse_product(name)
    if blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed = apply_category_hint_fallback(parsed, name)
        parsed["category"] = "ストレート"
        parsed["origin_country"] = origin
        parsed["origin_source"] = "raw_name"
    info = text_of(item.get("information"))
    # タグ列挙行(「珈琲豆 コーヒー 自家焙煎珈琲 ...」)以降は説明から落とす
    info = re.split(r"\n(?:珈琲豆|コーヒー豆)\s", info)[0]
    info = re.sub(r"\s+", " ", info).strip() or None
    stock = item.get("stock") or {}
    available = bool(stock.get("isAvailable", True))
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast or parsed["roast_level"],
        "roast_hint": roast_hint,
        "flavor_notes": info,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(item["applicablePrice"]),
        "weight_g": weight,
        "stock_status": "販売中" if available else "完売",
        "out_of_stock": not available,
        "product_url": f"{BASE}{code}.html",
    }


def scrape_all_products() -> list:
    records = []
    for i, (code, *rest) in enumerate(ITEMS):
        if i:
            time.sleep(INTERVAL)
        item = fetch_item(code)
        if item:
            records.append(build_record(code, *rest, item))
    return records


def main():
    records = scrape_all_products()
    with open("data_cocomameya.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_cocomameya.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], "|", r["category"], r["origin_country"], r["roast_level"], r["price"], r["weight_g"], r["stock_status"])


if __name__ == "__main__":
    main()
