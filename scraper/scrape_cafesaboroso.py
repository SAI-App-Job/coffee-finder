# -*- coding: utf-8 -*-
"""
scrape_cafesaboroso.py

Cafe Saboroso(カフェサボローゾ焙煎所、京都府京田辺市薪東沢21-3)のカラーミーショップ
(cafe-saboroso.com、EUC-JP)から焙煎豆の商品情報を取得する。

【対象】カテゴリ「シングル」(505644)・「定番ブレンド」(505645)・「創作ブレンド」(517098)の豆。
各商品は 200g/250g/400g/500g/1kg × 豆のまま/各挽き目の選択式で、最小重量200g・豆のままの価格を代表とする
(表示価格=200gの価格)。除外: おためしセット・きまぐれセット(詰め合わせ)、カフェ・オ・レのもと・
ドリップバッグ、器具、おくりもの、スイーツ、書籍。
在庫は一覧の「SOLD OUT」表示で判定(売り切れ商品は一覧に価格が出ないため詳細ページのColorme JSONから取る)。
焙煎度は商品名・説明文中の「〜煎り」表記から取る(明記が無ければNone)。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "Cafe Saboroso",
    "url": "https://cafe-saboroso.com/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "京都府京田辺市薪東沢21-3",
    "prefecture": "京都府",
    "robots_txt_status": "許可(2026-10確認。robots.txtは/secure/と/cart/のみ禁止)",
    "source_note": "カラーミーショップのカテゴリ「シングル」「定番ブレンド」「創作ブレンド」と各商品ページを2026-10-21に確認。住所は特定商取引法ページ(https://cafe-saboroso.com/?mode=sk)。「価格改定のお知らせ(2025年5月9日より)」が最新の価格告知",
    "last_verified_at": "2026-10-21",
}

BASE_URL = "https://cafe-saboroso.com"
CATEGORIES = [("505644", "ストレート"), ("505645", "ブレンド"), ("517098", "ブレンド")]
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
INTERVAL = 1.6
ROAST_RE = re.compile(r"(中深煎|中浅煎|浅煎|中煎|深煎)り?")
COUNTRIES = ["エチオピア", "コロンビア", "ケニア", "ブラジル", "グアテマラ", "コスタリカ", "インドネシア"]
ORIGIN_OVERRIDE = {"グァテマラ": "グアテマラ"}
COLORME_RE = re.compile(r"var Colorme = (\{.*?\});\s*\n", re.S)

_last = [0.0]


def fetch(url):
    wait = INTERVAL - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    _last[0] = time.time()
    resp.encoding = "euc-jp"
    return resp


def scrape_list(cbid):
    resp = fetch(f"{BASE_URL}/?mode=cate&cbid={cbid}&csid=0&sort=n")
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    items = []
    for li in soup.select("li.c-product-list__item"):
        a = li.select_one("a.c-product-list__name")
        if not a:
            continue
        items.append({
            "title": a.get_text(" ", strip=True),
            "href": a["href"],
            "sold_out": "SOLD OUT" in li.get_text(),
        })
    return items


def fetch_detail(href):
    resp = fetch(f"{BASE_URL}/{href}")
    resp.raise_for_status()
    html = resp.text
    price = None
    m = COLORME_RE.search(html)
    if m:
        try:
            price = json.loads(m.group(1))["product"]["sales_price_including_tax"]
        except (ValueError, KeyError):
            pass
    soup = BeautifulSoup(html, "html.parser")
    for s in soup(["script", "style"]):
        s.decompose()
    t = soup.get_text("\n", strip=True)
    a = t.find("ツイート")
    b = t.find("この商品を購入する")
    desc_lines = []
    if a >= 0 and b > a:
        lines = t[a:b].split("\n")[1:]
        for l in lines:
            if re.fullmatch(r"[\d,]+円\(内税\)(\s*〜\s*[\d,]+円\(内税\))?", l):
                continue
            if re.match(r"^\d+(g|kg|ｇ)", unicodedata.normalize("NFKC", l)) and "･･･" in l:
                continue
            if "ネコポス" in l or "ご希望のグラム数" in l:
                continue
            if re.search(r"お休み|再開は|入荷が|販売を開始|こちらも是非|また違った", l):
                continue  # 古い休売告知は除く
            desc_lines.append(l)
    desc = "\n".join(desc_lines).strip() or None
    paused = bool(re.search(r"販売お休みし中|入荷待ち", t[a:b])) if a >= 0 and b > a else False
    return price, desc, paused


def clean_name(title):
    t = unicodedata.normalize("NFKC", title)
    t = re.sub(r"\s*\(\s*\d+\s*g\s*[〜~～]?\s*\)", "", t)
    return re.sub(r"\s+", " ", t).strip()


def detect_roast(name, desc):
    m = ROAST_RE.search(name)
    if m:
        return m.group(1) + "り"
    found = set(ROAST_RE.findall(desc or ""))
    return found.pop() + "り" if len(found) == 1 else None


def build_record(it, kind, price, desc):
    name = clean_name(it["title"])
    parsed = parse_product(name)
    if kind == "ブレンド":
        category, origin, origin_source, brand = "ブレンド", None, None, None
    else:
        parsed = apply_category_hint_fallback(parsed, name)
        category = parsed["category"]
        origin = ORIGIN_OVERRIDE.get(parsed["origin_country"], parsed["origin_country"])
        origin_source = parsed["origin_source"]
        brand = parsed["designated_brand"]
        if origin is None and desc:
            hits = [c for c in COUNTRIES if c in desc]
            if len(hits) == 1:  # モカ等は説明文の産地表記から補う
                origin, origin_source = hits[0], "shop_attribute"
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": category,
        "origin_country": origin,
        "origin_source": origin_source,
        "designated_brand": brand,
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": detect_roast(name, desc),
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": 200,
        "stock_status": "完売" if it["sold_out"] else "販売中",
        "out_of_stock": it["sold_out"],
        "product_url": f"{BASE_URL}/{it['href']}",
    }


def scrape_all_products():
    records = []
    for cbid, kind in CATEGORIES:
        for it in scrape_list(cbid):
            price, desc, paused = fetch_detail(it["href"])
            if paused:
                it["sold_out"] = True  # 説明文に「販売お休み中/入荷待ち」と明記されている商品は品切れ扱い
            if price is None:
                print(f"[warn] 価格取得失敗: {it['title']}")
                continue
            records.append(build_record(it, kind, price, desc))
    return records


def main():
    records = scrape_all_products()
    with open("data_cafesaboroso.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_cafesaboroso.json に出力しました")
    for r in records:
        print(r["raw_name"], r["category"], r["origin_country"], r["price"], r["weight_g"], r["roast_level"], r["stock_status"])


if __name__ == "__main__":
    main()
