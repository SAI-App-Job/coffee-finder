# -*- coding: utf-8 -*-
"""
scrape_plaincoffeeshop.py

PLAIN COFFEE SHOP(https://plaincoffee.theshop.jp/、鹿児島県鹿児島市加治屋町9-14)の
自家焙煎コーヒー豆の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(鹿児島県)の新規発掘で発見。

【住所について】
BASEの特商法ページ(/law)に事業者の所在地として「〒892-0846 鹿児島県鹿児島市加治屋町9-14」
(事業者名: 西田朗)が記載されている(2026-10-13確認)。公式サイトは未確認。

【対象商品について】
sitemap.xml の商品7件のうち、コーヒー豆4銘柄(シングルオリジン3種+DARK BLEND、各150g)を
対象とする。水出しコーヒーバッグ(cold brew)・ディップスタイルコーヒーバッグ・
ZENcoffee ドリップバッグ(デカフェ)は除外。各商品は「豆のまま/中挽き/粗挽き」の選択式で同額。
商品名はタイトルから重量(150g)と焙煎度(【浅煎り】等)の表記を除いたもの。
焙煎度は店の表記(浅煎り/中浅煎り/中煎り/深煎り)を roast_hint に保持する。
説明文末尾の注意書き(クリックポスト)は除く。

【robots.txtについて】
他のBASE系店舗と同一の記述。識別可能な独自User-Agentを使用する。
"""

import html as _html
import json
import re
import time

import requests

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    detect_country_name,
    normalize_processing_method,
)

SHOP_INFO = {
    "name": "PLAIN COFFEE SHOP",
    "url": "https://plaincoffee.theshop.jp/",
    "platform": "BASE",
    "address": "鹿児島県鹿児島市加治屋町9-14",
    "prefecture": "鹿児島県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://plaincoffee.theshop.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
# (商品ID, 分類の上書き(Noneなら自動判定))
ITEMS = [
    ("155581550", None),        # KENYA New Joma Farm
    ("149672671", None),        # Peru Edwin Tello
    ("149672220", None),        # TANZANIA Acacia Hills KentAA
    ("85890728", "ブレンド"),   # DARK BLEND
]
WEIGHT_G = 150

TITLE_PATTERN = re.compile(r'<meta property="og:title" content="([^"]*)"')
DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
VARIATION_NAME = re.compile(r'cot-itemOrder-variationName"[^>]*>([^<]*)')
VARIATION_STOCK = re.compile(r'cot-itemOrder-variationStock"[^>]*>([^<]*)')
ROAST_TITLE = re.compile(r"[【\[]\s*(浅煎り|中浅煎り|中煎り|中深煎り|深煎り)\s*[】\]]")
FIELD_KEYS = ["生産者", "地域", "標高", "品種", "精製", "テイスト"]


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("　", " ")).strip()


def field(desc: str, key: str):
    others = "|".join(k for k in FIELD_KEYS if k != key)
    m = re.search(key + r"：(.+?)(?=(?:" + others + r")：|[ぁ-んァ-ヶ一-龥]{6,}|$)", desc)
    return clean(m.group(1)) if m else None


def build_record(item_id: str, category_override: str | None) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    t = resp.text
    title = clean(_html.unescape(TITLE_PATTERN.search(t).group(1)))
    title = re.sub(r"\s*\|.*$", "", title)
    rm = ROAST_TITLE.search(title)
    roast_hint = rm.group(1) if rm else None
    name = clean(ROAST_TITLE.sub("", re.sub(r"\s*150\s*g\b", "", title, flags=re.IGNORECASE)))
    desc = clean(_html.unescape(DESC_PATTERN.search(t).group(1)))
    desc = re.sub(r"※クリックポストでの発送.*$", "", desc).strip()
    price_m = PRICE_PATTERN.search(t)
    pm = PURCHASABILITY_PATTERN.search(t)
    sold_out = bool(pm) and pm.group(1) == "unpurchasable"
    names, stocks = VARIATION_NAME.findall(t), VARIATION_STOCK.findall(t)
    if names and stocks and "在庫なし" in stocks[0]:
        sold_out = True

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if category_override:
        parsed["category"] = category_override
    blend_comp = []
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        blend_comp = [clean(x) for x in re.findall(r"・\s*([A-Za-z ]+ (?:Washed|Natural|Honey)\s*\d+%)", desc)]
        parsed["processing_method"] = None
        origin_label = None
    else:
        origin_label = field(desc, "地域")
        # 「地域」には国がないため、商品名(KENYA/Peru/TANZANIA)で産地を判定する
        parsed = apply_category_hint_fallback(parsed, name)
        proc = field(desc, "精製")
        if proc and not parsed["processing_method"]:
            parsed["processing_method"] = normalize_processing_method(proc)
    farm_parts = []
    for key, label in (("生産者", "生産者"), ("地域", "地域"), ("標高", "標高"), ("品種", "品種")):
        v = field(desc, key) if parsed["category"] != "ブレンド" else None
        if v:
            farm_parts.append(f"{label}: {v}")
    taste = field(desc, "テイスト") if parsed["category"] != "ブレンド" else None
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": None,
        "roast_hint": roast_hint,
        "post_processing_tags": parsed["post_processing_tags"],
        "farm_note": " / ".join(farm_parts) or None,
        "flavor_notes": taste or (re.sub(r"^.*?[】\]]\s*", "", re.sub(r"・[A-Za-z ]+ (?:Washed|Natural|Honey)\s*\d+%", "", desc), count=1).strip()[:300] if parsed["category"] == "ブレンド" else None),
        "blend_components": blend_comp,
        "decaf_process": None,
        "price": int(price_m.group(1)) if price_m else None,
        "weight_g": WEIGHT_G,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/items/{item_id}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item_id, cat in ITEMS:
        try:
            rec = build_record(item_id, cat)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        if rec:
            records.append(rec)
        time.sleep(0.5)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_plaincoffeeshop.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_plaincoffeeshop.json に出力しました")


if __name__ == "__main__":
    main()
