# -*- coding: utf-8 -*-
"""
scrape_marqcoffee.py

marQ coffee(https://marqcoffee.thebase.in/、福井県敦賀市野坂69-25-1)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(北陸3県)の新規発掘で発見(2026-11)。

【実店舗・自家焙煎の根拠(2026-11-03確認)】
公式 https://coffeemarq.wixsite.com/marqcoffee に「914-0145 福井県敦賀市野坂69-25-1」「野坂岳の麓にある コーヒー豆焙煎所です。」(TEL 0770-36-4047)。食べログ https://tabelog.com/fukui/A1803/A180301/18007475/ にも「マルクコーヒー(marQ coffee)」「福井県敦賀市野坂69-25-1」(コーヒースタンド)。BASE about に「約40種類のコーヒー生豆からお好みのものを、ご注文いただいてから焙煎します」。

【対象商品について】
実データ確認済み(2026-11-03時点): BASE全24商品のうち豆17商品(ブレンド3・シングル12・デカフェ1・水出し用ブレンド1を含む)。定期便3・セット2・ドリップバッグセット・キャニスターは除外。商品名に100gと明記のある13品は100g、重量記載が無い4品(ピクニック・BLEND#1・アリーチャ・ドミニカ)はNone。ピクニックは10%OFF価格(855円、通常950円)。
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。

【robots.txtについて】
marqcoffee.thebase.in の robots.txt を2026-11-03に確認。User-Agent: * は /cart/ /web_cart/ /shops/ 等のみ Disallow で、商品ページ(/items/)・カテゴリは許可。
BASEの robots.txt は python-requests/curl 等を個別に Disallow しているため、識別可能な
独自User-Agentを使用し、リクエスト間隔は5秒以上空ける。
"""

import html as html_lib
import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "marQ coffee",
    "url": "https://marqcoffee.thebase.in/",
    "platform": "BASE",
    "address": "福井県敦賀市野坂69-25-1",
    "prefecture": "福井県",
    "robots_txt_status": "実質許可(2026-11-03確認。Disallowは/cart/等のみ。python-requests/curl等は個別禁止のため識別可能なUser-Agentを使用)",
    "source_note": "https://marqcoffee.thebase.in/ (BASE商品ページ2026-11-03確認)、住所は公式Wix・食べログ(2026-11-03確認)。冬の推し豆・春ブレンド等あり、更新は新しい",
    "last_verified_at": "2026-11-03",
}

BASE_URL = "https://marqcoffee.thebase.in"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
CRAWL_DELAY_SECONDS = 5

# (商品ID, 商品名, 重量(g)(商品ページに記載が無ければNone), 分類の上書き, 焙煎度(Noneなら商品名から判定))
ITEMS = [('136547292', '春をイメージしたブレンド「ピクニック」', None, 'ブレンド', None),
 ('80703430', "オリジナルブレンド haven't we met BLEND#1", None, 'ブレンド', None),
 ('32842616', '水出しコーヒー用 COLD BREW BLEND', 100, 'ブレンド', None),
 ('109127705', 'エチオピア イルガチェフェ アリーチャ ナチュラルG1', None, 'ストレート', None),
 ('27895303', 'ドミニカ プリンセサ ワイニー ナチュラル', None, 'ストレート', None),
 ('78396394', 'モカ グジ G-4 プラス ナチュラル(エチオピア)', 100, 'ストレート', None),
 ('71445411', 'ケニア マサイAA', 100, 'ストレート', None),
 ('22091271', 'タンザニア ンゴロンゴロ AA++', 100, 'ストレート', None),
 ('5025337', 'ブラジル ショコラ ピーベリー', 100, 'ストレート', None),
 ('5025019', 'トミオフクダ DOT バウー農園(ブラジル)', 100, 'ストレート', None),
 ('58381620', 'メキシコ デカフェ', 100, 'デカフェ', None),
 ('5025318', 'サントス No.2(ブラジル)', 100, 'ストレート', None),
 ('5025003', 'マンデリン G-1(インドネシア)', 100, 'ストレート', None),
 ('5025347', 'グァテマラ ウェウェティナンゴ(グァテマラ)', 100, 'ストレート', None),
 ('5146198', 'イルガチェフェ G-1ウォッシュド(エチオピア)', 100, 'ストレート', None),
 ('5025053', 'チャンチャマイヨ(ペルー)', 100, 'ストレート', None),
 ('4994867', 'シダモG-2(エチオピア)', 100, 'ストレート', None)]

# 産地(日本語の国名)を明示する(ブレンドは対象外)
ORIGIN_OVERRIDES = {'109127705': 'エチオピア',
 '27895303': 'ドミニカ共和国',
 '78396394': 'エチオピア',
 '71445411': 'ケニア',
 '22091271': 'タンザニア',
 '5025337': 'ブラジル',
 '5025019': 'ブラジル',
 '58381620': 'メキシコ',
 '5025318': 'ブラジル',
 '5025003': 'インドネシア',
 '5025347': 'グアテマラ',
 '5146198': 'エチオピア',
 '5025053': 'ペルー',
 '4994867': 'エチオピア'}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id: str, name: str, weight_g: int | None, category_override: str | None, roast_level: str | None) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    desc = None
    if desc_m:
        desc = re.sub(r"\s+", " ", html_lib.unescape(desc_m.group(1))).strip()[:400] or None
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
    for i, (item_id, name, weight_g, category_override, roast_level) in enumerate(ITEMS):
        if i:
            time.sleep(CRAWL_DELAY_SECONDS)
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
    with open("data_marqcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_marqcoffee.json に出力しました")


if __name__ == "__main__":
    main()
