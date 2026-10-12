# -*- coding: utf-8 -*-
"""
scrape_tomikawacoffee.py

コーヒーのとみかわ(https://tomikawa.theshop.jp/、富山県魚津市仏又556-2)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(富山県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): sitemap上の約70商品のうち、ドリップバッグ・アイスコーヒー1Lパック・インスタントを除く煎豆。同一銘柄が200g/500g(一部300g/500g)で別ページのため最小重量を代表として収録した32商品。焙煎度は商品説明に明記がある場合のみ採用。住所は/lawで確認済み。
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している
(商品ページのタイトルがキャッチコピー付き・重量違いの重複登録のため)。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import json
import re

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "コーヒーのとみかわ",
    "url": "https://tomikawa.theshop.jp/",
    "platform": "BASE",
    "address": "富山県魚津市仏又556-2",
    "prefecture": "富山県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://tomikawa.theshop.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [('15232360', 'オリジナルAブレンド', 200, 'ブレンド', None),
 ('15232402', 'オリジナルBブレンド', 200, 'ブレンド', None),
 ('15232380', 'オリジナルBRブレンド', 200, 'ブレンド', None),
 ('15223162', 'アイスコーヒーブレンド', 200, 'ブレンド', None),
 ('15232647', 'アメリカンブレンド', 200, 'ブレンド', None),
 ('15232615', 'ゴールデンブレンド', 200, 'ブレンド', None),
 ('15232490', 'スペシャルブレンド', 200, 'ブレンド', None),
 ('15232431', 'ミラージュロイヤルブレンド', 200, 'ブレンド', None),
 ('15223095', 'メキシコブレンド', 200, 'ブレンド', None),
 ('15232701', 'モカクイーンブレンド', 200, 'ブレンド', None),
 ('15232537', 'モカブレンド', 200, 'ブレンド', None),
 ('29722284', 'ヨーロピアンブレンド', 200, 'ブレンド', None),
 ('15232516', 'ローヤルブレンド', 200, 'ブレンド', None),
 ('29703055', 'ブルーマウンテンブレンド', 200, 'ブレンド', None),
 ('29469782', 'インドネシア マンデリン G-1', 200, None, None),
 ('15223572', 'エチオピアモカ イルガチェフ G2 WS', 200, None, None),
 ('15223517', 'エチオピア モカ シダモ ウォッシュド', 200, None, None),
 ('34533780', 'グアテマラ SHB サンタバーバラ', 200, None, None),
 ('15223070', 'カフェインレス コスタリカ', 300, None, None),
 ('15223380', 'キリマンジャロ タンザニアAA', 200, None, None),
 ('17153864', 'グアテマラ SHB', 200, None, None),
 ('15217755', 'コロンビア スプレモ', 200, None, None),
 ('29109705', 'タンザニア マサマキリマンジャロ', 200, None, None),
 ('15215021', 'ブラジル サントス No.2 17/18', 200, None, None),
 ('15215036', 'ブラジル サントス ピーベリー', 200, None, None),
 ('15215077', 'ブルーマウンテン No.1', 300, None, None),
 ('15232232', 'ペルー G2', 200, None, None),
 ('15215101', 'ホンジュラス HG', 200, None, None),
 ('15214537', 'メキシコ AL', 200, None, None),
 ('15217828', '天空のコロンビア', 200, None, None),
 ('29534040', '有機栽培 コロンビア ラカバニア', 200, None, None),
 ('17085488', 'ケニア AA', 200, None, None)]

# coffee_parser.pyの国名辞書で検出できない表記(「タイ」「中国」「ケニヤ」等)の産地を明示する
ORIGIN_OVERRIDES = {}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


ROAST_IN_DESC = re.compile(r"(中浅煎り|中深煎り|浅煎り|中煎り|深煎り|フレンチロースト|シティロースト|ハイロースト)")


def roast_from_desc(desc: str | None) -> str | None:
    """商品説明に焙煎度の明記がある場合のみ採用する(無ければNone)。
    ゴールデンブレンドは浅煎りと深煎りの混合のため単一の焙煎度にせずNoneとする。"""
    if desc and "浅煎りと深煎りのコーヒー豆をブレンド" in desc:
        return None
    m = ROAST_IN_DESC.search(desc or "")
    return m.group(1) if m else None


def build_record(item_id: str, name: str, weight_g: int, category_override: str | None, roast_level: str | None) -> dict | None:
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

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level or parsed["roast_level"] or roast_from_desc(desc),
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
    with open("data_tomikawacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_tomikawacoffee.json に出力しました")


if __name__ == "__main__":
    main()
