# -*- coding: utf-8 -*-
"""
scrape_motoazaburoastery.py

元麻布焙煎所(https://www.motoazabu-roastery.com/、東京都港区元麻布)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(東京都)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): 店舗名・焙煎士紹介(2023年12月開業、注文焙煎)から港区元麻布の焙煎所と判断(BASEの特定商取引法表記はBASE社所在地のみで番地は公式サイト上で確認できないため、住所は区・町名のみ)。全22商品のうちドリップバッグ・定期便・水出し・シークレット(3個詰合せ)を除く12銘柄(ブレンド1・シングル11、デカフェ2含む)を対象とする。注文焙煎のため焙煎度はお客様が選択(オススメ表示のみ)でroast_levelはNone。内容量は商品名の【200g】【100g】から取り、デカフェ2種は商品ページに内容量の記載がないためNone。
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している
(商品名に重量・焙煎度・キャッチコピーが混在しているため)。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。
在庫がpartially_purchasable(豆のみ品切れ等)の商品は販売中として扱う。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import json
import re

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "元麻布焙煎所",
    "url": "https://www.motoazabu-roastery.com/",
    "platform": "BASE",
    "address": "東京都港区元麻布",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://www.motoazabu-roastery.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g。ページに記載がなければNone), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('159721289', 'ニカラグア サンタマリア パカマラ ウォッシュド', 200, None, None),
    ('159721272', 'ケニア キアンヤンギ AA', 200, None, None),
    ('159721257', 'ケニア ガトンボヤ AA', 200, None, None),
    ('159721243', 'ペルー クラシック・プーノ ウォッシュド', 200, None, None),
    ('96618810', 'デカフェ NewCropフルッタメルカドン SWISS WATER アナエロビックナチュラルプロセス', None, None, None),
    ('94015485', 'パナマ エスメラルダPrivate Collection ゲイシャ ウォッシュド', 100, None, None),
    ('94015093', 'パナマ エスメラルダPrivate Collection ゲイシャ ナチュラル', 100, None, None),
    ('86542404', 'インドネシア マンデリン トバコ', 200, None, None),
    ('81679949', '元麻布ブレンド', 200, None, None),
    ('81307613', 'エチオピア イルガチェフェ G/1 コンガ農協 ナチュラル', 200, None, None),
    ('81008457', 'デカフェ コロンビア デカフェ ラ・プラデーラ', None, None, None),
    ('80580217', 'ブラジル パッセイオ イエローブルボン パルプドナチュラル', 200, None, None),
]

# coffee_parser.pyの国名辞書で検出できない表記の産地を明示する(商品ID: 産地)
ORIGIN_OVERRIDES = {'96618810': 'ブラジル'}

# 商品名の語から誤判定される/名称に記載がない精選方法を、商品ページの記載に合わせて上書きする(商品ID: 精選方法)
PROCESSING_OVERRIDES = {}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id: str, name: str, weight_g: int | None, category_override: str | None, roast_level: str | None) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    desc = re.sub(r"\s+", " ", desc_m.group(1)).strip()[:400] if desc_m else None
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

    if item_id in PROCESSING_OVERRIDES:
        parsed["processing_method"] = PROCESSING_OVERRIDES[item_id]

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
    with open("data_motoazaburoastery.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_motoazaburoastery.json に出力しました")


if __name__ == "__main__":
    main()
