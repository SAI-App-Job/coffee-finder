# -*- coding: utf-8 -*-
"""
scrape_fivecoffeewakayama.py

珈琲専門店 ファイブ(和歌山県和歌山市四番丁55、公式 http://www.eonet.ne.jp/~five-coffee/ )の
Yahoo!ショッピングストア(store.shopping.yahoo.co.jp/5coffee)のコーヒー豆の商品情報を取得する。
※東京都台東区の「FIVE COFFEE STAND&ROASTERY」(scrape_fivecoffee.py)とは別の店(slugを分けている)。

【店舗発見の経緯】
全国再調査(和歌山県)の新規発掘で発見。

【取得方法】search.html (30件/ページ、?page=1,2 まで・全65件)の __NEXT_DATA__ から商品一覧を取り、
各商品ページの __NEXT_DATA__ (props.pageProps.item) から name / applicablePrice / information /
stock.isAvailable を読む。
【対象】注文後焙煎の自家焙煎豆(ストレート約60点+ホット/アイスブレンド)。基準は300g。
除外: 「詰合せ」(2種セット)、600g商品(いずれも同銘柄の300g商品が別にあるため最小重量の300gを代表とする)。
【焙煎度】商品説明は「深煎り浅煎りではなく豆に合った焙煎」とあり焙煎度の記載がないため null。
robots.txt: store.shopping.yahoo.co.jpはUser-agent: *に対し/cgi-bin/等のみDisallow。
"""

import json
import re
import time
import unicodedata

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "珈琲専門店 ファイブ",
    "url": "https://store.shopping.yahoo.co.jp/5coffee/",
    "platform": "Yahoo!ショッピング",
    "address": "和歌山県和歌山市四番丁55",
    "prefecture": "和歌山県",
    "robots_txt_status": "実質許可(Yahoo!ショッピング標準。/cgi-bin/等のみDisallow、search.htmlは取得可)",
}

BASE = "https://store.shopping.yahoo.co.jp/5coffee"
SEARCH_URLS = [BASE + "/search.html", BASE + "/search.html?page=1", BASE + "/search.html?page=2"]
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}
NEXT_DATA = re.compile(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)

EXCLUDE_WORDS = ["詰合せ", "詰め合わせ", "セット", "ドリップバッグ"]
BLEND_WORDS = ["ブレンド"]
# 名称から産地を判定できない銘柄の補正(名称キー部分一致 → 産地)
ORIGIN_OVERRIDES = {
    "ハイマウンテン": "ジャマイカ",
    "キューバTL": "キューバ",
    "トラジャ": "インドネシア",
    "ゴールデンマンデリン": "インドネシア",
    "マンデリン": "インドネシア",
    "カロシ": "インドネシア",
    "ジャバ": "インドネシア",
    "モカ": "エチオピア",
    "ガテマラ": "グアテマラ",
    "バリ": "インドネシア",
    "インド": "インド",
}


def get_next_data(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    t = r.content.decode("utf-8", "replace")
    return json.loads(NEXT_DATA.search(t).group(1))


def list_items():
    items = {}
    for u in SEARCH_URLS:
        d = get_next_data(u)
        try:
            sr = d["props"]["initialState"]["bff"]["searchResults"]["items"]
            sr = list(sr.values())[0]
        except Exception:
            break
        for blk in sr:
            if blk.get("type") != "PAGER" and isinstance(blk.get("content"), dict):
                for x in blk["content"].get("items", []):
                    items[x["url"].split("?")[0]] = x
        time.sleep(0.5)
    return items


def clean_html(s):
    s = re.sub(r"<br\s*/?>", "\n", s or "")
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return s.strip()


def split_name_weight(raw):
    """商品名から (表示名, 重量g) を取り出す。"""
    norm = unicodedata.normalize("NFKC", raw).replace("　", " ")
    norm = re.sub(r"\s+", " ", norm).strip()
    m = re.search(r"[(（]?\s*(\d+)\s*g\s*[)）]?", norm, re.IGNORECASE)
    weight = int(m.group(1)) if m else None
    name = norm
    name = re.sub(r"[(（]?\s*\d+\s*g\s*[)）]?", " ", name, flags=re.IGNORECASE)
    name = re.sub(r"(ネコポス便|コンパクト便)", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name, weight


def build_record(url, item):
    name, weight = split_name_weight(item["name"])
    is_blend = any(w in name for w in BLEND_WORDS)

    info = clean_html(item.get("information"))
    # 説明の冒頭(産地・農園の解説)のみを採用し、定型の保存・焙煎の注意書きは除く
    head = re.split(r"(ご注文を受け次第|焙煎の度合い|焙煎は深煎り)", info)[0]
    flavor = re.sub(r"\s*\n\s*", " ", head).strip()[:400] or None

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
        if not parsed["origin_country"]:
            for key, country in ORIGIN_OVERRIDES.items():
                if key in name:
                    parsed["origin_country"] = country
                    parsed["origin_source"] = "raw_name"
                    break

    stock = item.get("stock") or {}
    available = bool(stock.get("isAvailable"))
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": None,
        "roast_hint": None,
        "flavor_notes": flavor,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item.get("applicablePrice"),
        "weight_g": weight,
        "stock_status": "販売中" if available else "完売",
        "out_of_stock": not available,
        "product_url": url,
    }


def scrape_all_products():
    records = []
    for url, x in list_items().items():
        nm = (x.get("name") or x.get("title") or "")
        if any(w in nm for w in EXCLUDE_WORDS):
            continue
        if re.search(r"[6６][0０][0０]\s*[gｇ]", nm):
            continue
        item = get_next_data(url)["props"]["pageProps"]["item"]
        time.sleep(0.5)
        records.append(build_record(url, item))
    return records


def main():
    records = scrape_all_products()
    with open("data_fivecoffeewakayama.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_fivecoffeewakayama.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], r["category"], r["origin_country"], r["price"], r["weight_g"], r["stock_status"])


if __name__ == "__main__":
    main()
