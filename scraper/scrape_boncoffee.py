# -*- coding: utf-8 -*-
"""
scrape_boncoffee.py

BON COFFEE -BEANS STORE-(https://onlinestore.boncoffee.net/、福井県福井市板垣5-1212)の
商品情報を取得する。カラーミーショップ(onlinestore.boncoffee.net / bon-coffee.shop-pro.jp)。

【店舗発見の経緯】
全国再調査(福井県)の新規発掘。住所は特定商取引法ページ(?mode=sk)で確認(2026-10-12)。

【対象商品について】
実データ確認済み(2026-10-12): カテゴリ「コーヒー豆」の商品のうち、200gの豆/粉(購入時に
「豆のまま」「中挽き」等を選択するバリアント。価格は挽き方によらず同一)の15銘柄を対象とする。
ドリップバッグ(1個180円)、ギフトセット、水出しアイスコーヒー(パック)は除外。
「デカフェ、カフェインレス、コーヒー 200g」は1商品内でブレンド/ブラジル/ホンジュラスを
選択する形式のため、1商品(ブレンド扱い)として収録する。
商品名は商品ページのタイトルからキャッチコピーを除いて下のITEMSに明示している。
価格はColorme JSONのバリアント価格(税込)、在庫は「ADD TO CART」の有無で判定する。

【robots.txtについて】
User-agent: *は/secure/と/cart/のみ制限。識別可能な独自User-Agentを使用する。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "BON COFFEE -BEANS STORE-",
    "url": "https://onlinestore.boncoffee.net/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "福井県福井市板垣5-1212",
    "prefecture": "福井県",
    "robots_txt_status": "許可(2026-10確認。User-agent: *は/secure/と/cart/のみ制限)",
}

BASE_URL = "https://onlinestore.boncoffee.net/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 産地(日本語。Noneなら自動判定))
ITEMS = [
    ("156647260", "パプアニューギニア シグリ農園", 200, None, "パプアニューギニア"),
    ("156749681", "デカフェ(カフェインレス)コーヒー", 200, "ブレンド", None),
    ("162116381", "ナチュラルブレンド", 200, "ブレンド", None),
    ("165428862", "タンザニア アデラ", 200, None, "タンザニア"),
    ("186635138", "インドネシア トバコ(マンデリン)", 200, None, "インドネシア"),
    ("186886359", "コロンビア サンアグスティン", 200, None, "コロンビア"),
    ("186988816", "ケニア レッドマウンテン", 200, None, "ケニア"),
    ("187022846", "ブラジル トミオフクダ DOT(Dry On Tree)", 200, None, "ブラジル"),
    ("191893034", "ブラジル エレナ農園 ムンドノーボ", 200, None, "ブラジル"),
    ("192328796", "グアテマラ ラ・アゾテア SHB", 200, None, "グアテマラ"),
    ("192776434", "グアテマラ アンティグア ジャスミン", 200, None, "グアテマラ"),
    ("193664723", "エチオピア イルガチェフェG1 コンガ村 ナチュラル", 200, None, "エチオピア"),
    ("91003012", "オリジナルブレンド", 200, "ブレンド", None),
    ("95126508", "ビターブレンド", 200, "ブレンド", None),
    ("151819136", "アイスコーヒーブレンド", 200, "ブレンド", None),
]

# 商品ページ本文の焙煎度の明記(実データ確認済み 2026-10-12)に基づく。表の「焙煎度」行があればそちらを優先。
ROAST_OVERRIDES = {
    "186886359": "中深煎り(フルシティロースト)",
    "186988816": "中深煎り",
    "187022846": "中深煎り",
    "191893034": "中深煎り",
    "192776434": "中深煎り",
    "193664723": "中深煎り",
    "95126508": "深煎り",
    "151819136": "深煎り",
}

ROAST_TABLE_LABEL = "焙煎度"
FLAVOR_LABELS = ("口当たり", "香り", "酸味", "余韻", "味わい", "コク", "甘味", "甘み", "フレーバー")


def fetch_soup(url):
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    text = resp.content.decode("euc-jp", errors="replace")
    return BeautifulSoup(text, "html.parser"), text


def extract_colorme_product(text):
    m = re.search(r"var\s+Colorme\s*=\s*(?=\{)", text)
    if not m:
        return None
    try:
        data, _ = json.JSONDecoder().raw_decode(text[m.end():])
    except json.JSONDecodeError:
        return None
    return data.get("product")


def extract_body(soup):
    txt = soup.get_text("\n", strip=True)
    i = txt.find("返品について")
    j = txt.find("review", i)
    return txt[i + len("返品について"):j] if i >= 0 and j > i else ""


def extract_roast(soup):
    for tr in soup.select("table.boncoffee-table tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
        if len(cells) >= 2 and cells[0] == ROAST_TABLE_LABEL:
            return cells[1]
    return None


def extract_flavor_notes(body):
    lines = [ln.strip() for ln in body.split("\n") if ln.strip()]
    picked = []
    for ln in lines:
        m = re.match(r"^(%s)[：:]\s*(.+)$" % "|".join(FLAVOR_LABELS), ln)
        if m:
            picked.append(ln)
    if picked:
        return " ".join(picked)[:400]
    # 味の表記ラベルが無いページは、冒頭の紹介文(産地・農園・味わいの説明)を使う
    return " ".join(lines)[:250] or None


def build_record(pid, name, weight_g, category_override, origin):
    url = f"{BASE_URL}?pid={pid}"
    soup, text = fetch_soup(url)
    cp = extract_colorme_product(text) or {}
    variants = cp.get("variants") or []
    price = variants[0].get("option_price_including_tax") if variants else cp.get("sales_price_including_tax")
    in_stock = "ADD TO CART" in soup.get_text(" ", strip=True)
    body = extract_body(soup)

    parsed = parse_product(name)
    if category_override:
        parsed["category"] = category_override
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if origin:
            parsed["origin_country"] = origin
            parsed["origin_source"] = "raw_name"

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": extract_roast(soup) or ROAST_OVERRIDES.get(pid) or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": extract_flavor_notes(body),
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": "販売中" if in_stock else "完売",
        "out_of_stock": not in_stock,
        "product_url": url,
    }


def scrape_all_products():
    records = []
    for pid, name, weight_g, category_override, origin in ITEMS:
        try:
            records.append(build_record(pid, name, weight_g, category_override, origin))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={pid} ({e})")
        time.sleep(1)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_boncoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_boncoffee.json に出力しました")


if __name__ == "__main__":
    main()
