# -*- coding: utf-8 -*-
"""
scrape_jikabaisen.py

Mr.自家焙煎(豊園茶舗、千葉県柏市西原2-2-9、Yahoo!ショッピング store.shopping.yahoo.co.jp/jikabaisen)の
商品情報を取得する。創業60年の茶舗(代表 田中康蔵)が、静岡茶・落花生・海苔・アイスと並んで
自家焙煎コーヒー豆を販売するストア。商品ページに「自家焙煎工房で煎るプレミアムコーヒーを
市価の半値以下でお届け」とあり、コーヒー豆は自店の焙煎。実店舗は1店(柏市西原)。

【プラットフォームについて】
他のYahoo!ショッピング店舗(scrape_juncoffee.py / scrape_mameyanetshop.py)と同様、店舗の商品一覧
(/search.html、2ページ目は ?page=1)の Next.js `__NEXT_DATA__` JSON
(props.initialState.bff.searchResults.items."1"[1].content.items)に商品名・価格・URLが埋め込まれている。
robots.txtでは /search.html のクエリなし・page指定は Disallow 対象外。

【対象商品について】
実データ確認済み(2026-10時点、全32件): 「コーヒー」カテゴリ13件(全て200g)のみを対象とする。
アイスクリーム・落花生・海苔・静岡茶(お茶9件)は対象外。ブレンド6(深煎り・オリジナル・リーズナブル・
ロイヤル、ほか)・ストレート7。商品名はSEO向けの長いタイトル(「スペシャルティコーヒー コーヒー豆 珈琲
… 200g 自家焙煎 ドリップ 豊園茶舗 Mr.自家焙煎」)のため、定型語を除去して銘柄名を取り出す。
同一銘柄(グアテマラ リオアズール/リオアスール)が別ページで2件掲載されているが、別商品ページのため
そのまま2件として収録する。マンデリン ポルンアルフィナーは焙煎度違い(浅煎り・深煎り・指定なし)の
別ページがあり、焙煎度は商品名に含まれるものを roast_level に反映する。
価格は一覧JSONの `price`(税込表示価格)。在庫は詳細ページの availability(schema.org)で判定する。
"""

import html
import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "Mr.自家焙煎(豊園茶舗)",
    "url": "https://store.shopping.yahoo.co.jp/jikabaisen/",
    "platform": "Yahoo!ショッピング",
    "address": "千葉県柏市西原2-2-9",
    "prefecture": "千葉県",
    "robots_txt_status": "実質許可(2026-10確認。User-agent: *は/cgi-bin/・/search.htmlの絞り込みクエリ等のみDisallow。"
                          "本スクレイパーが使う/search.html・?page=1は制限対象外)",
}

BASE_URL = "https://store.shopping.yahoo.co.jp/jikabaisen"
LIST_URLS = [f"{BASE_URL}/search.html", f"{BASE_URL}/search.html?page=1"]
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; CoffeeFinderBot/0.1; +contact: your-contact-info-here)"
}
NEXT_DATA_PATTERN = re.compile(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)
BOILERPLATE = (
    "Mr.自家焙煎", "スペシャルティコーヒー", "コーヒー豆", "珈琲", "自家焙煎", "ドリップ", "豊園茶舗",
    "送料無料", "200g", "200ｇ",
)
ROAST_WORDS = ("中深煎り", "深煎り", "中煎り", "浅煎り")
ORIGIN_OVERRIDES = {
    "ロイヤルブレンド": None,
}


def fetch_list_items() -> list[dict]:
    items: list[dict] = []
    for url in LIST_URLS:
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
        resp.raise_for_status()
        m = NEXT_DATA_PATTERN.search(resp.content.decode("utf-8"))
        if not m:
            continue
        data = json.loads(m.group(1))
        try:
            page_items = data["props"]["initialState"]["bff"]["searchResults"]["items"]["1"][1]["content"]["items"]
        except (KeyError, IndexError, TypeError):
            continue
        items.extend(page_items)
    return items


def fetch_detail(url: str) -> dict:
    try:
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[warn] 詳細ページ取得失敗: {url} ({e})")
        return {"in_stock": True, "notes": None}
    text = resp.content.decode("utf-8")
    soup = BeautifulSoup(text, "html.parser")
    og = soup.select_one('meta[property="og:description"]')
    notes = None
    if og and og.get("content"):
        desc = html.unescape(og["content"])
        desc = BeautifulSoup(desc.replace("<br>", "\n"), "html.parser").get_text("\n", strip=True)
        lines = [ln for ln in desc.split("\n") if ln and not ln.startswith(("内容量", "外形寸法", "形式", "賞味期限", "保存方法", "※")) and "ゆうパケット" not in ln]
        notes = " / ".join(lines).strip() or None
    in_stock = "schema.org/OutOfStock" not in text and "schema.org/SoldOut" not in text
    return {"in_stock": in_stock, "notes": notes}


def clean_name(title: str) -> str:
    n = title
    for b in BOILERPLATE:
        n = n.replace(b, " ")
    n = re.sub(r"[\s　]+", " ", n).strip()
    return n


def is_coffee_bean(title: str) -> bool:
    return ("コーヒー豆" in title or "珈琲" in title) and "ティーバッグ" not in title and "静岡茶" not in title


def build_record(item: dict) -> dict | None:
    title = (item.get("name") or "").strip()
    if not is_coffee_bean(title):
        return None
    wm = re.search(r"(\d+)\s*[gｇ]", title)
    name = clean_name(title)
    url = (item.get("url") or "").split("?")[0]
    detail = fetch_detail(url)

    parsed = parse_product(name)
    is_blend = "ブレンド" in name
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        detected = detect_country_name(name)
        if "マンデリン" in name and not detected:
            detected = "インドネシア"
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)

    roast_level = parsed["roast_level"]
    for w in ROAST_WORDS:
        if w in name:
            roast_level = w
            break

    out = not detail["in_stock"]
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_hint": None,
        "flavor_notes": detail["notes"],
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item.get("price"),
        "weight_g": int(wm.group(1)) if wm else None,
        "stock_status": "完売" if out else "販売中",
        "out_of_stock": out,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in fetch_list_items():
        rec = build_record(item)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_jikabaisen.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_jikabaisen.json に出力しました")


if __name__ == "__main__":
    main()
