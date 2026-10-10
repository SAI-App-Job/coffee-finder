# -*- coding: utf-8 -*-
"""
scrape_amian.py

カフェ・ド・アミアン(新潟県長岡市寺島町713、公式 www.amian.co.jp)のYahoo!ショッピング
ストア(store.shopping.yahoo.co.jp/amian-coffee、ストア名「アミアンコーヒー」、運営は
有限会社渡辺フアミリー)の商品情報を取得する。

【住所】店舗住所は公式サイト(https://www.amian.co.jp/)記載の「新潟県長岡市寺島町713」。
Yahoo!ショッピングの会社概要の住所(長岡市藤沢1-8-14)は法人所在地のため採用しない。

【対象商品】search.html(全9件)の__NEXT_DATA__から取得し、コーヒー豆6点(ストレート3:
グアテマラSHB・タンザニアAA・ブラジル サントスNo2、ブレンド3:アイスコーヒーブレンド・
ダークローストブレンド・マイルドブレンド、いずれも200g)を対象。ドリップバッグギフト、
アイスコーヒーリキッド2点は除外。商品名は「送料無料 コーヒー豆 ...」とSEO文が長いため
DISPLAY_NAMESで整形名を与える。焙煎度は詳細ページの『焙煎度合/焙煎…』記載による
(ダークローストブレンドは記載なしのため商品名の深煎りブレンドから深煎り)。

robots.txt: store.shopping.yahoo.co.jpはUser-agent: *に対し/cgi-bin/等のみDisallow。
"""

import html
import json
import re

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "カフェ・ド・アミアン",
    "url": "https://store.shopping.yahoo.co.jp/amian-coffee/",
    "platform": "Yahoo!ショッピング",
    "address": "新潟県長岡市寺島町713",
    "prefecture": "新潟県",
    "robots_txt_status": "実質許可(Yahoo!ショッピング標準。/cgi-bin/等のみDisallow、search.htmlは取得可)",
}

BASE_URL = "https://store.shopping.yahoo.co.jp/amian-coffee"
SEARCH_URL = f"{BASE_URL}/search.html"
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; CoffeeFinderBot/0.1; +contact: your-contact-info-here)"
}
NEXT_DATA_PATTERN = re.compile(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)

# (URL末尾のコード) -> (整形名, ブレンドか, 焙煎度の補完)
DISPLAY_NAMES = {
    "shb-200s0": ("グアテマラSHB", False, None),
    "aa-200s0": ("タンザニアAA(キリマンジャロ)", False, None),
    "amino2-200s0": ("ブラジル サントスNo2 スクリーン18", False, None),
    "ac-200s0": ("アイスコーヒーブレンド(アイスコーヒー豆)", True, None),
    "es-200s0": ("ダークローストブレンド", True, "深煎り"),
    "mbl200": ("マイルドブレンド", True, None),
}
ROAST_PATTERN = re.compile(r"(?:焙煎度合】|焙煎…)\s*(やや深煎り|中深煎り|中浅煎り|浅煎り|中煎り|深煎り)")


def fetch_items() -> list[dict]:
    resp = requests.get(SEARCH_URL, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    m = NEXT_DATA_PATTERN.search(resp.content.decode("utf-8"))
    data = json.loads(m.group(1))
    return data["props"]["initialState"]["bff"]["searchResults"]["items"]["1"][1]["content"]["items"]


def fetch_detail(url: str) -> tuple[str | None, bool]:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    text = resp.content.decode("utf-8", "replace")
    dm = re.search(r'og:description" content="([^"]*)"', text)
    desc = html.unescape(dm.group(1)).replace("<br>", "\n") if dm else None
    in_stock = "schema.org/InStock" in text
    return desc, in_stock


def build_record(item: dict) -> dict | None:
    url = (item.get("url") or "").split("?")[0]
    code = url.rsplit("/", 1)[-1].replace(".html", "")
    if code not in DISPLAY_NAMES:
        return None
    name, is_blend, roast_fallback = DISPLAY_NAMES[code]
    desc, in_stock = fetch_detail(url)
    roast = None
    flavor = None
    if desc:
        rm = ROAST_PATTERN.search(desc)
        if rm:
            roast = {"やや深煎り": "中深煎り"}.get(rm.group(1), rm.group(1))
        lines = [l.strip() for l in desc.split("\n") if l.strip()]
        lines = [l for l in lines if not re.match(r"^(【?(内容量|挽き方|送料無料|焙煎|豆の挽き方)|※)", l.lstrip("　 "))]
        flavor = " ".join(lines)[:400] or None
    roast = roast or roast_fallback

    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        c = detect_country_name(name)
        if c and not parsed["origin_country"]:
            parsed["origin_country"] = c
            parsed["origin_source"] = "raw_name"
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
        "roast_level": roast or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": flavor,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item.get("price"),
        "weight_g": 200,
        "stock_status": "販売中" if in_stock else "完売",
        "out_of_stock": not in_stock,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in fetch_items():
        rec = build_record(item)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    with open("data_amian.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_amian.json に出力しました")


if __name__ == "__main__":
    main()
