# -*- coding: utf-8 -*-
"""
scrape_storyboxcoffeeroaster.py

STORY BOX & coffee roaster(https://storycoffee.base.shop/、神奈川県大和市中央2-7-1 1R)の商品情報を取得する。BASE。

【店舗発見の経緯】
全国再調査(神奈川県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10-21時点): 国内発送の豆(シングル・ブレンド・デカフェ)14銘柄を収録(うち品切れ6)。1kg大容量、COFFEE BAG(ディップ)、お試し/ギフトセット、海外発送用の同一銘柄ページ(for overseas)は対象外。SEASONAL BLEND #03は構成に「China - Infused washed 25%」(インフューズド)を含むため除外。重量は商品名の表記(150g、Limitedは100g)。焙煎度は店の方針(浅煎り〜中浅煎り)のみで商品別の表記が無いため未設定。
商品名・重量・焙煎度は、商品ページの表記を確認したうえで下のITEMSに明示している。
価格・在庫(item_purchasability)・説明(og:description)は商品ページから取得する。
BASEの商品ページは1商品1価格(バリエーションは在庫のみ)のため、価格は商品ページの表示価格をそのまま採用する。

【実店舗・自家焙煎の根拠】
Walkerplus「コーヒーで旅する日本/関東編」(https://www.walkerplus.com/article/1442196/)に所在地「神奈川県大和市中央2-7-1 1R」「大和駅からほど近く、住宅街に佇む」「焙煎機はポルトガル製「Joper(ジーパー)」を使用」「基本的に浅煎り」。神奈川新聞カナロコ(https://www.kanaloco.jp/news/culture/bunka/article-1014399.html)にも大和駅徒歩3分の店として掲載。販売ページABOUT「素材の個性を最大限引き出せる焙煎を追求し、浅煎り〜中浅煎りに焙煎したコーヒー豆」、特商法に営業時間9:30〜18:30・定休日(火曜、第三水曜)。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用し、リクエスト間隔を5秒以上空ける。
"""

import html as html_lib
import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "STORY BOX & coffee roaster",
    "url": "https://storycoffee.base.shop/",
    "platform": "BASE",
    "address": "神奈川県大和市中央2-7-1 1R",
    "prefecture": "神奈川県",
    "robots_txt_status": "実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用)",
    "source_note": "BASE(https://storycoffee.base.shop/)のsitemap.xmlの全商品ページとABOUT・特商法ページを2026-10-21に確認。販売中の商品の最終更新は2026-08〜2026-10。住所は特商法・Walkerplusの表記",
    "last_verified_at": "2026-10-21",
}

BASE_URL = "https://storycoffee.base.shop"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL_SEC = 5.0

# (商品ID, 商品名, 重量(g)(不明はNone), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名・説明文から判定))
ITEMS = [
    ('158126872', 'ルワンダ HUYE MOUNTAIN', 150, None, None),
    ('155265999', 'ケニア GUAMA', 150, None, None),
    ('150117777', 'エチオピア DIMTU', 150, None, None),
    ('137867035', 'エチオピア CHELCHELE', 150, None, None),
    ('71201184', 'ブラジル ALMOND CHOCCY（ESPRESSO）', 150, None, None),
    ('91326130', 'ブラジル DECAF', 150, None, None),
    ('132818925', 'コロンビア OSCAR GEISHA WASHED（Limited）', 100, None, None),
    ('147940830', 'SEASONAL BLEND #02 LONG VACATION', 150, 'ブレンド', None),
    ('123287196', 'SEASONAL BLEND #01 DAILY DRIFT', 150, 'ブレンド', None),
    ('131884415', 'コロンビア LA ROCA TIPYCA HONEY（Limited）', 100, None, None),
    ('122072549', 'エチオピア SEDAKA', 150, None, None),
    ('118970167', 'エチオピア DESTA GOLO', 150, None, None),
    ('110593737', 'タンザニア ACACIA HILLS', 150, None, None),
    ('137246756', 'コロンビア LAS PERLITAS', 150, None, None),
]

# coffee_parser.pyの国名辞書で検出できない表記の産地を明示する
ORIGIN_OVERRIDES = {}

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
BEAN_OUT_PATTERN = re.compile(r'<option[^>]*data-stock="0"[^>]*>\s*在庫なし[:：]\s*豆')
ROAST_LABEL_PATTERN = re.compile(r"焙煎度[：:]\s*(極深煎り|中深煎り|中浅煎り|浅煎り|中煎り|深煎り)")


def build_record(item_id: str, name: str, weight_g, category_override, roast_level) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    html_text = resp.text

    desc_m = DESC_PATTERN.search(html_text)
    raw_desc = html_lib.unescape(desc_m.group(1)) if desc_m else ""
    desc = re.sub(r"\s+", " ", raw_desc).strip()[:400] or None
    price_m = PRICE_PATTERN.search(html_text)
    purchasability_m = PURCHASABILITY_PATTERN.search(html_text)
    # 全バリエーション在庫なし、または「豆のまま」バリエーションが在庫なし(粉のみ在庫あり)の場合は品切れ扱い
    sold_out = (bool(purchasability_m) and purchasability_m.group(1) == "unpurchasable") or bool(BEAN_OUT_PATTERN.search(html_text))

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

    roast = roast_level or parsed["roast_level"]
    if not roast:
        label_m = ROAST_LABEL_PATTERN.search(raw_desc)
        if label_m:
            roast = label_m.group(1)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast,
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
        finally:
            time.sleep(REQUEST_INTERVAL_SEC)
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_storyboxcoffeeroaster.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_storyboxcoffeeroaster.json に出力しました")


if __name__ == "__main__":
    main()
