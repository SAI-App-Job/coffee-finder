# -*- coding: utf-8 -*-
"""
scrape_koyacoffee.py

小屋珈琲(https://koyacoffee.theshop.jp/、岡山県岡山市北区下足守757)の商品情報を取得する。BASE。

【店舗について】
aboutに「受け継いだ焙煎機とともに…自家焙煎を始めました」「焙煎所は山々に囲まれた静かな谷にあります」「火曜日と木曜日が焙煎日」「注文を受けてから必要な分だけ焙煎」。
同時に「小屋での喫茶営業はしていません。ドリンク販売はイベント出店」とあるため、実店舗(店頭販売)の有無は未確認。
現在のサイトマップ(32商品)には100g商品がなく(100g商品カテゴリは空)、最小重量は全銘柄200g。
各銘柄は200g/600g/1000gが別商品なので200gを代表にする。同じ銘柄で焙煎度違い(中深煎り/極深煎り)は別商品として出力。ドリップバッグ・ドリッパーは除外。

【robots.txtについて】
2026-11-02確認: User-agent: * は Allow: / で、Disallow は /cart/ /web_cart/ /shops/ 等のみ。
python-requests/curl 等は個別に Disallow: / 指定のため、本スクレイパーは識別可能な
独自User-Agent(CoffeeFinderBot)を使用し、リクエスト間隔は5秒以上とする。

【対象商品の選定について】
実データ確認済み(2026-11-02): 下のITEMSは、サイトマップ/カテゴリ一覧の全商品から
豆(シングルオリジン・ブレンド・デカフェ)のみを選んだもの。ドリップバッグ・セット・
ギフト・雑貨・水出しパック等は除外。同一銘柄が重量違いで並ぶ場合は最小重量の商品を
代表にしている。商品名・重量・焙煎度は商品ページの表記を確認したうえでITEMSに明示している。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。
"""

import html
import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "小屋珈琲",
    "url": "https://koyacoffee.theshop.jp/",
    "platform": "BASE",
    "address": "岡山県岡山市北区下足守757",
    "prefecture": "岡山県",
    "robots_txt_status": "実質許可(2026-11-02確認。User-agent: * は Allow: / で /cart/ 等のみ禁止。python-requests/curl等は個別にDisallow: /指定のため識別可能なUser-Agentを使用、間隔5秒以上)",
    "source_note": "BASEショップ(https://koyacoffee.theshop.jp/)のabout・特商法・サイトマップ・全商品ページを2026-11-02に確認。住所は特商法の「〒701-1464 岡山県岡山市北区下足守757」、食べログも同住所。最新ブログは2025-01-29(2025-03-01の豆価格改定告知)と古めだが商品は全て販売中表示。aboutに「小屋での喫茶営業はしていません」とあり店頭販売の有無は未確認(焙煎所はあり)",
    "last_verified_at": "2026-11-02",
}

BASE_URL = "https://koyacoffee.theshop.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL = 5.2  # BASEは5秒以上

# (商品ID, 商品名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定), 産地の上書き(Noneなら自動))
ITEMS = [
    ('112722592', 'あらいぐまブレンドⅥ [200g] 自家焙煎珈琲豆 小屋珈琲のブレンド', 200, 'ブレンド', '中深煎り', None),
    ('28131897', 'ごりらブレンドⅢ [200g] 珈琲豆 自家焙煎珈琲 極深煎りの重厚なブレンド珈琲', 200, 'ブレンド', '極深煎り', None),
    ('112720690', '【インドネシア】マンデリンビンタンリマ [200g] 極深煎り 自家焙煎珈琲', 200, None, '極深煎り', None),
    ('112719202', '【インドネシア】マンデリンビンタンリマ [200g] 中深煎り 自家焙煎珈琲', 200, None, '中深煎り', None),
    ('112707614', '【ケニア】マサイAA [200g] 極深煎り 自家焙煎珈琲', 200, None, '極深煎り', None),
    ('112706080', '【ケニア】マサイAA [200g] 中深煎り 自家焙煎珈琲', 200, None, '中深煎り', None),
    ('112704937', '【ブラジル】プレミアムショコラ [200g] 中深煎り 自家焙煎珈琲', 200, None, '中深煎り', None),
    ('112703317', '【ルワンダ】スカイヒル コプロカWS [200g] 中深煎り 自家焙煎珈琲', 200, None, '中深煎り', None),
    ('112699690', '【タンザニア】サウステラAA [200g] 浅煎り 自家焙煎珈琲', 200, None, '浅煎り', None),
]

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def build_record(item_id, name, weight_g, category_override, roast_level, origin_override):
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    if resp.status_code != 200:
        print(f"[warn] 取得失敗(回避せずスキップ): item_id={item_id} status={resp.status_code}")
        return None
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    desc = re.sub(r"\s+", " ", html.unescape(desc_m.group(1))).strip()[:400] if desc_m else None
    price_m = PRICE_PATTERN.search(html_text)
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    # unpurchasable=全バリエーション購入不可(品切れ)。partially_purchasable=一部のみ不可なので販売中扱い
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


def scrape_all_products():
    records = []
    for i, (item_id, name, weight_g, category_override, roast_level, origin_override) in enumerate(ITEMS):
        if i:
            time.sleep(REQUEST_INTERVAL)
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
    with open("data_koyacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_koyacoffee.json に出力しました")


if __name__ == "__main__":
    main()
