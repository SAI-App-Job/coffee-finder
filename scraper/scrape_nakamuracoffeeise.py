# -*- coding: utf-8 -*-
"""
scrape_nakamuracoffeeise.py

なかむら珈琲(三重県伊勢市船江2丁目20-22、公式 https://nakamura-coffee.jp/、2016年伊勢志摩サミット配偶者
プログラムで珈琲を提供)のYahoo!ショッピングストア(store.shopping.yahoo.co.jp/coffee-nakamura)の
コーヒー豆の商品情報を取得する。
※兵庫県神戸市の「NAKAMURA coffee」(scrape_nakamuracoffee.py / nakamuracoffee.shop-pro.jp)とは別の店。

【住所】公式サイト記載の「三重県伊勢市船江2丁目20-22」(2026-10-11確認。船江本店のほか
おかげ横丁に喫茶・販売店あり)。

【取得方法】search.html (2ページ・全53件、2ページ目は ?page=1) の __NEXT_DATA__ から商品一覧を取り、
各商品ページの __NEXT_DATA__ (props.pageProps.item) から name / applicablePrice / information /
stock.isAvailable / selectOptionList(「内容量」の最小容量が基準価格) / specList を読む。
【対象】名称が「コーヒー豆」で始まる焙煎豆15件(+「ブラジル 中煎り(ハイロースト)」)。
ドリップバッグ・ディップバッグ・各種セット・水出し/リキッドアイス・カフェオレ・菓子・雑貨は除外。
【重量】価格は最小容量(内容量オプションの先頭=100g)の価格。内容量オプションが無い商品(エクアドル ゲイシャ)
は容量が不明のため weight_g は null。
robots.txt: store.shopping.yahoo.co.jpはUser-agent: *に対し/cgi-bin/等のみDisallow。
"""

import json
import re
import time

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "なかむら珈琲",
    "url": "https://store.shopping.yahoo.co.jp/coffee-nakamura/",
    "platform": "Yahoo!ショッピング",
    "address": "三重県伊勢市船江2丁目20-22",
    "prefecture": "三重県",
    "robots_txt_status": "実質許可(Yahoo!ショッピング標準。/cgi-bin/等のみDisallow、search.htmlは取得可)",
}

BASE = "https://store.shopping.yahoo.co.jp/coffee-nakamura"
SEARCH_URLS = [BASE + "/search.html", BASE + "/search.html?page=1"]
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}
NEXT_DATA = re.compile(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)

EXTRA_BEAN_CODES = {"n000000000074"}  # 「ブラジル 中煎り(ハイロースト)」(名称に「コーヒー豆」が付かない)
EXCLUDE_WORDS = ["セット", "ドリップ", "ディップ", "ようかん", "水出し", "カフェオレ"]
ROAST_RE = re.compile(r"(中浅煎り|中深煎り|浅煎り|中煎り|深煎り)")
BLEND_WORDS = ["ブレンド"]
# 焙煎段階名(ロースト名)のまま入った値を日本語の焙煎度に揃える
ROAST_NORMALIZE = {
    "フルシティロースト": "深煎り", "フレンチロースト": "深煎り", "シティロースト": "中深煎り",
    "ハイロースト": "中煎り", "ミディアムロースト": "中浅煎り",
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
        sr = d["props"]["initialState"]["bff"]["searchResults"]["items"]
        sr = list(sr.values())[0]
        for blk in sr:
            if blk.get("type") != "PAGER":
                for x in blk["content"].get("items", []) if isinstance(blk.get("content"), dict) else []:
                    items[x["url"].split("?")[0]] = x
        time.sleep(0.5)
    return items


def fetch_detail(url):
    d = get_next_data(url)
    return d["props"]["pageProps"]["item"]


def clean_html(s):
    s = re.sub(r"<br\s*/?>", "\n", s or "")
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return s.strip()


def build_record(url, item):
    raw = item["name"].replace("　", " ")
    raw = re.sub(r"\s+", " ", raw).strip()
    name = re.sub(r"^コーヒー豆\s*", "", raw)
    is_blend = any(w in name for w in BLEND_WORDS)

    info = clean_html(item.get("information"))
    info = info.split("【お得なセットオプション】")[0].strip()
    flavor = re.sub(r"\n\s*\n+", "\n", info)
    flavor = re.sub(r"\s*\n\s*", " ", flavor).strip()[:400] or None

    # 重量: 「内容量」オプションの先頭(最小容量)、無ければ specList の容量
    weight = None
    for opt in item.get("selectOptionList") or []:
        if opt.get("name") == "内容量" and opt.get("choiceList"):
            m = re.match(r"(\d+(?:\.\d+)?)\s*(kg|g)", opt["choiceList"][0]["name"])
            if m:
                weight = int(float(m.group(1)) * (1000 if m.group(2) == "kg" else 1))
            break
    if weight is None:
        for spec in item.get("specList") or []:
            if "容量" in spec.get("name", "") and spec.get("valueList"):
                m = re.match(r"(\d+(?:\.\d+)?)g", spec["valueList"][0]["name"])
                if m:
                    weight = int(float(m.group(1)))
                break

    rm = ROAST_RE.search(name)
    roast = rm.group(1) if rm else None
    if not roast:
        im = re.search(r"焙煎度合[い]?[：:\s]*(?:<br>|\n)?\s*(中浅煎り|中深煎り|浅煎り|中煎り|深煎り|Light Roa)", info)
        if im:
            roast = {"Light Roa": "浅煎り"}.get(im.group(1), im.group(1))
    fm = re.search(r"農園[:：]", info)  # noqa: F841

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
        "roast_level": ROAST_NORMALIZE.get(roast or parsed["roast_level"], roast or parsed["roast_level"]),
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
        code = url.rsplit("/", 1)[-1].replace(".html", "")
        nm = (x.get("name") or x.get("title") or "").replace("　", " ")
        if not (nm.startswith("コーヒー豆") or code in EXTRA_BEAN_CODES):
            continue
        if any(w in nm for w in EXCLUDE_WORDS):
            continue
        item = fetch_detail(url)
        time.sleep(0.5)
        records.append(build_record(url, item))
    return records


def main():
    records = scrape_all_products()
    with open("data_nakamuracoffeeise.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_nakamuracoffeeise.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], r["category"], r["origin_country"], r["roast_level"], r["price"], r["weight_g"], r["stock_status"])
        print("     ", (r["flavor_notes"] or "")[:70])


if __name__ == "__main__":
    main()
