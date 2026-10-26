# -*- coding: utf-8 -*-
"""
scrape_bearcoffee.py

BEARCOFFEE(https://bearcoffee.official.ec、大阪府泉南郡熊取町野田1-5-5)の商品情報を取得する。BASE(official.ecドメイン)。

【店舗発見の経緯】
大阪府の未登録店の発掘調査(2026-10-26)で発見。

【対象商品について】
実データ確認済み(2026-10-26時点): 全22商品のうち、焙煎豆13銘柄(ブレンド7・シングル6)を収録(すべて100g)。ドリップバッグ・セット・コールドブリューパックは除外。ミディアムブレンドは豆の選択肢が表示されていない(粉のみ)ため完売として収録する。
商品名・重量・焙煎度・産地は、商品ページの表記を確認したうえで下のITEMSに明示している。
価格・在庫・説明文は商品ページから取得する。

【在庫について】
購入ページのバリエーション(豆/粉)がある場合は、豆のバリエーションが全て在庫なしなら完売とする
(粉のみ在庫ありでも完売)。バリエーション表示が無い商品は item_purchasability が unpurchasable なら完売。

【robots.txtについて】
他のBASE系店舗と同一の記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用し、リクエスト間隔は5秒以上とする。
"""

import html
import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {'name': 'BEARCOFFEE',
 'url': 'https://bearcoffee.official.ec/',
 'platform': 'BASE',
 'address': '大阪府泉南郡熊取町野田1-5-5',
 'prefecture': '大阪府',
 'robots_txt_status': '実質許可(他のBASE系店舗と同一の記述。識別可能なUser-Agentを使用、取得間隔5秒以上)',
 'source_note': 'BASE店(https://bearcoffee.official.ec/)の全商品22件と各商品ページを2026-10-26に確認。住所・自家焙煎・カフェ店舗(14席)は公式サイト(https://bear-coffee.com/)で確認(2026-10-26確認)',
 'last_verified_at': '2026-10-26'}

BASE_URL = "https://bearcoffee.official.ec"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL_SEC = 5.0

# 商品ごとの明示情報。
#   id: 商品ID / name: 表示名 / weight: 代表(最小重量)のグラム数 / category: Noneなら自動判定
#   roast: 焙煎度 / roast_hint: 焙煎度の補足表記 / origin: 産地国の上書き
#   process: 精選方法の上書き / blend: ブレンドの構成国(判明分のみ) / farm: 農園・生産者の補足
ITEMS = [{'id': '156886942', 'name': 'グアテマラ エスヴィン・マラゴジッペ', 'weight': 100, 'origin': 'グアテマラ'},
 {'id': '39418308',
  'name': 'ケニア カンゴチョ ナチュラル',
  'weight': 100,
  'roast': '中煎り',
  'origin': 'ケニア',
  'process': 'ナチュラル',
  'farm': 'カンゴチョコーヒーファクトリー(ニエリ)'},
 {'id': '146571592', 'name': 'エチオピア アリーチャ レラ', 'weight': 100, 'roast': '浅煎り', 'origin': 'エチオピア', 'farm': 'イルガチェフェ・アリーチャ村'},
 {'id': '39418969',
  'name': 'ミャンマー ホーポン ナチュラル',
  'weight': 100,
  'roast': '中煎り',
  'roast_hint': 'ハイロースト',
  'origin': 'ミャンマー',
  'process': 'ナチュラル',
  'farm': 'シャン州ホーポン'},
 {'id': '39419343', 'name': 'オンライン限定 ブラジル No.2 カフェインレス', 'weight': 100, 'roast': '中深煎り', 'origin': 'ブラジル'},
 {'id': '39418622', 'name': 'グアテマラ カフェインレス', 'weight': 100, 'origin': 'グアテマラ'},
 {'id': '45704633',
  'name': 'オータムブレンド',
  'weight': 100,
  'category': 'ブレンド',
  'roast': '中煎り',
  'roast_hint': 'ハイロースト',
  'blend': [('ミャンマー', None), ('ブラジル', None)]},
 {'id': '39419406', 'name': '熊取ブレンド', 'weight': 100, 'category': 'ブレンド', 'blend': [('インドネシア', None)]},
 {'id': '39419415',
  'name': 'ライトブレンド',
  'weight': 100,
  'category': 'ブレンド',
  'roast': '中浅煎り',
  'roast_hint': 'ハイロースト程度',
  'blend': [('コロンビア', None), ('タンザニア', None)]},
 {'id': '39419424',
  'name': 'ミディアムブレンド',
  'weight': 100,
  'category': 'ブレンド',
  'roast': '中煎り',
  'blend': [('エチオピア', None), ('パナマ', None)]},
 {'id': '39419440', 'name': 'ダークブレンド', 'weight': 100, 'category': 'ブレンド', 'blend': [('ケニア', None), ('ブラジル', None)]},
 {'id': '39419450',
  'name': 'アイスブレンド',
  'weight': 100,
  'category': 'ブレンド',
  'roast': '深煎り',
  'roast_hint': 'フルシティロースト程度',
  'blend': [('グアテマラ', None), ('パプアニューギニア', None), ('インドネシア', None)]},
 {'id': '39419468',
  'name': 'エスプレッソブレンド',
  'weight': 100,
  'category': 'ブレンド',
  'roast': '深煎り',
  'roast_hint': 'フレンチロースト程度',
  'blend': [('ブラジル', None), ('エチオピア', None), ('インドネシア', None)]}]

DESC_PATTERN = re.compile(r'<meta property="og:description" content="([^"]*)"')
PRICE_PATTERN = re.compile(r"'itemPrice':\s*(\d+)")
PRICE_PATTERN2 = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")
VARIATION_PATTERN = re.compile(
    r'<p class="cot-itemOrder-variationName"[^>]*>([^<]*)</p>\s*'
    r'(?:<p class="cot-itemOrder-variationStock"[^>]*>([^<]*)</p>)?'
)
SELECT_PATTERN = re.compile(r'<select name="select" id="valiationSelect">(.*?)</select>', re.S)
OPTION_PATTERN = re.compile(r"<option[^>]*>(.*?)</option>", re.S)
GROUND_KEYWORDS = ("粉", "挽", "ドリップ")


def clean_text(s: str) -> str:
    s = re.sub(r"<br\s*/?>", " ", s)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def is_sold_out(html_text: str) -> bool:
    """豆(挽いていない)のバリエーションが全て在庫なしなら完売。バリエーションが無ければ購入可否で判定する。"""
    bean_variations = [
        (name, stock.strip())
        for name, stock in VARIATION_PATTERN.findall(html_text)
        if not any(k in name for k in GROUND_KEYWORDS)
    ]
    if bean_variations:
        return all(stock == "在庫なし" for _, stock in bean_variations)
    sel = SELECT_PATTERN.search(html_text)
    if sel:
        options = [clean_text(o) for o in OPTION_PATTERN.findall(sel.group(1))]
        if options and all(any(k in o for k in GROUND_KEYWORDS) for o in options):
            return True  # 豆の選択肢が(在庫切れで)表示されていない
    m = PURCHASABILITY_PATTERN.search(html_text)
    return bool(m) and m.group(1) == "unpurchasable"


def extract_description(html_text: str) -> str | None:
    m = DESC_PATTERN.search(html_text)
    desc = clean_text(m.group(1)) if m else ""
    if not desc:
        # og:description が空のテーマは、価格表示の直前にある商品説明を使う
        j = html_text.find('class="item_priceArea')
        if j > 0:
            seg = html_text[max(0, j - 3000):j]
            k = seg.find("商品説明")
            if k >= 0:
                seg = seg[k + 4:]
                seg = re.split(r"BEARCOFFEEでは|※一部商品", seg)[0]
                desc = clean_text(seg)
    desc = re.sub(r"-{3,}", " ", desc)
    return desc[:400] or None


def build_record(item: dict) -> dict | None:
    item_url = f"{BASE_URL}/items/{item['id']}"
    resp = requests.get(item_url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    html_text = resp.text

    desc = extract_description(html_text)
    price_m = PRICE_PATTERN.search(html_text) or PRICE_PATTERN2.search(html_text)
    sold_out = is_sold_out(html_text)

    name = item["name"]
    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if item.get("category"):
        parsed["category"] = item["category"]
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if item.get("origin"):
            parsed["origin_country"] = item["origin"]
            parsed["origin_source"] = "raw_name"
    if item.get("process"):
        parsed["processing_method"] = item["process"]

    blend_components = [{"origin_country": c, "percentage": p} for c, p in (item.get("blend") or [])]

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": item.get("roast") or parsed["roast_level"],
        "roast_hint": item.get("roast_hint"),
        "flavor_notes": desc,
        "farm_note": item.get("farm"),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": blend_components,
        "price": int(price_m.group(1)) if price_m else None,
        "weight_g": item["weight"],
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": item_url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for n, item in enumerate(ITEMS):
        if n:
            time.sleep(REQUEST_INTERVAL_SEC)
        try:
            record = build_record(item)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item['id']} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_bearcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_bearcoffee.json に出力しました")


if __name__ == "__main__":
    main()
