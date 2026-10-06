# -*- coding: utf-8 -*-
"""
scrape_supremocoffee.py

珈琲屋スプレモ(www.supremocoffee.jp、広島県三次市十日市東、自家焙煎珈琲店)の商品情報を取得する。
独自CMS(Movable Type)+ 決済カート(ec-sites.jp「カゴ」、es_shop_id=4172)。

【店舗発見の経緯】
全国再調査(広島県)の新規発掘で発見。

【住所について】
オンラインショップ一覧ページの店舗情報で実データ確認済み(2026-10時点): 「住所 広島県三次市十日市東
3丁目3-22 マスダランドビル1F」。

【サイト構造について】
実データ確認済み(2026-10時点): 「コーヒー豆(焙煎度別)」一覧(/online-shop/baisendo/)に焙煎度別
(深煎り/中深煎り/中煎り/浅煎り)の商品ページへのリンクがある。各商品ページはカートのタグ
(es_item_id=○;es_shop_id=4172、100g用と200g用の2つ)を埋め込んでおり、実際の価格・在庫は
カートのスクリプト(js1.ec-sites.jp/syncro.php)が返す。商品ページ本文の静的な価格表示や一覧の
一部名称は古い(例: ケニアの商品ページ本文は980円だがカートは1,050円、「ガラパゴス・サンタクルス」は
一覧で販売終了表記のままだが同じページURLがニカラグアの商品に差し替わっている)ため、
商品名・価格・在庫・重量はカート側(syncro.phpの応答)を正とする。

【対象商品について】
一覧に掲載された21商品ページのうち、カートに100gの商品が存在するもの(ブレンド7・ストレート14=21件。全ページに100gのカート商品あり)を
対象とし、最小重量の100gを代表として採用する。除外: 200g単品(イタリアンブレンド等の200g)・ドリップ
パック・ギフト・スイーツ・器具(別カテゴリ、一覧に含まれない)。商品ページが無いカート商品
(「パナマ・レリダ・ゲイシャN」100g=カート商品ID39。サイト内のどのページにも掲載が無い)は
商品URLを特定できないため対象外とした。

【在庫・価格・焙煎度について】
価格は税込(一覧に「価格は全て税込み・100gの値段」と明記、カート価格と一覧価格は一致)。在庫はカート
応答の stock_num(0以下で在庫切れ、未設定は大きな数値)で判定する。焙煎度は商品名の「(深煎り)」
等、無ければ商品ページのフォルダ名(Fukairi=深煎り、ChuFukairi=中深煎り、Chuiri=中煎り、Asairi=
浅煎り)から決め、どちらも無い商品(ウインターブレンド等)はNone。焙煎度は選択式ではない。

【robots.txtについて】
User-agent: *はDisallow: /mt/のみ(実データ確認済み、2026-10)。商品ページは許可。
"""

import json
import re
import time
import unicodedata

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "珈琲屋スプレモ",
    "url": "https://www.supremocoffee.jp/",
    "platform": "独自CMS(Movable Type)+決済カート(ec-sites.jp)",
    "address": "広島県三次市十日市東3丁目3-22 マスダランドビル1F",
    "prefecture": "広島県",
    "robots_txt_status": "許可(2026-10確認。User-agent: *は/mt/のみDisallow)",
}

BASE_URL = "https://www.supremocoffee.jp"
LIST_URL = BASE_URL + "/online-shop/baisendo/"
CART_URL = "https://js1.ec-sites.jp/syncro.php?sh={shop}&it={item}&pm=kago_ssl_type:,&sec={sec}"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

LIST_ITEM_PATTERN = re.compile(
    r'<div><a href="\s*([^"#][^"]*?)\s*">.*?<h3>(.*?)</h3>.*?<p>(.*?)</p>.*?<div class="price">(.*?)</div>', re.S
)
ES_ID_PATTERN = re.compile(r"es_item_id=(\d+);es_shop_id=(\d+)")
CART_NAME_PATTERN = re.compile(r'es_charset" value="sjis">(.*?)<br />(.*?)<br /><span[^>]*>([\d,]+)円</span>', re.S)
CART_STOCK_PATTERN = re.compile(r"var stock_num_\w+\s*=\s*(-?\d+);")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g", re.I)
ROAST_PATTERN = re.compile(r"(中深煎り|中浅煎り|浅煎り|中煎り|深煎り)")
FOLDER_ROAST = {"Fukairi": "深煎り", "ChuFukairi": "中深煎り", "Chuiri": "中煎り", "Asairi": "浅煎り"}
ORIGIN_OVERRIDES = {
    "インディア": "インド",
    "東ティモール": "東ティモール",
    "グァテマラ": "グアテマラ",
    "コスタリカ": "コスタリカ",
    "パナマ": "パナマ",
    "ニカラグア": "ニカラグア",
    "ペルー": "ペルー",
    "ケニア": "ケニア",
    "タイ": "タイ",
}


def fetch_html(url: str) -> str:
    resp = requests.get(url.strip(), headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def fetch_cart_item(shop_id: str, item_id: str) -> dict | None:
    resp = requests.get(
        CART_URL.format(shop=shop_id, item=item_id, sec=int(time.time() * 1000)),
        headers=REQUEST_HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    text = resp.text
    name_m = CART_NAME_PATTERN.search(text)
    if not name_m:
        return None  # 「存在しない商品です」
    stock_m = CART_STOCK_PATTERN.search(text)
    weight_m = WEIGHT_PATTERN.search(unicodedata.normalize("NFKC", name_m.group(1)))
    return {
        "name": unicodedata.normalize("NFKC", name_m.group(1)),
        "price": int(name_m.group(3).replace(",", "")),
        "stock": int(stock_m.group(1)) if stock_m else None,
        "weight": int(weight_m.group(1)) if weight_m else None,
    }


def list_products() -> list[dict]:
    html_text = fetch_html(LIST_URL)
    products = []
    seen = set()
    for m in LIST_ITEM_PATTERN.finditer(html_text):
        href = m.group(1)
        if not href.startswith("http"):
            href = BASE_URL + href
        if href in seen:
            continue
        seen.add(href)
        products.append({
            "url": href,
            "list_name": unicodedata.normalize("NFKC", re.sub(r"<[^>]+>", "", m.group(2))).strip(),
            "list_desc": re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(3))).strip(),
            "list_price": re.sub(r"<[^>]+>", "", m.group(4)).strip(),
        })
    return products


def pick_roast(*texts: str) -> str | None:
    for t in texts:
        if t:
            m = ROAST_PATTERN.search(t)
            if m:
                return m.group(1)
    return None


def build_record(entry: dict) -> dict | None:
    html_text = fetch_html(entry["url"])
    page_h1_m = re.search(r"<h1[^>]*>(.*?)</h1>", html_text, flags=re.S)
    page_h1 = unicodedata.normalize("NFKC", re.sub(r"<[^>]+>", "", page_h1_m.group(1))).strip() if page_h1_m else ""

    # ページ内のカート商品(100g/200g)から最小重量(100g)を採用する
    best = None
    for item_id, shop_id in ES_ID_PATTERN.findall(html_text):
        cart = fetch_cart_item(shop_id, item_id)
        time.sleep(0.3)
        if not cart or cart["weight"] is None:
            continue
        if "ドリップ" in cart["name"]:
            continue
        if best is None or cart["weight"] < best["weight"]:
            best = cart
    if best is None:
        return None

    discontinued = "販売終了" in entry["list_price"]
    # 一覧が販売終了表記のままページが別商品に差し替わっている場合は、ページ見出しとカートの商品名を採用する
    name_source = page_h1 if discontinued else entry["list_name"]
    name = re.sub(r"\s*\d+\s*g\s*$", "", name_source, flags=re.I).strip()
    name = re.sub(r"\s+", " ", name)

    folder_m = re.search(r"/baisendo/(\w+)/", entry["url"])
    folder_roast = FOLDER_ROAST.get(folder_m.group(1)) if folder_m else None
    roast_hint = pick_roast(name, page_h1) or folder_roast

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    is_blend = "ブレンド" in name or "ブレンド" in page_h1 or "Peaceful" in name
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"]:
            detected = detect_country_name(name)
            if detected:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
        if not parsed["origin_country"]:
            for kw, country in ORIGIN_OVERRIDES.items():
                if name.startswith(kw):
                    parsed["origin_country"] = country
                    parsed["origin_source"] = "raw_name"
                    break
        parsed = apply_category_hint_fallback(parsed, name)

    # 説明: 商品ページ本文の最初の説明文(カート直前)、無ければ一覧の説明文
    desc_m = re.search(r"<article>.*?<div class=\"article-data\">\s*<p>(.*?)</p>", html_text, flags=re.S)
    desc = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", desc_m.group(1))).strip() if desc_m else None
    if not desc and not discontinued:
        desc = entry["list_desc"] or None

    sold_out = best["stock"] is not None and best["stock"] <= 0

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
        "roast_hint": roast_hint,
        "roast_selectable": False,
        "flavor_notes": desc[:400] if desc else None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": best["price"],
        "weight_g": best["weight"],
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": entry["url"],
    }


def scrape_all_products() -> list[dict]:
    records = []
    for entry in list_products():
        try:
            record = build_record(entry)
        except requests.RequestException as e:
            print(f"[warn] 取得失敗: {entry['url']} ({e})")
            continue
        if record is not None:
            records.append(record)
        time.sleep(0.5)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_supremocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_supremocoffee.json に出力しました")


if __name__ == "__main__":
    main()
