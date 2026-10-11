# -*- coding: utf-8 -*-
"""
scrape_nikonikocoffee.py

ニコニコ珈琲(nico-coffee.net、茨城県土浦市下高津1-21-50、公式 nico-coffee.com)の
商品情報を取得する。EC-CUBE 3系(煎豆屋 scrape_irimameya.py と同系統)。
※ scrape_nicocoffee.py は別店(nico caffee roaster、神奈川県藤沢市)のため、
  本店は slug を nikonikocoffee とした。

robots.txt確認済み(2026-10時点): `Disallow: /*.csv$` のみ。商品ページは制限対象外。

【商品一覧】/products/list?pageno=N&disp_number=60(全商品、60件)を巡回し、
/products/detail/<id> を取得する。

【除外】ドリップバッグ・ギフト・ネルフィルター・コールドブリュー・セット/飲み比べ・
アイス水出し用小分けアソート・さくら(フレーバー)・ネルフィルター付き商品。
【重量・重複】同一銘柄が100/180/200/300/380/400/500g等で別商品登録されているため、
整形した銘柄名でグルーピングして最小重量を代表にする。
【価格】`.price02_default`(表示は税込、送料込み/一部送料無料表記の商品)。
【焙煎度】説明文の「焙煎レンジ」行をraw_nameに付与して焙煎度をパースする。
"""

import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "ニコニコ珈琲",
    "url": "https://nico-coffee.net/",
    "platform": "EC-CUBE",
    "address": "茨城県土浦市下高津1-21-50",
    "prefecture": "茨城県",
    "robots_txt_status": "実質許可(2026-10確認。Disallow: /*.csv$ のみ。商品ページは制限対象外)",
}

BASE_URL = "https://nico-coffee.net"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "ドリップバッグ", "ギフト", "ネル", "フィルター", "コールドブリュー", "スタータ",
    "飲み比べ", "セット", "各50g", "5産地", "さくら", "タンブラー", "定期便", "生豆",
]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
PRICE_PATTERN = re.compile(r"[\d,]+")
NOISE_PHRASES = [
    "究極のコーヒー", "お得！焙煎", "お得！", "焙煎即だし", "焙煎即出荷", "焙煎即出し",
    "収穫したて新豆", "収穫新豆", "新豆", "夏の旬", "ふるさとコーヒー", "オリジナル",
    "アイスコーヒーレシピ付", "≪深煎≫", "豆または粉", "豆・粉", "（送料込み）", "(送料込み)",
]
KEEP_BRACKETS = ("エメラルドマウンテン", "デカフェ")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_product_ids() -> list[str]:
    ids: list[str] = []
    for page in range(1, 10):
        soup = fetch_page(f"{BASE_URL}/products/list?pageno={page}&disp_number=60")
        found = []
        for a in soup.select('a[href*="/products/detail/"]'):
            m = re.search(r"/products/detail/(\d+)", a.get("href", ""))
            if m and m.group(1) not in ids and m.group(1) not in found:
                found.append(m.group(1))
        if not found:
            break
        ids.extend(found)
    return ids


def clean_name(title: str) -> str:
    n = unicodedata.normalize("NFKC", title)
    wm = WEIGHT_PATTERN.search(n)
    if wm:
        n = n[:wm.start()]
    n = n.replace("sea・ne", "海音")
    for kw in KEEP_BRACKETS:
        n = n.replace(f"【{kw}】", f"@@{kw}@@")
    n = re.sub(r"【[^】]*】", " ", n)
    n = n.replace("@@", " ")
    for ph in NOISE_PHRASES:
        n = n.replace(unicodedata.normalize("NFKC", ph), " ")
    n = n.replace("_", " ")
    return re.sub(r"\s+", " ", n).strip()


def group_key(name: str) -> str:
    # 同一銘柄の表記ゆれ(No2、中黒、空白)を吸収したグルーピングキー
    k = re.sub(r"No\.?\s*2", "", name, flags=re.I)
    return re.sub(r"[\s・･()（）]", "", k)


def extract_fields(soup: BeautifulSoup) -> dict | None:
    title_el = soup.find("title")
    if not title_el:
        return None
    parts = title_el.get_text(strip=True).split(" / ", 1)
    title = (parts[1] if len(parts) > 1 else parts[0]).strip()
    price_el = soup.select_one(".price02_default")
    price = None
    if price_el:
        m = PRICE_PATTERN.search(price_el.get_text())
        if m:
            price = int(m.group(0).replace(",", ""))
    ntitle = unicodedata.normalize("NFKC", title)
    wm = WEIGHT_PATTERN.search(ntitle)
    weight = int(wm.group(1)) if wm else None
    roast = None
    desc = soup.select_one("#detail_not_stock_box__description_detail")
    if desc:
        for br in desc.find_all("br"):
            br.replace_with("\n")
        for line in desc.get_text().split("\n"):
            m = re.match(r"\s*焙煎レンジ[\s　]+(.+)", unicodedata.normalize("NFKC", line))
            if m:
                # 「ブラジル ライトロースト」のように産地が前置される場合は末尾の焙煎度のみ採用
                roast = m.group(1).strip().split(" ")[-1]
                break
    sold_out = "カートに入れる" not in soup.get_text()
    return {"title": title, "price": price, "weight": weight,
            "roast": roast, "sold_out": sold_out}


def pick_canonical_items(items: list[dict]) -> list[dict]:
    by_key: dict[str, dict] = {}
    for item in items:
        k = group_key(item["name"])
        ex = by_key.get(k)
        w = item["weight"] or float("inf")
        if ex is None or w < (ex["weight"] or float("inf")):
            by_key[k] = item
    return list(by_key.values())


def build_record(item: dict) -> dict:
    raw_name = item["raw_name"]
    parsed = parse_product(raw_name)
    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"], "raw_name": raw_name,
            "category": "フレーバー", "is_flavored": True,
            "flavor_name": parsed["flavor_name"], "price": item["price"],
            "product_url": item["url"],
        }
    stock_status = "品切れ" if item["sold_out"] else detect_stock_status(raw_name)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": raw_name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "flavor_notes": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": item["weight"],
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    all_items = []
    for pid in fetch_product_ids():
        url = f"{BASE_URL}/products/detail/{pid}"
        try:
            f = extract_fields(fetch_page(url))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {url} ({e})")
            continue
        if not f:
            continue
        ntitle = unicodedata.normalize("NFKC", f["title"])
        if any(unicodedata.normalize("NFKC", kw) in ntitle for kw in NON_BEAN_KEYWORDS):
            continue
        if not f["weight"]:
            continue
        f["url"] = url
        f["name"] = clean_name(f["title"])
        f["raw_name"] = " ".join(x for x in [f["name"], f"{f['weight']}g", f["roast"]] if x)
        all_items.append(f)

    previous = load_previous_products(SHOP_INFO["name"])
    records, flavored = [], []
    for item in pick_canonical_items(all_items):
        prev = previous.get(item["url"])
        if is_unchanged(prev, raw_name=item["raw_name"]):
            records.append(prev)
            continue
        d = build_record(item)
        (flavored if d.get("is_flavored") else records).append(d)
    return records, flavored


if __name__ == "__main__":
    import json

    records, flavored = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records,
              "flavored_products_excluded": flavored}
    with open("data_nikonikocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_nikonikocoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored)}件は別枠に分離)")
