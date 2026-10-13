# -*- coding: utf-8 -*-
"""
scrape_cafejpn.py

日本珈琲社((有)日本珈琲社、cafejpn.co.jp、〒023-0817 岩手県奥州市水沢区宮下町25)の
自家焙煎コーヒー豆の商品情報を取得する。静的HTML(Shift_JIS、Adobe GoLive製)+
ショップメーカー(shopmaker.jp)カートの構成。

【構成について】
実データ確認済み(2026-10-13): 商品一覧ページは /itiran/itiran.html(/itiran.html は404)。
各商品の個別ページが st/stNN/stNN.html(ストレート13件)、bl/blNN/blNN.html
(ブレンド11件)、fr/frNN/frNN.html(深煎り・エスプレッソ・アイス用6件)にあり、
各ページに「100gパック ￥830(税込)」「200gパック」「500gパック」の価格が静的HTMLで
載っている。このスクレイパーは上記30ページを巡回し、最小重量(100g)の価格を採用する。
トップページ(/)のナビゲーションに列挙された商品ページを候補としている。

【除外したもの】
紅茶(tea/)・フレーバーティー(ftea/)・ギフト(gift/)・セット(set/)・ミルク関連(milk/)は
対象外。stNN の一部ページ(st01, st02, st05)には同一ページ内に「深煎り(フレンチロースト)」
版が併記されているが、これは fr01〜fr03(深煎りコロンビア/ブラジル/キリマンジャロ)
と同じ商品であるため、stNN側は通常焙煎版のみを採用し深煎り版は fr 側で収録する。

【在庫】
在庫状況の表示が無いため販売中として扱う。

robots.txt: 2026-10-13時点でサイトにrobots.txtは見当たらない(制限なし扱い)。
"""

import json
import re
import time

import requests

from coffee_parser import parse_product

SHOP_INFO = {
    "name": "日本珈琲社",
    "url": "https://www.cafejpn.co.jp/",
    "platform": "静的HTML+ショップメーカーカート",
    "address": "岩手県奥州市水沢区宮下町25",
    "prefecture": "岩手県",
    "robots_txt_status": "制限なし(2026-10-13確認。robots.txtなし)",
}

BASE_URL = "https://www.cafejpn.co.jp"
CRAWL_DELAY_SECONDS = 1
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# (ページパス, 商品名(ナビ表記), ブレンドか, 産地(ストレートのみ、ページ記述で確認できるもの))
PAGES = [
    ("st/st01/st01", "コロンビア スプレモ", False, "コロンビア"),
    ("st/st02/st02", "ブラジル No.2/#18 バルジニアスペシャル", False, "ブラジル"),
    ("st/st03/st03", "エチオピア モカ イルガチェフェ G1", False, "エチオピア"),
    ("st/st04/st04", "ガテマラ SHB アンティグア リンダ", False, "グアテマラ"),
    ("st/st05/st05", "キリマンジャロ AA キボー", False, "タンザニア"),
    ("st/st06/st06", "マンデリン G-1", False, "インドネシア"),
    ("st/st08/st08", "パプアニューギニア", False, "パプアニューギニア"),
    ("st/st10/st10", "アンデスマウンテン", False, "エクアドル"),
    ("st/st11/st11", "ドミニカ AA", False, "ドミニカ共和国"),
    ("st/st12/st12", "カリビアンマウンテン", False, None),  # イスパニョーラ島(ハイチ/ドミニカ共和国)で国名は特定できない
    ("st/st13/st13", "エチオピア モカ シダモ G2", False, "エチオピア"),
    ("st/st14/st14", "ブラジル ハニー", False, "ブラジル"),
    ("st/st15/st15", "エメラルドマウンテン", False, "コロンビア"),
    ("bl/bl01/bl01", "オリジナル ブレンド", True, None),
    ("bl/bl02/bl02", "カリビアン ブレンド", True, None),
    ("bl/bl03/bl03", "マイルドビター ブレンド", True, None),
    ("bl/bl04/bl04", "ホテル ブレンド", True, None),
    ("bl/bl05/bl05", "ヨーロピアン ブレンド", True, None),
    ("bl/bl06/bl06", "ゴールデン ブレンド", True, None),
    ("bl/bl07/bl07", "スペシャル ブレンド", True, None),
    ("bl/bl08/bl08", "コロンビア ブレンド", True, None),
    ("bl/bl09/bl09", "ブラジル ブレンド", True, None),
    ("bl/bl10/bl10", "モカ ブレンド", True, None),
    ("bl/bl11/bl11", "キリマンジャロ ソフト ブレンド", True, None),
    ("fr/fr01/fr01", "深煎りコロンビア スプレモ(フレンチロースト)", False, "コロンビア"),
    ("fr/fr02/fr02", "深煎りブラジル No.2/#18 バルジニアスペシャル(フレンチロースト)", False, "ブラジル"),
    ("fr/fr03/fr03", "深煎りキリマンジャロ AA キボー(フレンチロースト)", False, "タンザニア"),
    ("fr/fr04/fr04", "深煎りブレンド(フレンチロースト)", True, None),
    ("fr/fr05/fr05", "エスプレッソ(フレンチロースト)", True, None),
    ("fr/fr06/fr06", "アイスコーヒー(イタリアンロースト)", True, None),
]

PRICE_RE = re.compile(r"(\d+)\s*g\s*パック\s*[￥¥]\s*([\d,]+)\s*（税込）")
FEATURE_RE = re.compile(r"豆 の 特 徴\s*(.*?)\s*香味チャート")


def fetch_text(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    html = resp.content.decode("cp932", errors="replace")  # 実データ確認済み: Shift_JIS
    html = re.sub(r"<script.*?</script>|<style.*?</style>", "", html, flags=re.S)
    html = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", html)


def parse_page(text: str) -> tuple[int | None, int | None, str | None]:
    """ページ内の最初の(=通常版の)価格表から最小重量の価格と、豆の特徴文を返す。"""
    body = text[text.find("ホーム ＞"):] if "ホーム ＞" in text else text
    prices = [(int(w), int(p.replace(",", ""))) for w, p in PRICE_RE.findall(body)[:3]]
    if not prices:
        return None, None, None
    weight, price = min(prices)
    m = FEATURE_RE.search(body)
    feature = m.group(1).strip() if m else None
    return weight, price, feature


def build_record(page: str, name: str, is_blend: bool, origin: str | None, text: str) -> dict | None:
    weight, price, feature = parse_page(text)
    if price is None:
        return None
    url = f"{BASE_URL}/{page}.html"
    parsed = parse_product(name)
    if is_blend:
        category = "ブレンド"
        origin_country, origin_source = None, None
    else:
        category = "ストレート"
        origin_country = origin
        origin_source = (parsed["origin_source"] if parsed["origin_country"] == origin else "description") if origin else None
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": category,
        "origin_country": origin_country,
        "origin_source": origin_source,
        "designated_brand": parsed["designated_brand"] if not is_blend else None,
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "flavor_notes": feature,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "販売中",
        "out_of_stock": False,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for page, name, is_blend, origin in PAGES:
        url = f"{BASE_URL}/{page}.html"
        try:
            text = fetch_text(url)
        except requests.RequestException as e:
            print(f"[warn] 取得失敗: {url} ({e})")
            continue
        rec = build_record(page, name, is_blend, origin, text)
        if rec is None:
            print(f"[warn] 価格が取れないためスキップ: {url}")
        else:
            records.append(rec)
        time.sleep(CRAWL_DELAY_SECONDS)
    return records


if __name__ == "__main__":
    records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": [],
        "non_bean_products_excluded": [],
    }
    with open("data_cafejpn.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_cafejpn.json に出力しました")
