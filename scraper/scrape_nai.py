# -*- coding: utf-8 -*-
"""
scrape_nai.py

nai(https://naicoffee.thebase.in/、長崎県諫早市幸町13-17)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(長崎県)の新規発掘で発見。

【住所について】
BASEの特定商取引法ページ(/law)の事業者所在地「〒854-0022 長崎県諫早市幸町13−17」(営業時間10:00-17:00、定休日木曜日)を採用。

【対象商品について】
実データ確認済み(2026-10時点): BASE全32商品のうち自家焙煎のコーヒー豆6銘柄(コスタリカ2・ケニア2・ブラジル・ブレンド。うち1件は6周年限定のゲイシャ)。
同一銘柄が200g/400gで別ページの場合は小さい200gを代表とし、ゲイシャのみ100g。
1kgパック・水出しコーヒーパック・ドリップバッグ・飲み比べ/初めてセット・ギフトボックス・Tシャツ等雑貨・コーヒーミルは除外。
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している
(商品ページのタイトルが焙煎度付き・重量違いの重複登録のため)。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。

【アクセス間隔について】
BASEは連続アクセスで429になりやすいため、リクエスト間隔を5秒とし、429を受けた場合は
30秒ずつ待機を延ばして再試行する(最大4回。それでも取れなければ諦めて警告を出す)。
ボット判定の回避は行わず、識別可能なUser-Agentを使用する。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用する。
"""

import html
import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "nai",
    "url": "https://naicoffee.thebase.in/",
    "platform": "BASE",
    "address": "長崎県諫早市幸町13-17",
    "prefecture": "長崎県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
}

BASE_URL = "https://naicoffee.thebase.in"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 5
RETRY_WAIT_STEP_SECONDS = 30
MAX_RETRIES = 4

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定))
ITEMS = [
    ('153224543', '6周年限定豆 コスタリカ サンタテレサ2000 ゲイシャ種', 100, 'ストレート', None),
    ('158991852', '浅煎り コスタリカ イバン グティエレス', 200, 'ストレート', '浅煎り'),
    ('158992453', '浅煎り ケニア ケグア', 200, 'ストレート', '浅煎り'),
    ('150223880', '浅煎り ブラジル イナシオ ウルバン', 200, 'ストレート', '浅煎り'),
    ('28322915', '中深煎り nai blend', 200, 'ブレンド', '中深煎り'),
    ('158992303', '深煎り ケニア カリアイニ', 200, 'ストレート', '深煎り'),
]

# coffee_parser.pyの国名辞書で検出できない表記の産地を明示する
ORIGIN_OVERRIDES = {'153224543': 'コスタリカ'}

# 商品説明の「精製処理」表記で確認した精製方法
PROCESSING_OVERRIDES = {'153224543': 'ハニー', '158991852': 'ハニー', '158992453': 'ウォッシュド', '150223880': 'ナチュラル', '158992303': 'ウォッシュド'}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")

_last_request = [0.0]


def fetch_item_html(item_id: str) -> str:
    """5秒間隔で取得し、429なら30秒ずつ待機を延ばして再試行する。"""
    wait = CRAWL_DELAY_SECONDS - (time.time() - _last_request[0])
    if wait > 0:
        time.sleep(wait)
    retry_wait = RETRY_WAIT_STEP_SECONDS
    for _ in range(MAX_RETRIES):
        resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
        _last_request[0] = time.time()
        if resp.status_code == 429:
            print(f"[warn] 429: {retry_wait}秒待機して再試行 item_id={item_id}")
            time.sleep(retry_wait)
            retry_wait += RETRY_WAIT_STEP_SECONDS
            continue
        resp.raise_for_status()
        resp.encoding = "utf-8"
        return resp.text
    raise requests.RequestException(f"429が解消しない: item_id={item_id}")


def build_record(item_id: str, name: str, weight_g: int, category_override: str | None, roast_level: str | None) -> dict | None:
    html_text = fetch_item_html(item_id)

    desc_m = DESC_PATTERN.search(html_text)
    desc = re.sub(r"\s+", " ", html.unescape(desc_m.group(1))).strip()[:400] if desc_m else None
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
    with open("data_nai.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_nai.json に出力しました")


if __name__ == "__main__":
    main()
