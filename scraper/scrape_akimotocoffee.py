# -*- coding: utf-8 -*-
"""
scrape_akimotocoffee.py

秋元珈琲焙煎所(akimoto.base.shop、栃木県大田原市親園2301。2014年開業、
田んぼの中の自家焙煎豆屋)の商品情報を取得する。BASE(base.shopドメイン)。

【店舗発見の経緯】
全国再調査(栃木県)でサブエージェント調査から発見。

【対象商品について】
実データ確認済み(2026-09時点): 商品一覧全15件のうち、無農薬栽培米
「田谷米」2種・ネルフィルター2種・コラボCDアルバム・十周年記念手ぬぐい
2種を除いた、コーヒー豆7銘柄(200g、ブレンド6・ストレート1)を対象とする。
「キャラメラード〜Brazil blend〜」は商品名に"blend"を含むが実際は
単一農園(ヴィセンチ氏)の豆を2つの焙煎パターンでアフターミックスした
ものであり、産地はブラジル一国のみのためparse_product()もこれを反映
してcategory=ブレンド・origin_country=ブラジルの両方を保持している
(矛盾ではなく、焙煎方法としての"ブレンド"と産地の単一性を両立して
記録している)。

【商品説明・重量について】
実データ確認済み: og:descriptionは短い風味フレーズのみで構造化ラベルは
無い。重量はメタタグに含まれず、ページのJS描画される購入オプション
(「200g 豆」「200g 粉」)からのみ確認できるため、全商品共通で200gを
ハードコードしている。
"""

import json
import re

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "秋元珈琲焙煎所",
    "url": "https://akimoto.base.shop/",
    "platform": "BASE(base.shop)",
    "address": "栃木県大田原市親園2301",
    "prefecture": "栃木県",
    "robots_txt_status": "未確認(BASE標準構成)",
}

BASE_URL = "https://akimoto.base.shop"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}

ITEM_IDS = [
    "23011586",  # キャラメラード ~ Brazil blend ~
    "39554853",  # 土のブレンド「芝草」 - しばくさ -
    "9002846",   # 光のブレンド「舞白」- まいは -
    "9002865",   # 風のブレンド「田綾」 - たあや -
    "9002878",   # 火のブレンド「遥灯」- はるひ -
    "9002906",   # 空のブレンド「咲雨」- えみう -
    "9002929",   # 水のブレンド「瑠日」- るか -
]

TITLE_PATTERN = re.compile(r"<title>([^<|]+?)\s*\|\s*")
DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id: str) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=20)
    resp.encoding = "utf-8"
    html_text = resp.text

    title_m = TITLE_PATTERN.search(html_text)
    if not title_m:
        return None
    title = re.sub(r"\s+", " ", title_m.group(1).strip()).strip()

    desc_m = DESC_PATTERN.search(html_text)
    flavor_text = desc_m.group(1).strip() if desc_m else None

    price_m = PRICE_PATTERN.search(html_text)
    price = int(price_m.group(1)) if price_m else None
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    sold_out = bool(purchasability_m) and purchasability_m.group(1) != "purchasable"
    stock_status = "完売" if sold_out else "販売中"

    parsed = parse_product(title)
    url = f"{BASE_URL}/items/{item_id}"

    if parsed["category"] != "ブレンド":
        detected = detect_country_name(title)
        if detected:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
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
        "flavor_notes": flavor_text,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": 200,
        "stock_status": stock_status,
        "out_of_stock": sold_out,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item_id in ITEM_IDS:
        try:
            detail = build_record(item_id)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        if detail is None:
            continue
        records.append(detail)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_akimotocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_akimotocoffee.json に出力しました")


if __name__ == "__main__":
    main()
