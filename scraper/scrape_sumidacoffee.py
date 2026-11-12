# -*- coding: utf-8 -*-
"""
scrape_sumidacoffee.py

すみだ珈琲(https://shop.sumidacoffee.jp/、東京都墨田区太平4-7-11)の商品情報を取得する。BASE(独自ドメイン)。

【店舗発見の経緯】
全国再調査(東京都東部・北部)の新規発掘で発見。

【確認内容(2026-10-21)】
BASE独自ドメイン https://shop.sumidacoffee.jp/ の商品ページ(sitemap.xml)・特商法(/law)を2026-10-21に確認。公式 http://sumidacoffee.jp/about/ に「自家焙煎したスペシャルティコーヒー」、/access/ に本店(墨田区太平4-7-11)。豆6銘柄(200g)を採用。1kg大容量・COFFEE BAG(ドリップバッグ)・COFFEE LIQUID・ギフト・雑貨は除外。デカフェ メキシコは商品ページに内容量の記載が無くweight_gはnull。やや深煎りは中深煎りとして記録。

【対象商品について】
商品名・重量・焙煎度・産地は、商品ページの表記を確認したうえで下のITEMSに明示している。
価格・在庫(item_purchasability)・説明文は商品ページから実行時に取得する。
ITEMSにもEXCLUDED_IDSにも無い商品がsitemap.xmlに現れた場合は、新商品の可能性があるため
警告を表示する(自動では収録しない)。

【robots.txtについて】
BASE系の標準的な記述(python-requests/curl等は個別にDisallow、User-agent: *では
許可)。本スクレイパーは識別可能な独自User-Agentを使用し、リクエスト間隔は5秒以上とする。
"""

import html
import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "すみだ珈琲",
    "url": "https://shop.sumidacoffee.jp/",
    "platform": "BASE(独自ドメイン)",
    "address": "東京都墨田区太平4-7-11",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(BASE系の標準的な記述。python-requests/curl等のみ個別にDisallowで、識別可能なUser-Agentを使用。間隔5秒以上)",
    "source_note": "BASE独自ドメイン https://shop.sumidacoffee.jp/ の商品ページ(sitemap.xml)・特商法(/law)を2026-10-21に確認。公式 http://sumidacoffee.jp/about/ に「自家焙煎したスペシャルティコーヒー」、/access/ に本店(墨田区太平4-7-11)。豆6銘柄(200g)を採用。1kg大容量・COFFEE BAG(ドリップバッグ)・COFFEE LIQUID・ギフト・雑貨は除外。デカフェ メキシコは商品ページに内容量の記載が無くweight_gはnull。やや深煎りは中深煎りとして記録。",
    "last_verified_at": "2026-10-21",
}

BASE_URL = "https://shop.sumidacoffee.jp"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL = 5

# (商品ID, 商品名, 重量(g)(不明ならNone), 分類の上書き(Noneなら自動判定), 焙煎度(商品ページに明記があるものだけ), 産地(ブレンドはNone))
ITEMS = [('10345608', 'すみだブレンド 深煎り', 200, 'ブレンド', '深煎り', None),
 ('10353376', 'すみだブレンド やや深煎り', 200, 'ブレンド', '中深煎り', None),
 ('10353500', 'すみだブレンド 浅煎り', 200, 'ブレンド', '浅煎り', None),
 ('10353583', 'インドネシア マンデリン 深煎り', 200, None, '深煎り', 'インドネシア'),
 ('10353865', 'エチオピア やや深煎り', 200, None, '中深煎り', 'エチオピア'),
 ('104091562', 'デカフェ メキシコ', None, None, None, 'メキシコ')]

# 豆以外(ドリップバッグ・セット・ギフト・定期便・器具・雑貨・インフューズド等)や大容量のみの商品など、収録しないsitemap上の商品ID
EXCLUDED_IDS = {'10345086', '59241075', '43749544', '10345002', '57686032', '89481210', '57869391', '89482118', '29982719', '147186132', '63063251', '30584521', '62856844', '89484019', '62857938', '24956392', '10282883', '83550789', '10354496', '62857574', '89484108', '89478980'}

# 説明文の整形: 開始マーカー(あれば以降を使う)、この文字列以降は切る、この文字列で始まる行は捨てる
DESC_START_MARKER = None
DESC_CUT_MARKERS = ['原材料']
DESC_DROP_LINE_PREFIXES = []

PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')
PURCHASABILITY_PATTERN = re.compile(r"item_purchasability['\"]:\s*['\"]([a-z_]+)['\"]")


def clean_description(soup: BeautifulSoup) -> str | None:
    el = soup.select_one('[class*="item-detail_description"]')
    if el:
        text = el.get_text("\n")
    else:
        og = soup.select_one('meta[property="og:description"]')
        text = og.get("content", "") if og else ""
    text = html.unescape(text)
    if DESC_START_MARKER and DESC_START_MARKER in text:
        text = text.split(DESC_START_MARKER, 1)[1]
    lines = [ln.strip() for ln in text.split("\n")]
    lines = [ln for ln in lines if ln and not any(ln.startswith(p) for p in DESC_DROP_LINE_PREFIXES)]
    text = re.sub(r"\s+", " ", " ".join(lines)).strip()
    cut = len(text)
    for marker in DESC_CUT_MARKERS:
        idx = text.find(marker)
        if idx > 0:
            cut = min(cut, idx)
    return text[:cut].strip()[:400] or None


def build_record(item_id: str, name: str, weight_g: int | None, category_override: str | None,
                 roast_level: str | None, origin: str | None) -> dict | None:
    resp = requests.get(f"{BASE_URL}/items/{item_id}", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    html_text = resp.text
    soup = BeautifulSoup(html_text, "html.parser")

    desc = clean_description(soup)
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
        if origin:
            parsed["origin_country"] = origin
            parsed["origin_source"] = "raw_name" if origin in name else "product_description"
        parsed = apply_category_hint_fallback(parsed, name)

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


def check_new_items() -> None:
    """sitemap.xmlに未分類の商品があれば警告する(収録はしない)。"""
    try:
        resp = requests.get(f"{BASE_URL}/sitemap.xml", headers=REQUEST_HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[warn] sitemap取得失敗 ({e})")
        return
    known = {item[0] for item in ITEMS} | set(EXCLUDED_IDS)
    for item_id in dict.fromkeys(re.findall(r"/items/(\d+)", resp.text)):
        if item_id not in known:
            print(f"[warn] 未分類の商品がsitemapにあります: {BASE_URL}/items/{item_id}")
    time.sleep(REQUEST_INTERVAL)


def scrape_all_products() -> list[dict]:
    records = []
    for item_id, name, weight_g, category_override, roast_level, origin in ITEMS:
        try:
            record = build_record(item_id, name, weight_g, category_override, roast_level, origin)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: item_id={item_id} ({e})")
            continue
        finally:
            time.sleep(REQUEST_INTERVAL)
        if record is not None:
            records.append(record)
    return records


def main():
    check_new_items()
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_sumidacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_sumidacoffee.json に出力しました")


if __name__ == "__main__":
    main()
