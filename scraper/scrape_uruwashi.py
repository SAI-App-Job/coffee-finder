# -*- coding: utf-8 -*-
"""
scrape_uruwashi.py

ウルワシ(https://uruwashi.base.ec/、宮崎県宮崎市橘通西3丁目10-36 原ビル2F(橘通本店)/宮崎県宮崎市阿波岐原町前浜4276-1083(一ツ葉店・焙煎所))の商品情報を取得する。BASE。

【店舗発見の経緯】
九州再調査(宮崎県)で発見。実店舗2店(橘通本店・一ツ葉店=焙煎所)、1972年創業。

【対象商品について】
実データ確認済み(2026-10時点): オンラインショップ(URUWASHI ONLINE SHOP)の豆はブレンド4種(ウルワシブレンド、名画シリーズ「シャレード」「ティファニーで朝食を」「ローマの休日」)のみで、各200g/300g/400g(200g×2)の重量違い別商品。最小重量の200gを代表にする。ドリップバッグ・コースターは除外。ストレートはオンラインに無い
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している
(商品ページのタイトルがキャッチコピー付き・重量違いの重複登録のため)。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "ウルワシ",
    "url": "https://uruwashi.base.ec/",
    "platform": "BASE",
    "address": "宮崎県宮崎市橘通西3丁目10-36 原ビル2F(橘通本店)/宮崎県宮崎市阿波岐原町前浜4276-1083(一ツ葉店・焙煎所)",
    "prefecture": "宮崎県",
    "robots_txt_status": "実質許可(2026-11-03確認。User-agent: * は /cart/ /web_cart/ /shops/ 等のみ不許可で商品ページは許可。python-requests/curl等は個別にDisallowのため識別UAを使用)",
    "source_note": "BASE公式EC(https://uruwashi.base.ec/)の商品一覧と各商品ページを2026-11-03に確認。実店舗2店(橘通本店・一ツ葉店)は公式サイト https://www.uruwashi.com/ で確認。価格に更新日表示なし(『価格や内容量に変更』の告知あり)",
    "last_verified_at": "2026-11-03",
}

BASE_URL = "https://uruwashi.base.ec"
REQUEST_INTERVAL = 5  # BASEは5秒以上
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ("85283573", "ウルワシブレンド", 200, "ブレンド", None),
    ("148568477", "名画シリーズ「シャレード」", 200, "ブレンド", None),
    ("148214298", "名画シリーズ「ティファニーで朝食を」", 200, "ブレンド", None),
    ("111404918", "名画シリーズ「ローマの休日」", 200, "ブレンド", None),
]

# coffee_parser.pyの国名辞書で検出できない表記(「タイ」「中国」「ケニヤ」等)の産地を明示する
ORIGIN_OVERRIDES = {}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id: str, name: str, weight_g: int, category_override: str | None, roast_level: str | None) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    desc = re.sub(r"\s+", " ", desc_m.group(1)).strip().split("※賞味期限")[0].strip()[:400] if desc_m else None
    price_m = PRICE_PATTERN.search(html_text)
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    sold_out = bool(purchasability_m) and purchasability_m.group(1) == "unpurchasable"

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
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
        if item_id in ORIGIN_OVERRIDES:
            parsed["origin_country"] = ORIGIN_OVERRIDES[item_id]
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
        "roast_level": roast_level or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price_m.group(1)) if price_m else None,
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/items/{item_id}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item_id, name, weight_g, category_override, roast_level in ITEMS:
        try:
            time.sleep(REQUEST_INTERVAL)
            record = build_record(item_id, name, weight_g, category_override, roast_level)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_uruwashi.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_uruwashi.json に出力しました")


if __name__ == "__main__":
    main()
