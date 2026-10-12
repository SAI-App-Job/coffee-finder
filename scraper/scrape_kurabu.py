# -*- coding: utf-8 -*-
"""
scrape_kurabu.py

珈琲倶ら部(山梨県富士吉田市松山1-4-56、coffeemame.cart.fc2.com、公式Wix
https://fujiyoshida-coffee.wixsite.com/umai-coffee)の商品情報を取得する。FC2ショッピングカート。

【ページ構造】
カテゴリ「コーヒー」(/?ca=1、30件)に par_page=100 をPOSTして全件を1ページに出し、各商品
(`li.item_inner` の `dt.name a` = 商品名・リンク、`dd.price` = 価格)の詳細ページ
(/ca1/<id>/p-r1-s/)から説明文(「シェアする」と「商品検索」の間)と在庫(バリエーション select の
data-stock/data-submit、「[完売しました]」表記)を取る。バリエーションは豆/粉と、数量セレクタ
100g〜1000gで、表示価格は100gあたりの価格。

【対象商品】
実データ確認済み(2026-10時点): 「コーヒー」30件のうち焙煎豆28件(商品名末尾の「100g」)を対象とし、
NAMESの表のとおり整形する。除外: 水出しアイス(65g×5袋入、パック品)・アイスコーヒー1Lパック
(液体)。「ふじやま、ぐるめ、富士五湖、樹海ぶれんど、お気に煎り100g」(id=82)は1ページに5種の別銘柄
ブレンドが選択肢として並ぶ(同一価格550円)ため、5銘柄を別商品として収録する(product_urlは
ページURL#銘柄名)。「ブラジル サンマリノサンドライ(浅煎り・中煎り)」(id=59)は焙煎度を購入時に選ぶ
方式のため roast_selectable=True・roast_hint とする。「10月のおすすめ珈琲 ブラジル・サンマリノ
サンドライ」(id=48)は月替わりの割引品(中煎り)として別商品で収録する。
ドリップバッグ(16件)・ギフト・ココアは対象外。
"""

import json
import re
import unicodedata
import urllib.parse

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "珈琲倶ら部",
    "url": "https://coffeemame.cart.fc2.com/",
    "platform": "FC2ショッピングカート(cart.fc2.com)",
    "address": "山梨県富士吉田市松山1-4-56",
    "prefecture": "山梨県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://coffeemame.cart.fc2.com"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}
ROAST_RE = r"(中深煎り|中浅煎り|浅煎り|中煎り|深煎り)"
PAREN_ROAST_PATTERN = re.compile(r"[（(][^）)]*?" + ROAST_RE + r"[^）)]*[）)]")
ROAST_PATTERN = re.compile(ROAST_RE)

# id -> (整形名, ブレンドか, 産地国)
NAMES = {
    "48": ("ブラジル・サンマリノサンドライ 10月のおすすめ", False, "ブラジル"),
    "72": ("ブルマンぶれんど", True, None),
    "49": ("モカモカぶれんど", True, None),
    "64": ("ビタスキぶれんど", True, None),
    "90": ("フレンチモカ", False, "エチオピア"),
    "89": ("ラオス・ゲイシャ", False, "ラオス"),
    "71": ("ブルーマウンテン", False, "ジャマイカ"),
    "54": ("タンザニア", False, "タンザニア"),
    "27": ("パナマ・バルマウンテン", False, "パナマ"),
    "15": ("レトロぶれんど", True, None),
    "25": ("ペルー・マチュピチュQグレード", False, "ペルー"),
    "26": ("ケニアAA Qグレード", False, "ケニア"),
    "20": ("コスタリカ・ジャガーハニー", False, "コスタリカ"),
    "6": ("ドミニカ・バラオナ", False, "ドミニカ共和国"),
    "9": ("コロンビア・ナリーニョ", False, "コロンビア"),
    "75": ("モカゲイシャG3", False, "エチオピア"),
    "10": ("モカ イルガチャフェG2", False, "エチオピア"),
    "12": ("トラジャカロシ", False, "インドネシア"),
    "18": ("ルビーマウンテン", False, None),
    "13": ("バリアラビカ", False, "インドネシア"),
    "42": ("グァテマラ", False, "グアテマラ"),
    "59": ("ブラジル サンマリノサンドライ", False, "ブラジル"),
    "53": ("メキシコ Qグレード", False, "メキシコ"),
    "62": ("モカマタリNO9", False, "イエメン"),
    "29": ("マンデリン・G1", False, "インドネシア"),
    "55": ("パプアニューギニア", False, "パプアニューギニア"),
    "63": ("アイスコーヒー", True, None),
}
# id=82 のページに並ぶ5種の別銘柄ブレンド
BLEND_PAGE_ID = "82"
BLEND_PAGE_NAMES = ["ふじやまぶれんど", "ぐるめぶれんど", "富士五湖ぶれんど", "樹海ぶれんど", "お気に煎りぶれんど"]


def fetch_list() -> tuple[dict[str, int], dict[str, str]]:
    sess = requests.Session()
    sess.headers.update(REQUEST_HEADERS)
    resp = sess.post(f"{BASE_URL}/?ca=1", data={"par_page": "100", "Submit_par": "設定"}, timeout=30)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")
    prices: dict[str, int] = {}
    titles: dict[str, str] = {}
    for li in soup.select("li.item_inner"):
        a = li.select_one("dt.name a")
        p = li.select_one("dd.price")
        if not a or not p:
            continue
        m = re.search(r"/ca1/(\d+)/", a["href"])
        pm = re.search(r"([\d,]+)\s*円", unicodedata.normalize("NFKC", p.get_text()))
        if m and pm:
            prices[m.group(1)] = int(pm.group(1).replace(",", ""))
            titles[m.group(1)] = a.get_text(" ", strip=True)
    return prices, titles


def fetch_detail(item_id: str) -> dict:
    url = f"{BASE_URL}/ca1/{item_id}/p-r1-s/"
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")
    opts = soup.select("select[name=variation] option")
    real = [o for o in opts if o.get("value") != "not_selected"]
    sold = {
        o.get_text(strip=True): (o.get("data-stock") == "0" or o.get("data-submit") == "0"
                                 or "完売" in o.get_text())
        for o in real
    }
    for sc in soup(["script", "style"]):
        sc.decompose()
    text = soup.get_text("\n", strip=True)
    a = text.find("シェアする")
    b = text.find("商品検索")
    desc = re.sub(r"\s+", " ", text[a + 5:b]).strip() if a >= 0 and b > a else None
    return {"url": url, "desc": desc or None, "sold": sold, "all_sold": bool(sold) and all(sold.values())}


def detect_roast(title: str, desc: str | None) -> str | None:
    for src in (title, desc or ""):
        m = PAREN_ROAST_PATTERN.search(src)
        if m:
            return ROAST_PATTERN.search(m.group(0)).group(1)
    m = ROAST_PATTERN.search(desc or "")
    return m.group(1) if m else None


def make_record(name: str, is_blend: bool, origin: str | None, price: int, url: str, desc: str | None,
                out: bool, roast: str | None, roast_hint: str | None = None) -> dict:
    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["origin_country"] = origin
        if origin:
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
    rec = {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast,
        "roast_hint": roast_hint,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": 100,
        "stock_status": "完売" if out else "販売中",
        "out_of_stock": out,
        "product_url": url,
    }
    if roast_hint:
        rec["roast_selectable"] = True
    return rec


def scrape_all_products() -> list[dict]:
    prices, titles = fetch_list()
    print(f"[info] 一覧 {len(prices)}件取得")
    records = []
    for item_id, (name, is_blend, origin) in NAMES.items():
        if item_id not in prices:
            print(f"[warn] 一覧に無い: {item_id} {name}")
            continue
        d = fetch_detail(item_id)
        if item_id == "59":
            records.append(make_record(name, is_blend, origin, prices[item_id], d["url"], d["desc"],
                                       d["all_sold"], None, roast_hint="浅煎り・中煎りから選択"))
            continue
        roast = detect_roast(titles.get(item_id, ""), d["desc"])
        records.append(make_record(name, is_blend, origin, prices[item_id], d["url"], d["desc"],
                                   d["all_sold"], roast))
    if BLEND_PAGE_ID in prices:
        d = fetch_detail(BLEND_PAGE_ID)
        for n in BLEND_PAGE_NAMES:
            url = d["url"] + "#" + urllib.parse.quote(n)
            sold = [v for k, v in d["sold"].items() if k.startswith(n)]
            out = bool(sold) and all(sold)
            records.append(make_record(n, True, None, prices[BLEND_PAGE_ID], url, d["desc"], out, None))
    return records


def main():
    records = scrape_all_products()
    with open("data_kurabu.json", "w", encoding="utf-8") as f:
        json.dump({"shop": SHOP_INFO, "products": records}, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kurabu.json に出力しました")
    for r in records:
        print(r["raw_name"], r["category"], r["origin_country"], r["price"], r["weight_g"],
              r["roast_level"], r["roast_hint"], r["stock_status"])


if __name__ == "__main__":
    main()
