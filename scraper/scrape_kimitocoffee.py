# -*- coding: utf-8 -*-
"""
scrape_kimitocoffee.py

きみと珈琲(https://kimitocoffee.theshop.jp/、滋賀県彦根市柳川町218-1 VOID A PART内)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(滋賀県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): 全8商品のうち、200gのブレンド3種とデカフェ(メキシコ)1種の計4商品を対象とする。定期便・コーヒーバッグ・Tシャツ・1kg大容量(きみとふかいりブレンド)は除外。
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している。
価格・在庫(item_purchasability、豆/粉のバリエーション在庫)・説明(商品ページのJSON-LD)は
商品ページから取得する。焙煎度は商品名の表記(中煎り/中深煎り/深煎り)を使う。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "きみと珈琲",
    "url": "https://kimitocoffee.theshop.jp/",
    "platform": "BASE",
    "address": "滋賀県彦根市柳川町218-1 VOID A PART内",
    "prefecture": "滋賀県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://kimitocoffee.theshop.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品ページから判定), 産地の上書き(Noneなら自動判定))
ITEMS = [
    ('38745069', 'びわ湖ロースタリーブレンド 中煎り 200g', 200, 'ブレンド', '中煎り', None),
    ('82262461', '日々ブレンド 中深煎り 200g', 200, 'ブレンド', '中深煎り', None),
    ('69936933', 'きみとふかいりブレンド 深煎り 200g', 200, 'ブレンド', '深煎り', None),
    ('38746007', 'デカフェ メキシコ 深煎り 200g', 200, None, '深煎り', 'メキシコ'),
]

PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
LD_PATTERN = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
ROAST_PATTERN = re.compile(r"焙煎度[:：]\s*([^\s　]+)")
SCALE_PATTERN = re.compile(r"焙煎度[:：]\s*浅煎り([ー〇○◯]+)深煎り")
SCALE_LABELS = ["浅煎り", "中浅煎り", "中煎り", "中深煎り", "深煎り"]


def fetch_page(item_id: str) -> tuple[str, int | None, str | None, bool | None]:
    """商品ページから(説明全文, 価格, item_purchasability, 豆バリエーションの品切れ)を返す。"""
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    html_text = resp.text

    desc = ""
    for m in LD_PATTERN.finditer(html_text):
        try:
            data = json.loads(m.group(1))
        except ValueError:
            continue
        if isinstance(data, dict) and data.get("description"):
            desc = BeautifulSoup(data["description"], "html.parser").get_text(" ", strip=True)
            break
    desc = re.sub(r"\s+", " ", desc).strip()

    price_m = PRICE_PATTERN.search(html_text)
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)

    # 「豆/粉」「豆のまま/中挽き」等のバリエーションがある場合は、豆のバリエーションの在庫で判定する
    bean_sold_out = None
    soup = BeautifulSoup(html_text, "html.parser")
    bean_states = []
    for li in soup.select(".cot-itemOrder-variationLI"):
        name_el = li.select_one(".cot-itemOrder-variationName")
        if not name_el:
            continue
        vname = unicodedata.normalize("NFKC", name_el.get_text(strip=True))
        if "豆" in vname and "粉" not in vname and "挽き豆" not in vname:
            bean_states.append(li.select_one('[data-type="soldOut"]') is not None)
    if bean_states:
        bean_sold_out = all(bean_states)

    return desc, (int(price_m.group(1)) if price_m else None), (purchasability_m.group(1) if purchasability_m else None), bean_sold_out


def detect_roast(desc: str) -> tuple[str | None, str | None]:
    """説明文の「焙煎度:」から(焙煎度, 目盛りの原文)を返す。"""
    m = SCALE_PATTERN.search(desc)
    if m:
        marks = m.group(1)
        pos = next((i for i, c in enumerate(marks) if c in "〇○◯"), None)
        if pos is not None and len(marks) == len(SCALE_LABELS):
            return SCALE_LABELS[pos], f"店の焙煎度目盛り: 浅煎り{marks}深煎り(5段階中{pos + 1})"
        return None, None
    m = ROAST_PATTERN.search(desc)
    if m:
        return m.group(1), None
    return None, None


def build_record(item_id: str, name: str, weight_g: int, category_override: str | None,
                 roast_level: str | None, origin_override: str | None) -> dict | None:
    desc_full, price, purchasability, bean_sold_out = fetch_page(item_id)
    desc = desc_full[:400] or None
    if bean_sold_out is not None:
        sold_out = bean_sold_out
    else:
        sold_out = purchasability == "unpurchasable"

    parse_name = unicodedata.normalize("NFKC", name)
    parsed = parse_product(parse_name)
    if parsed["is_flavored"]:
        return None
    if category_override:
        parsed["category"] = category_override
    roast_hint = None
    if roast_level is None:
        roast_level, roast_hint = detect_roast(unicodedata.normalize("NFKC", desc_full))
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(parse_name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, parse_name)
        if origin_override:
            parsed["origin_country"] = origin_override
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
        "roast_hint": roast_hint,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/items/{item_id}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item_id, name, weight_g, category_override, roast_level, origin_override in ITEMS:
        try:
            record = build_record(item_id, name, weight_g, category_override, roast_level, origin_override)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_kimitocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kimitocoffee.json に出力しました")


if __name__ == "__main__":
    main()
