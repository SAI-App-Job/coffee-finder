# -*- coding: utf-8 -*-
"""
scrape_mameyatajimi.py

珈琲工房豆家(有限会社豆家珈琲商会、岐阜県多治見市虎渓山町2-63、公式 www.mameya-tajimi.jp)の
Yahoo!ショッピング店「珈琲工房豆家ネットショップ」(store.shopping.yahoo.co.jp/mameya-net)の
商品情報を取得する。

【Yahoo!ショッピング店を採用した理由】
公式サイトは Jimdo 製で、通販は「会員限定ネット通販」。商品ごとの価格・カートがあるのは
Yahoo!ショッピング店のみ(店舗トップの紹介に「産地から選びぬいたコーヒー豆を自家焙煎しています。」)。
前回は「公式がJimdo製で実装前例なし」として見送ったが、実際の販売先はYahoo!ショッピング店のため
他のYahoo!ショッピング店舗(scrape_mameyanetshop.py 等)と同じ方式で実装する。

【取得方法】
店舗の商品一覧(/search.html)は Next.js の `__NEXT_DATA__` JSON(props.initialState.bff.searchResults.items)に
商品名・価格・URLが埋め込まれている(全17件、1ページのみ)。各商品ページの `__NEXT_DATA__`
(props.pageProps.item)から在庫(stock.isAvailable)と説明文(catchCopy/pageComment/metaDescription)を取る。
robots.txt(store.shopping.yahoo.co.jp)は /search.html の絞り込みクエリ等のみ Disallow で、
本スクレイパーが使う /search.html(クエリなし)と商品ページは制限対象外(2026-11-01確認)。
リクエスト間隔は3秒、User-Agent は識別UA(CoffeeFinderBot/0.1)。

【対象商品について】
豆単品15種(ブレンド7 + ストレート8)。
除外: 選べるコーヒーセット(e001)、お試しセット(o001)。
全て200g単位の1種類のみ(100g設定なし)で、「豆の挽き方」オプション(豆のまま/ペーパーフィルター/
サイフォン/コーヒーメーカー)は追加料金なしのため、価格は豆のままの価格と同じ。
価格は一覧JSONの `price`(税込表示価格、ポイント還元前)。焙煎度は商品名に明記のあるもの
(浅煎ブレンド・深煎ブレンド・アイスブレンド〈深くロースト〉)のみ。他は表記なしのため null。
"""

import html
import json
import re
import time
import unicodedata

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "珈琲工房豆家",
    "url": "https://store.shopping.yahoo.co.jp/mameya-net/",
    "platform": "Yahoo!ショッピング",
    "address": "岐阜県多治見市虎渓山町2-63",
    "prefecture": "岐阜県",
    "robots_txt_status": "実質許可とみなす(2026-11-01確認。store.shopping.yahoo.co.jpのrobots.txtは/search.htmlの絞り込みクエリ・/cgi-bin/等のみDisallow。"
                          "本スクレイパーが使う/search.html(クエリなし)と商品ページは制限対象外)",
    "source_note": "Yahoo!ショッピング店(https://store.shopping.yahoo.co.jp/mameya-net/)の商品一覧と各商品ページを2026-11-01に確認。"
                   "ストアのお知らせは2026-10付で更新は新しい。公式(Jimdo)は会員限定通販のため不採用",
    "last_verified_at": "2026-11-01",
}

BASE_URL = "https://store.shopping.yahoo.co.jp/mameya-net"
LIST_URL = f"{BASE_URL}/search.html"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL = 3
NEXT_DATA_PATTERN = re.compile(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)
EXCLUDE_KEYWORDS = ("セット",)

# 商品名にない焙煎度(商品名・説明文に明記のあるもののみ)
ROAST_BY_NAME = {
    "浅煎ブレンド": "浅煎り",
    "深煎ブレンド": "深煎り",
    "アイスブレンド": "深煎り",  # 説明文「深くローストした本格的なアイスコーヒー」
}


def get(url: str) -> requests.Response:
    resp = None
    for attempt in range(3):
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=60)
        if resp.status_code not in (429, 500, 502, 503, 504):
            break
        time.sleep(15 * (attempt + 1))
    return resp


def next_data(text: str) -> dict:
    return json.loads(NEXT_DATA_PATTERN.search(text).group(1))


def fetch_list_items() -> list[dict]:
    resp = get(LIST_URL)
    resp.raise_for_status()
    groups = next_data(resp.content.decode("utf-8"))["props"]["initialState"]["bff"]["searchResults"]["items"]
    items = []
    for entries in groups.values():
        for entry in entries:
            content = entry.get("content") or {}
            if isinstance(content.get("items"), list):
                items.extend(i for i in content["items"] if "name" in i)
    return items


def fetch_detail(url: str) -> dict | None:
    resp = get(url)
    if resp.status_code != 200:
        print(f"[warn] 商品ページ取得失敗: {url} (HTTP {resp.status_code})")
        return None
    item = next_data(resp.content.decode("utf-8"))["props"]["pageProps"].get("item") or {}
    parts = []
    for k in ("catchCopy", "pageComment", "metaDescription"):
        v = html.unescape(re.sub(r"<[^>]+>", " ", item.get(k) or ""))
        v = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", v)).strip()
        if v and v not in parts:
            parts.append(v)
    return {
        "available": bool((item.get("stock") or {}).get("isAvailable", True)),
        "notes": " ".join(parts)[:400] or None,
    }


def clean_name(title: str) -> str:
    name = unicodedata.normalize("NFKC", title)
    name = re.sub(r"\s*\d+\s*[gG]\s*$", "", name)
    return re.sub(r"\s+", " ", name).strip()


def build_record(item: dict) -> dict | None:
    title = (item.get("name") or "").strip()
    if not title or any(k in title for k in EXCLUDE_KEYWORDS):
        return None
    wm = re.search(r"(\d+)\s*[gG]", unicodedata.normalize("NFKC", title))
    weight = int(wm.group(1)) if wm else None
    name = clean_name(title)
    url = (item.get("url") or "").split("?")[0]
    time.sleep(REQUEST_INTERVAL)
    detail = fetch_detail(url)
    if detail is None:
        return None

    parsed = parse_product(name)
    if "ブレンド" in name:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)

    out = not detail["available"]
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": ROAST_BY_NAME.get(name) or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": detail["notes"],
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item.get("price"),
        "weight_g": weight,
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
    with open("data_mameyatajimi.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mameyatajimi.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], "|", r["category"], r["origin_country"], r["roast_level"], r["price"], r["weight_g"], r["stock_status"])


if __name__ == "__main__":
    main()
