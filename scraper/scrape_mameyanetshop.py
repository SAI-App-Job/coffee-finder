# -*- coding: utf-8 -*-
"""
scrape_mameyanetshop.py

自家焙煎 珈琲豆屋(千葉県柏市柏1-1-11、Yahoo!ショッピング store.shopping.yahoo.co.jp/mameya-netshoop
運営は有限会社コーヒーファーム、代表 松村岳志。柏駅前で40年以上続く
自家焙煎珈琲豆の専門店で、自社EC以外の通販はこのYahoo!ショッピングストア)の商品情報を取得する。

【店舗・住所について】
Yahoo!ストアの会社概要の住所は法人所在地(柏市豊四季1008-3)だが、実店舗は柏駅前
「自家焙煎珈琲 豆屋」(柏市柏1-1-11、店主 松村岳志)で、店主名が一致することをWeb検索で確認した。
本スクレイパーでは実店舗の住所を採用する(ビル名は資料により「丸井ビル」「ファミリかしわ」と
揺れるため記載しない)。

【プラットフォームについて】
他のYahoo!ショッピング店舗(scrape_juncoffee.py)と同様、店舗の商品一覧(/search.html、2ページ目は
?page=1)は Next.js の `__NEXT_DATA__` JSON(props.initialState.bff.searchResults.items."1"[1].content.items)
に商品名・価格・URLが埋め込まれている。robots.txtでは /search.html のクエリなし・page指定は
Disallow対象外(strcid=・brandid=・spec=等の絞り込みのみDisallow)。

【対象商品について】
実データ確認済み(2026-10時点、全37件): 各銘柄は「銘柄名/200g」(通常販売)と
「銘柄名/1kg以上のご注文はこちらから。(まとめ買い…)」(1kg以上の大口注文用の別ページ)の2種があり、
前者の200gのみを代表として採用する(まとめ買いページは重量違いの重複として除外)。
ペーパー&ドリッパー類(カリタ等)は対象外。ブレンド(シティ・スペシャル・マイルド・モカ・アイスコーヒー)と
ストレート(ブラジル・コロンビア・グァテマラ・キリマンジャロ・マンデリン・モカ各種・ケニア・
ルワンダ・エメラルド/クリスタルマウンテン等)が対象。
価格は一覧JSONの `price`(税込表示価格、ポイント還元前)。2026-01の価格改定(一部10〜20%値上げ)後の価格。
在庫は商品詳細ページの `availability`(schema.org/InStock)で判定し、説明文は og:description の
商品説明(【商品情報】より前)を flavor_notes にする。
"""

import html
import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "自家焙煎 珈琲豆屋",
    "url": "https://store.shopping.yahoo.co.jp/mameya-netshoop/",
    "platform": "Yahoo!ショッピング",
    "address": "千葉県柏市柏1-1-11",
    "prefecture": "千葉県",
    "robots_txt_status": "実質許可(2026-10確認。User-agent: *は/cgi-bin/・/search.htmlの絞り込みクエリ等のみDisallow。"
                          "本スクレイパーが使う/search.html・?page=1は制限対象外)",
}

BASE_URL = "https://store.shopping.yahoo.co.jp/mameya-netshoop"
LIST_URLS = [f"{BASE_URL}/search.html", f"{BASE_URL}/search.html?page=1"]
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; CoffeeFinderBot/0.1; +contact: your-contact-info-here)"
}
NEXT_DATA_PATTERN = re.compile(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)
EXCLUDE_KEYWORDS = ("1kg以上", "1Kg以上", "カリタ", "ドリッパー", "ペーパー", "フィルター", "ロシ")

ORIGIN_OVERRIDES = {
    "スペシャルブレンド": None,
    "モカ・シダモ": "エチオピア",
    "モカ・マタリ9": "イエメン",
    "モカ・イルガチェフェ": "エチオピア",
    "エメラルドマウンテン": "コロンビア",
    "クリスタルマウンテン": "キューバ",
    "マンデリン G1": "インドネシア",
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
        desc = re.split(r"<br>\s*<br>\s*【商品情報】|【商品情報】", desc)[0]
        desc = BeautifulSoup(desc.replace("<br>", "\n"), "html.parser").get_text("\n", strip=True)
        notes = " ".join(desc.split("\n")).strip() or None
    in_stock = "schema.org/OutOfStock" not in text and "schema.org/SoldOut" not in text
    return {"in_stock": in_stock, "notes": notes}


def build_record(item: dict) -> dict | None:
    title = (item.get("name") or "").strip()
    if not title or any(k in title for k in EXCLUDE_KEYWORDS):
        return None
    wm = re.search(r"/\s*(\d+)\s*[gｇ]\s*$", title)
    if not wm:
        return None
    name = re.sub(r"\s*/\s*\d+\s*[gｇ]\s*$", "", title).strip()
    url = (item.get("url") or "").split("?")[0]
    detail = fetch_detail(url)

    parsed = parse_product(name)
    is_blend = "ブレンド" in name or "アイスコーヒー" in name
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        override = ORIGIN_OVERRIDES.get(name)
        detected = override or detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)

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
        "roast_level": parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": detail["notes"],
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item.get("price"),
        "weight_g": int(wm.group(1)),
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
    with open("data_mameyanetshop.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mameyanetshop.json に出力しました")


if __name__ == "__main__":
    main()
