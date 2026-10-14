# -*- coding: utf-8 -*-
"""
scrape_tobidasubaisenjo.py

とびだす焙煎所(ダートコーヒー株式会社、和歌山県和歌山市野崎43。老舗珈琲専門店の通販ブランド)の
Yahoo!ショッピングストア(store.shopping.yahoo.co.jp/tobidasu-baisenjo)のコーヒー豆の商品情報を取得する。

【店舗発見の経緯】
全国再調査(和歌山県)の新規発掘で発見。

【取得方法】search.html (30件/ページ、全99件)の __NEXT_DATA__ から商品一覧を取り、
商品コード(例 tbb-columbia-100)の末尾のサイズ表記(100 / 150 / 200 / 500 / 2kg)で同一銘柄を束ねて、
最小重量の商品を代表1件とする。各商品ページの __NEXT_DATA__ (props.pageProps.item) の
applicablePrice / stock.isAvailable / specList(容量・焙煎度) / information を読む。
【対象】とびだすブレンド、グァテマラブレンド、モカブレンド、シーズナルブレンド、ストレート(コロンビア・
キリマンジャロ・マンデリン・ピンクブルボン・コスタリカハニー・ブルーマウンテン・ブルーマウンテンNo.1)、
7DAYS COFFEE(曜日別ブレンド)。
除外: ドリップバッグ、各種セット・ギフト、業務用(1kg単位)、水出しパック、リキッド、ゼリー、カフェラテベース、
菓子、器具、2kg等の大容量(いずれも同銘柄の小容量が別商品にあるため最小重量を代表とする)。
【焙煎度】specListの「焙煎、ローストの度合い」(フルシティ→深煎り、ミディアム→中浅煎り等)。無い商品は
商品名の「深煎り/中煎り」から、それも無ければ null。
robots.txt: store.shopping.yahoo.co.jpはUser-agent: *に対し/cgi-bin/等のみDisallow。
"""

import json
import re
import time

import requests

from coffee_parser import parse_product

SHOP_INFO = {
    "name": "とびだす焙煎所",
    "url": "https://store.shopping.yahoo.co.jp/tobidasu-baisenjo/",
    "platform": "Yahoo!ショッピング",
    "address": "和歌山県和歌山市野崎43",
    "prefecture": "和歌山県",
    "robots_txt_status": "実質許可(Yahoo!ショッピング標準。/cgi-bin/等のみDisallow、search.htmlは取得可)",
}

BASE = "https://store.shopping.yahoo.co.jp/tobidasu-baisenjo"
SEARCH_URLS = [BASE + "/search.html"] + [BASE + f"/search.html?page={i}" for i in range(1, 6)]
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}
NEXT_DATA = re.compile(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)

# 商品コード: tbb-<銘柄>-<サイズ> / 7days-<曜日>-<サイズ>g
CODE_RE = re.compile(
    r"^(?P<brand>tbb-(?:brend|guatemala|kilimanjaro|mandheling|pinkbourbon|costaricahoney|columbia|mochabrend|bluemountain|seasonal)"
    r"|7days-(?:mon|tue|wed|thu|fri|sat|sun))-(?P<size>\d+(?:g|kg)?)$"
)
SPECIAL_CODES = {"tbb-bluemountain-no1"}  # サイズ表記のない単独商品(100g)

# 銘柄ごとの(商品名, ブレンドか, 産地)
BRANDS = {
    "tbb-brend": ("とびだすブレンド", True, None),
    "tbb-guatemala": ("グァテマラブレンド", True, None),
    "tbb-mochabrend": ("モカブレンド", True, None),
    "tbb-seasonal": ("シーズナルブレンド【夏】", True, None),
    "tbb-kilimanjaro": ("キリマンジャロ", False, "タンザニア"),
    "tbb-mandheling": ("マンデリン", False, "インドネシア"),
    "tbb-pinkbourbon": ("ピンクブルボン", False, "コロンビア"),
    "tbb-costaricahoney": ("コスタリカハニー", False, "コスタリカ"),
    "tbb-columbia": ("コロンビア", False, "コロンビア"),
    "tbb-bluemountain": ("ブルーマウンテン", False, "ジャマイカ"),
    "tbb-bluemountain-no1": ("ブルーマウンテン No.1", False, "ジャマイカ"),
}
# 商品ページの説明文が別商品(グァテマラブレンド)の文面の誤掲載になっているため採用しない
NO_FLAVOR_BRANDS = {"tbb-kilimanjaro"}
DAYS = {"mon": "月曜日 MONDAY", "tue": "火曜日 TUESDAY", "wed": "水曜日 WEDNESDAY", "thu": "木曜日 THURSDAY",
        "fri": "金曜日 FRIDAY", "sat": "土曜日 SATURDAY", "sun": "日曜日 SUNDAY"}
ROAST_NORMALIZE = {
    "フルシティロースト": "深煎り", "フレンチロースト": "深煎り", "イタリアンロースト": "深煎り",
    "シティロースト": "中深煎り", "ハイロースト": "中煎り", "ミディアムロースト": "中浅煎り",
    "シナモンロースト": "浅煎り", "ライトロースト": "浅煎り",
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
        n = 0
        for blk in sr:
            if blk.get("type") != "PAGER" and isinstance(blk.get("content"), dict):
                for x in blk["content"].get("items", []):
                    items[x["url"].split("?")[0]] = x
                    n += 1
        if n == 0:
            break
        time.sleep(0.5)
    return items


def clean_html(s):
    s = re.sub(r"<br\s*/?>", "\n", s or "")
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return s.strip()


def size_to_g(size):
    m = re.match(r"(\d+)(kg|g)?$", size)
    v = int(m.group(1))
    return v * 1000 if m.group(2) == "kg" else v


def pick_representatives(items):
    """銘柄ごとに最小重量の商品URLを選ぶ。"""
    groups = {}
    for url in items:
        code = url.rsplit("/", 1)[-1].replace(".html", "")
        if code in SPECIAL_CODES:
            groups.setdefault(code, []).append((100, url, code))
            continue
        m = CODE_RE.match(code)
        if not m:
            continue
        groups.setdefault(m.group("brand"), []).append((size_to_g(m.group("size")), url, code))
    return {b: min(v) for b, v in groups.items()}


def build_record(brand, url, item):
    if brand.startswith("7days-"):
        day = brand.split("-")[1]
        name = f"7DAYS COFFEE {DAYS[day]}"
        is_blend, origin = True, None
    else:
        name, is_blend, origin = BRANDS[brand]

    weight = None
    roast = None
    for spec in item.get("specList") or []:
        if spec.get("name") == "容量（g）" and spec.get("valueList"):
            m = re.match(r"(\d+(?:\.\d+)?)", spec["valueList"][0]["name"])
            if m:
                weight = int(float(m.group(1)))
        if "ロースト" in spec.get("name", "") and spec.get("valueList"):
            r = spec["valueList"][0]["name"]
            roast = ROAST_NORMALIZE.get(r, r)
    if weight is None:
        m = re.search(r"(\d+)\s*g", item["name"])
        weight = int(m.group(1)) if m else None
    if not roast:
        m = re.search(r"(深煎り|中煎り|浅煎り)", item["name"])
        roast = m.group(1) if m else None

    info = clean_html(item.get("information"))
    head = re.split(r"(★美味しく飲んで|★こんな方に|■■ペアリング|【とびだす焙煎所について】)", info)[0]
    flavor = re.sub(r"\s*\n\s*", " ", head).strip()[:400] or None
    if brand in NO_FLAVOR_BRANDS:
        flavor = None

    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed["category"] = "ストレート"
        parsed["origin_country"] = origin
        parsed["origin_source"] = "raw_name"

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
        "roast_level": roast or parsed["roast_level"],
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
    for brand, (_w, url, _code) in sorted(pick_representatives(list_items()).items()):
        item = get_next_data(url)["props"]["pageProps"]["item"]
        time.sleep(0.5)
        records.append(build_record(brand, url, item))
    return records


def main():
    records = scrape_all_products()
    with open("data_tobidasubaisenjo.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_tobidasubaisenjo.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], r["category"], r["origin_country"], r["roast_level"], r["price"], r["weight_g"], r["stock_status"], r["product_url"].rsplit("/", 1)[-1])
        print("     ", (r["flavor_notes"] or "")[:60])


if __name__ == "__main__":
    main()
