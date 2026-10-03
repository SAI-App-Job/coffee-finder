# -*- coding: utf-8 -*-
"""
scrape_mamekichi.py

珈琲豆焙煎工房 まめ吉(mameya-mamekichi.jimdoweb.com、東京都立川市砂川町6-36-11、
玉川上水緑道沿いのログハウス。GRN完全熱風式焙煎機による自家焙煎、店主1名)の
商品情報を取得する。Jimdo(価格表は静的ページ、注文は別サイトのSTORES注文ボタン)。

【ページ構造について】
実データ確認済み(2026-10時点): 「ブレンド珈琲豆」「シングルオリジン珈琲豆」の2ページに
商品説明と「<焙煎度>♪ <銘柄名> 200g <価格>円(税込)」が並ぶ。同じ銘柄は
「400g(200g+200g)ご注文専用」「600g以上ご注文専用」の2つの注文ボタンが並ぶため
価格行が2回出現するので、(銘柄名, 焙煎度)で重複排除する。通信販売の最小発送量は
400g(200g×2)だが、価格表示の単位は200gのため、200gを代表重量・価格とする。
同一銘柄で焙煎度違い(例: ブラジル・ムンドノーボの深煎り/中煎り)は別商品として扱う。
STORES側(empty-wind-5260.stores.jp)はCAPTCHA(403)で取得できないため在庫状態は
Jimdoページ上の表記のみで、品切れ表示が無いため販売中として扱う。
ドリップバッグ・定期便・カフェ・スコーン類は対象外。個別URLが無いため
product_url はページURL + '#' + 商品名(+焙煎度)とする。
"""

import json
import re
import unicodedata
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, normalize_processing_method

SHOP_INFO = {
    "name": "珈琲豆焙煎工房 まめ吉",
    "url": "https://mameya-mamekichi.jimdoweb.com/",
    "platform": "Jimdo(静的価格表+STORES注文)",
    "address": "東京都立川市砂川町6-36-11",
    "prefecture": "東京都",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://mameya-mamekichi.jimdoweb.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (ページのパス, 既定カテゴリ, 先頭商品の説明文開始位置を示す区切り文字列)
PAGES = [
    ("/ブレンド珈琲豆/", "ブレンド", "お好みの味が見つかりますように！"),
    ("/シングルオリジン珈琲豆/", "ストレート", "シングルオリジン珈琲豆のご注文はこちらです"),
]

# 銘柄名・説明文から産地が判別できないもの
ORIGIN_OVERRIDES = {
    "トラジャママサ": "インドネシア",
    "マンデリンTABOO": "インドネシア",
}

PRICE_PATTERN = re.compile(r"200g\s*([\d,]+)\s*円")
ROAST_WORDS = ("中深煎り", "中浅煎り", "深煎り", "中煎り", "浅煎り")


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()


def parse_page(path: str, default_category: str, start_marker: str) -> list[dict]:
    url = BASE_URL + quote(path)
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    text = BeautifulSoup(resp.text, "html.parser").get_text(" ", strip=True)
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"(?<=\d)\s+(?=\d)", "", text)  # 「158 0円」のような桁途中の改行を詰める
    text = re.sub(r"\s+", " ", text)

    items = []
    seen = set()
    prev_end = 0
    last_desc = {}
    for m in PRICE_PATTERN.finditer(text):
        pre = text[prev_end:m.start()]
        prev_end = m.end()
        # 説明文: 直前ブロックの末尾(「準じます」)より後ろ〜「※お豆の通信販売」の手前
        if "準じます" in pre:
            after = pre.split("準じます")[-1]
        elif unicodedata.normalize("NFKC", start_marker) in pre:
            after = pre.split(unicodedata.normalize("NFKC", start_marker))[-1]
        else:
            after = ""
        desc_part = after.split("※お豆の通信販売")[0].strip()
        # 名前: 最後の区切り(「願います。」または「♪」)より後ろ
        cut = max(pre.rfind("願います。") + len("願います。") if "願います。" in pre else -1, pre.rfind("♪") + 1)
        name_part = pre[cut:].strip() if cut > 0 else pre.strip()
        roast = None
        if pre.rfind("♪") + 1 == cut and cut > 0:
            before = pre[:cut - 1].strip()
            for w in ROAST_WORDS:
                if before.endswith(w):
                    roast = w
                    break
        name = re.sub(r"\s+", " ", name_part).strip()
        if not name:
            continue
        key = (name.replace(" ", ""), roast)
        if key in seen:
            continue
        seen.add(key)
        if desc_part and "お豆の通信販売" not in desc_part:
            last_desc[name] = desc_part
        items.append({
            "name": name,
            "roast": roast,
            "price": int(m.group(1).replace(",", "")),
            "desc": last_desc.get(name),
            "page_url": url,
            "default_category": default_category,
        })
    # 後続の焙煎度違い(説明文なし)に同銘柄の説明文を補う
    for it in items:
        it["desc"] = it["desc"] or last_desc.get(it["name"])
    return items


def build_record(item: dict) -> dict:
    name = item["name"]
    desc = item["desc"]
    roast = item["roast"]
    # 名前の先頭の焙煎度表記(「デカフェ中煎り」)から焙煎度を補う
    if not roast:
        for w in ROAST_WORDS:
            if name.endswith(w):
                roast = w
                break

    parsed = parse_product(name)
    if item["default_category"] == "ブレンド" or "ブレンド" in name:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        if not parsed["origin_country"]:
            country = ORIGIN_OVERRIDES.get(name) or detect_country_name(desc or "")
            if country:
                parsed["origin_country"] = country
                parsed["origin_source"] = "description" if not ORIGIN_OVERRIDES.get(name) else "raw_name"
        parsed = apply_category_hint_fallback(parsed, desc or "")

    processing = parsed["processing_method"]
    if not processing and desc:
        pm = re.search(r"精製方法[：:]\s*([^\s。]+)", desc)
        if pm:
            processing = normalize_processing_method(pm.group(1))
    grade = parsed["grade"]
    if not grade and desc:
        gm = re.search(r"グレード[：:]\s*(G-?\d)", desc)
        if gm:
            grade = gm.group(1).replace("-", "")

    display = name if not roast or roast in name else f"{name}({roast})"
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": display,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": grade,
        "roast_level": roast or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": (desc or None) and desc[:500],
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": 200,
        "stock_status": "販売中",
        "out_of_stock": False,
        "product_url": item["page_url"] + "#" + quote(display),
    }


def scrape_all_products() -> list[dict]:
    records = []
    for path, cat, marker in PAGES:
        try:
            items = parse_page(path, cat, marker)
        except requests.RequestException as e:
            print(f"[warn] ページ取得失敗: {path} ({e})")
            continue
        records.extend(build_record(it) for it in items)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_mamekichi.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mamekichi.json に出力しました")


if __name__ == "__main__":
    main()
