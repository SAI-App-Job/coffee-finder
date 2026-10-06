# -*- coding: utf-8 -*-
"""
scrape_sonirokicoffee.py

深やき珈琲 そにろき(公式 http://www.sonirokicoffee.com/、広島県呉市宮原、深煎り専門の自家焙煎珈琲店)
の商品情報を取得する。FC2ショッピングカート(shopingsoniroki.cart.fc2.com)。

【店舗発見の経緯】
全国再調査(広島県)の新規発掘で発見。

【住所について】
カートの特定商取引法ページ(/laws)で実データ確認済み(2026-10時点): 「深やき珈琲 そにろき 所在地
広島県呉市宮原13丁目23-3」。

【対象商品について】
実データ確認済み(2026-10時点): カテゴリ「珈琲焙煎豆」(ca=1、全13商品)のうち、焙煎豆の8商品
(ストレート5・ブレンド3)を対象とする。除外: 「7日に1度お届け 6回コース」(定期便)、「ご贈答用
箱入りセット(ピッコロ/ミディ/グランデ)」(ギフトセット)、「ご贈答用 袋入り包装」(包装資材)。
全商品が100g単位(注文数 100g〜1000gの選択式)の1商品で、重量違いの別商品は無い。価格は100gの
単価として表示される(最小重量100gを採用)。公式サイトの旧表記に出ていたブルンジ・ブラジルは
現在カートに掲載されていない。

【価格について】
カートの表示価格(例: 972円、1,080円)を採用する。公式サイト(newpage2.html)の旧表記は「700円
(税込 756円)」の形式で、カート価格はこの税込側と同じ形式(756円→972円=本体900円×1.08)のため、
税込価格と判断している(カートページ自体には税込/税抜の明記なし)。価格改定は2026/03/30のお知らせ。

【焙煎度について】
店名・商品説明に「ヨーロピアンスタイルの深やき」等の記載があるため、説明文に「深やき/深煎り」が
ある商品のみroast_hint「深煎り」とする(焙煎度は選択式ではない)。

【在庫について】
カートへの投入ボタン(Submit_cart)の有無で判定する(取得時点では全商品が購入可能)。

【robots.txtについて】
カート側robots.txtは/cancel/・/setup/・/tools/のみDisallow(実データ確認済み、2026-10)。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "深やき珈琲 そにろき",
    "url": "http://www.sonirokicoffee.com/",
    "platform": "FC2ショッピングカート(cart.fc2.com)",
    "address": "広島県呉市宮原13丁目23-3",
    "prefecture": "広島県",
    "robots_txt_status": "許可(2026-10確認。カート側robots.txtは/cancel/・/setup/・/tools/のみDisallow)",
}

BASE_URL = "https://shopingsoniroki.cart.fc2.com"
LIST_URL = BASE_URL + "/?ca=1&par_page=100"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

PRICE_PATTERN = re.compile(r"価格：<b>([\d,]+)円</b>")
EXCLUDE_KEYWORDS = ["コース", "セット", "包装", "定期"]
# 商品名がひらがな表記のため、coffee_parser.pyの国名辞書では検出できない
HIRAGANA_ORIGINS = {
    "えちおぴあん": "エチオピア",
    "ぶるんじ": "ブルンジ",
    "ぶらじる": "ブラジル",
    "ぱぷあにゅーぎにあ": "パプアニューギニア",
    "いんどねしあ": "インドネシア",
    "にからぐあ": "ニカラグア",
    "たんざにあ": "タンザニア",
    "ころんびあ": "コロンビア",
    "ぐあてまら": "グアテマラ",
}
DEEP_ROAST_PATTERN = re.compile(r"深やき|深煎り")


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def list_items() -> list[dict]:
    html_text = fetch_html(LIST_URL)
    items = {}
    for m in re.finditer(r'<div class="name"><a href="/ca1/(\d+)/p-r1?-s/">(.*?)</a></div>', html_text, flags=re.S):
        pid = m.group(1)
        if pid not in items:
            name = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", re.sub(r"<[^>]+>", "", m.group(2)))).strip()
            items[pid] = {"pid": pid, "name": name}
    return list(items.values())


def fetch_detail(pid: str) -> dict:
    html_text = fetch_html(f"{BASE_URL}/ca1/{pid}/p-r-s/")
    soup = BeautifulSoup(html_text, "html.parser")
    comment = soup.select_one("div.comment")
    desc = re.sub(r"\s+", " ", comment.get_text(" ", strip=True)) if comment else None
    price_m = PRICE_PATTERN.search(html_text)
    return {
        "description": desc,
        "price": int(price_m.group(1).replace(",", "")) if price_m else None,
        "purchasable": "Submit_cart" in html_text,
    }


def build_record(item: dict) -> dict | None:
    name = item["name"]
    if any(kw in name for kw in EXCLUDE_KEYWORDS):
        return None
    detail = fetch_detail(item["pid"])
    if detail["price"] is None:
        return None
    desc = detail["description"]

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    is_blend = "ぶれんど" in name or "blend" in name.lower() or "ブレンド" in name
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"]:
            detected = detect_country_name(name)
            if detected:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
        if not parsed["origin_country"]:
            for kw, country in HIRAGANA_ORIGINS.items():
                if name.startswith(kw):
                    parsed["origin_country"] = country
                    parsed["origin_source"] = "raw_name"
                    break
        parsed = apply_category_hint_fallback(parsed, name)

    roast_hint = "深煎り" if desc and DEEP_ROAST_PATTERN.search(desc) else None
    out_of_stock = not detail["purchasable"]

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": roast_hint,
        "roast_selectable": False,
        "flavor_notes": desc[:400] if desc else None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": detail["price"],
        "weight_g": 100,
        "stock_status": "完売" if out_of_stock else "販売中",
        "out_of_stock": out_of_stock,
        "unit_note": "表示価格は100gあたり(注文数は100g単位)。税込表記の明記はないが公式サイトの旧表記(税込756円)と同形式のため税込と判断",
        "product_url": f"{BASE_URL}/ca1/{item['pid']}/p-r-s/",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in list_items():
        if any(kw in item["name"] for kw in EXCLUDE_KEYWORDS):
            continue
        try:
            record = build_record(item)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={item['pid']} ({e})")
            continue
        if record is not None:
            records.append(record)
        time.sleep(0.5)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_sonirokicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_sonirokicoffee.json に出力しました")


if __name__ == "__main__":
    main()
